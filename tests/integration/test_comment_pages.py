import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.services.moderation_job import ModerationJob
from app.application.services.operation import OperationContext, OperationStatus
from app.core.config import get_settings
from app.domain.entities import Comment, Post
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
)
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Redis"
)


def repository(h: Harness) -> MongoCommentRepository:
    return MongoCommentRepository(h.resources.mongo_client[get_settings().mongodb_database])


async def test_comments_paginate_ties_without_duplicates_and_new_comments_require_refresh(
    harness: Harness,
) -> None:
    h = harness
    store = repository(h)
    date = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(25):
        await store.create(
            Comment(
                id=UUID(int=i + 1),
                post_id=h.post.id,
                user_id=h.user.id,
                text=f"Comment {i}",
                created_at=date,
            )
        )
    path = f"/api/v1/posts/{h.post.id}/comments"
    first_response = await h.client.get(path, headers=h.headers())
    assert first_response.status_code == 200
    first = first_response.json()
    assert len(first["items"]) == 10
    assert [item["text"] for item in first["items"]] == [f"Comment {i}" for i in range(24, 14, -1)]
    assert first["items"][0]["author_name"] == h.user.full_name
    assert first["items"][0]["author_username"] == h.user.username
    assert first["items"][0]["created_at"].endswith("Z")
    assert "password_hash" not in first["items"][0]
    await store.create(
        Comment(
            post_id=h.post.id, user_id=h.user.id, text="New", created_at=date + timedelta(days=1)
        )
    )
    # A deleted boundary is still a valid position; no OFFSET dependence.
    await store.delete(UUID(int=16))
    second = (
        await h.client.get(path, headers=h.headers(), params={"cursor": first["next_cursor"]})
    ).json()
    third = (
        await h.client.get(path, headers=h.headers(), params={"cursor": second["next_cursor"]})
    ).json()
    assert [len(page["items"]) for page in (first, second, third)] == [10, 10, 5]
    ids = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(ids) == len(set(ids)) == 25
    assert third["next_cursor"] is None
    fresh = (await h.client.get(path, headers=h.headers())).json()
    assert fresh["items"][0]["text"] == "New"
    bad = await h.client.get(
        path, headers=h.headers(), params={"cursor": first["next_cursor"] + "x"}
    )
    assert bad.status_code == 422
    other = Post(user_id=h.admin.id, text="Other", moderation_status=ModerationStatus.APPROVED)
    await h.posts.create(other)
    assert (
        await h.client.get(
            f"/api/v1/posts/{other.id}/comments",
            headers=h.headers(),
            params={"cursor": first["next_cursor"]},
        )
    ).status_code == 422


@pytest.mark.parametrize("limit", [0, 51])
async def test_comment_page_limit_is_validated(harness: Harness, limit: int) -> None:
    response = await harness.client.get(
        f"/api/v1/posts/{harness.post.id}/comments",
        headers=harness.headers(),
        params={"limit": limit},
    )
    assert response.status_code == 422


async def test_comment_pages_require_active_login(harness: Harness) -> None:
    h = harness
    path = f"/api/v1/posts/{h.post.id}/comments"
    assert (await h.client.get(path)).status_code == 401
    assert (await h.client.get(path, headers={"Authorization": "Bearer bad"})).status_code == 401
    users = MongoUserRepository(h.resources.mongo_client[get_settings().mongodb_database])
    await users.update_account_status(h.user.id, "suspended")
    assert (await h.client.get(path, headers=h.headers())).status_code == 401


async def test_comments_filter_suspended_missing_authors_and_uncommitted_writes(
    harness: Harness,
) -> None:
    h = harness
    store = repository(h)
    log = MongoOperationLogRepository(h.resources.mongo_client[get_settings().mongodb_database])
    legacy = Comment(post_id=h.post.id, user_id=h.user.id, text="Legacy")
    await store.create(legacy)
    await store.create(Comment(post_id=h.post.id, user_id=uuid4(), text="Missing author"))
    pending = None
    for status in (
        OperationStatus.RUNNING,
        OperationStatus.FAILED,
        OperationStatus.COMPENSATING,
        OperationStatus.COMPLETED,
    ):
        comment = Comment(post_id=h.post.id, user_id=h.moderator.id, text=status.value)
        await store.create(comment)
        operation = OperationContext(
            "problem_05_comment", status=status, metadata={"comment_id": str(comment.id)}
        )
        await log.save(operation)
        if status == OperationStatus.RUNNING:
            pending = operation
    path = f"/api/v1/posts/{h.post.id}/comments"
    page = (await h.client.get(path, headers=h.headers())).json()
    assert {row["text"] for row in page["items"]} == {"Legacy", "completed"}
    assert pending is not None
    pending.status = OperationStatus.COMPLETED
    await log.save(pending)
    page = (await h.client.get(path, headers=h.headers())).json()
    assert {row["text"] for row in page["items"]} == {"Legacy", "running", "completed"}
    users = MongoUserRepository(h.resources.mongo_client[get_settings().mongodb_database])
    await users.update_account_status(h.user.id, "suspended")
    page = (await h.client.get(path, headers=h.headers(h.moderator))).json()
    assert {row["text"] for row in page["items"]} == {"running", "completed"}


async def test_comment_pages_respect_post_moderation_and_author_suspension(
    harness: Harness,
) -> None:
    h = harness
    private = Post(user_id=h.user.id, text="Private", visibility="private")
    await h.posts.create(private)
    private_response = await h.client.get(
        f"/api/v1/posts/{private.id}/comments", headers=h.headers()
    )
    assert private_response.status_code == 404
    await repository(h).create(Comment(post_id=h.post.id, user_id=h.user.id, text="Visible"))
    path = f"/api/v1/posts/{h.post.id}/comments"
    report = await h.report()
    await h.run(await h.decision(report))
    assert (await h.client.get(path, headers=h.headers())).status_code == 404
    reverted = await h.client.post(
        f"/api/v1/moderation/reports/{report}/revert",
        headers=h.headers(h.moderator),
        json={"reason": "Restore comments"},
    )
    assert reverted.status_code == 202
    await h.run(ModerationJob.model_validate(reverted.json()))
    assert len((await h.client.get(path, headers=h.headers())).json()["items"]) == 1
    users = MongoUserRepository(h.resources.mongo_client[get_settings().mongodb_database])
    await users.update_account_status(h.admin.id, "suspended")
    assert (await h.client.get(path, headers=h.headers())).status_code == 404
