"""P8 uses real MongoDB, Neo4j and Redis, isolated records and shared P7 fixtures."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.account_job import AccountJob
from app.application.services.account_processor import AccountProcessor
from app.application.services.moderation_job import ModerationJob
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore
from app.infrastructure.persistence.mongodb.repositories.messaging_repositories import (
    MongoConversationRepository,
)
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from tests.integration.support import _PASSWORD, Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


@pytest.fixture
async def account(harness: Harness) -> AsyncIterator[Harness]:
    h = harness
    database = h.resources.mongo_client[get_settings().mongodb_database]
    await database["posts"].update_one(
        {"_id": str(h.post.id)}, {"$set": {"user_id": str(h.user.id)}}
    )
    h.post.user_id = h.user.id
    await database["conversations"].insert_one(
        {
            "_id": str(uuid4()),
            "participant_ids": [str(h.user.id), str(h.moderator.id)],
            "created_at": datetime.now(UTC),
        }
    )
    ids = [str(actor.id) for actor in (h.user, h.moderator, h.admin)]
    graph = h.resources.neo4j
    async with graph.session() as session:
        result = await session.run(
            """
            CREATE (u:User {id:$user,account_status:'active'}),
                   (m:User {id:$mod,account_status:'active'}),
                   (a:User {id:$admin,account_status:'active'}),
                   (m)-[:FOLLOWS {status:'accepted'}]->(a),
                   (a)-[:FOLLOWS {status:'accepted'}]->(u),
                   (u)-[:BLOCKS]->(m)
        """,
            user=ids[0],
            mod=ids[1],
            admin=ids[2],
        )
        await result.consume()
    # Remove the block for recommendations; trace still has real FOLLOWS edges.
    async with graph.session() as session:
        result = await session.run("MATCH (u:User {id:$id})-[r:BLOCKS]->() DELETE r", id=ids[0])
        await result.consume()
    await RedisAccountViews(h.resources.redis).heartbeat(h.user.id)
    try:
        yield h
    finally:
        async with graph.session() as session:
            result = await session.run("MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u", ids=ids)
            await result.consume()


def store(h: Harness) -> MongoAccountStore:
    return MongoAccountStore(h.resources.mongo_client[get_settings().mongodb_database])


def processor(h: Harness) -> AccountProcessor:
    return AccountProcessor(
        store(h),
        Neo4jSocialGraphRepository(h.resources.neo4j),
        RedisAccountViews(h.resources.redis),
    )


async def submit(
    h: Harness, action: str = "suspend", fail: str | None = None, key: str | None = None
) -> AccountJob:
    headers = h.headers(h.moderator)
    if fail:
        headers["X-Fail-At-Step"] = fail
    if key:
        headers["Idempotency-Key"] = key
    response = await h.client.post(
        f"/api/v1/accounts/{h.user.id}/{action}",
        headers=headers,
        json={"reason": "P8 integration decision"},
    )
    assert response.status_code == 202, response.text
    return AccountJob.model_validate(response.json())


async def run(h: Harness, job: AccountJob) -> AccountJob:
    # Recover from Mongo in a freshly constructed context on every execution.
    current = await store(h).get(job.operation_id)
    await processor(h).process(current)
    return await store(h).get(job.operation_id)


async def test_suspend_all_three_engines_and_private_trace(account: Harness) -> None:
    h = account
    before = await h.client.get(f"/api/v1/accounts/{h.user.id}/trace", headers=h.headers())
    assert before.status_code == 200
    assert before.json()["presence"] is True
    assert before.json()["relationships"]["followers"] == [str(h.admin.id)]
    assert len(before.json()["active_conversations"]) == 1
    assert "password_hash" not in before.text and "email" not in before.json()["profile"]
    suggestions = await h.client.get(f"/api/v1/problems/4/recommendations/{h.moderator.id}")
    assert str(h.user.id) in suggestions.json()
    job = await run(h, await submit(h))
    assert job.status == "completed"
    assert (await store(h).user(h.user.id)).account_status == "suspended"
    graph = await Neo4jSocialGraphRepository(h.resources.neo4j).account_snapshot(h.user.id)
    assert graph["account_status"] == "suspended"
    assert await h.resources.redis.exists(f"presence:{h.user.id}") == 0
    assert await h.resources.redis.zcard(f"feed:{h.user.id}") == 0
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) is None
    assert await h.counts() == {"post_reactions": 0, "post_comments": 0}
    for path in (f"/api/v1/posts/{h.post.id}", f"/api/v1/users/{h.user.id}"):
        assert (await h.client.get(path)).status_code == 404
    assert (await h.client.get(f"/api/v1/posts/by-user/{h.user.id}")).json() == []
    assert (await h.client.get(f"/api/v1/feeds/{h.moderator.id}")).json()["items"] == []
    assert (await h.client.get(f"/api/v1/problems/4/recommendations/{h.moderator.id}")).json() == []
    assert (
        await h.client.put("/api/v1/accounts/me/presence", headers=h.headers())
    ).status_code == 401
    response = await h.client.get(
        f"/api/v1/problems/8/trace/{h.user.id}", headers=h.headers(h.admin)
    )
    assert response.status_code == 200
    trace = response.json()
    assert trace["profile"]["account_status"] == "suspended"
    assert trace["recent_posts"] == [] and len(trace["post_states"]) == 1
    assert len(trace["active_conversations"]) == 1
    assert trace["account_history"][0]["actor_id"] == str(h.moderator.id)
    assert trace["presence"] is False


async def test_reactivation_restores_feed_counts_but_not_tokens_or_presence(
    account: Harness,
) -> None:
    h = account
    old_token = h.headers()
    await run(h, await submit(h, key="suspend-1"))
    reactivations = await asyncio.gather(
        submit(h, "reactivate", key="restore-1"), submit(h, "reactivate", key="restore-1")
    )
    assert reactivations[0].operation_id == reactivations[1].operation_id
    job = await run(h, reactivations[0])
    await run(h, reactivations[1])
    assert job.status == "completed"
    assert (await store(h).user(h.user.id)).account_status == "active"
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) == 123.5
    assert await h.resources.redis.zcard(f"feed:{h.user.id}") == 1
    assert await h.counts() == {"post_reactions": 2, "post_comments": 3}
    assert not await RedisAccountViews(h.resources.redis).presence(h.user.id)
    assert (
        await h.client.put("/api/v1/accounts/me/presence", headers=old_token)
    ).status_code == 401
    login = await h.client.post(
        "/api/v1/users/login", json={"username": h.user.username, "password": _PASSWORD}
    )
    assert login.status_code == 200
    fresh = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert (await h.client.put("/api/v1/accounts/me/presence", headers=fresh)).status_code == 204
    assert await RedisAccountViews(h.resources.redis).presence(h.user.id)
    assert len(await store(h).history(h.user.id)) == 2


@pytest.mark.parametrize(
    "role,expected",
    [
        ("missing", 401),
        ("invalid", 401),
        ("expired", 401),
        ("user", 403),
        ("moderator", 202),
        ("admin", 202),
    ],
)
async def test_authorization(
    account: Harness, role: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    if role == "missing":
        headers = {}
    elif role == "invalid":
        headers = {"Authorization": "Bearer invalid.token"}
    elif role == "expired":
        with monkeypatch.context() as patch:
            patch.setattr("app.infrastructure.security.tokens.time.time", lambda: 0)
            headers = h.headers(h.moderator)
    else:
        headers = h.headers(getattr(h, role))
    response = await h.client.post(
        f"/api/v1/accounts/{h.user.id}/suspend", headers=headers, json={"reason": "test"}
    )
    assert response.status_code == expected


@pytest.mark.parametrize("path", ["/api/v1/problems/8/suspend", "/api/v1/accounts/USER/suspend"])
async def test_demo_never_bypasses_roles(account: Harness, path: str) -> None:
    h = account
    get_settings().app_demo_mode = True
    response = await h.client.post(
        path.replace("USER", str(h.user.id)),
        headers=h.headers(),
        json={"user_id": str(h.user.id), "reason": "test"}
        if "problems" in path
        else {"reason": "test"},
    )
    assert response.status_code == 403

    if "problems" in path:
        accepted = await h.client.post(
            path,
            headers=h.headers(h.moderator),
            json={"user_id": str(h.user.id), "reason": "legacy real job"},
        )
        assert accepted.status_code == 204
        assert accepted.headers["Operation-Id"]
        assert accepted.headers["Location"].endswith(accepted.headers["Operation-Id"])


@pytest.mark.parametrize(
    "case,expected",
    [
        ("missing", 404),
        ("blank", 422),
        ("too_long", 422),
        ("self", 409),
        ("reactivate_active", 409),
        ("invalid_key", 422),
        ("invalid_step", 422),
    ],
)
async def test_invalid_transitions(account: Harness, case: str, expected: int) -> None:
    h = account
    path = f"/api/v1/accounts/{h.user.id}/suspend"
    headers = h.headers(h.moderator)
    payload = {"reason": "test"}
    if case == "missing":
        path = f"/api/v1/accounts/{uuid4()}/suspend"
    if case == "blank":
        payload["reason"] = "  "
    if case == "too_long":
        payload["reason"] = "x" * 1001
    if case == "self":
        path = f"/api/v1/accounts/{h.moderator.id}/suspend"
    if case == "reactivate_active":
        path = f"/api/v1/accounts/{h.user.id}/reactivate"
    if case == "invalid_key":
        headers["Idempotency-Key"] = "x" * 201
    if case == "invalid_step":
        headers["X-Fail-At-Step"] = "unknown"
    response = await h.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected


@pytest.mark.parametrize(
    "step", ["mongo_suspend", "redis_close_presence", "neo4j_suspend", "redis_remove_posts"]
)
async def test_partial_suspension_compensates_all_engines(account: Harness, step: str) -> None:
    h = account
    job = await run(h, await submit(h, fail=step))
    assert job.status == "compensated" and job.error
    assert (await store(h).user(h.user.id)).account_status == "active"
    assert (await Neo4jSocialGraphRepository(h.resources.neo4j).account_snapshot(h.user.id))[
        "account_status"
    ] == "active"
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) == 123.5
    assert await h.counts() == {"post_reactions": 2, "post_comments": 3}
    assert await RedisAccountViews(h.resources.redis).presence(h.user.id)


@pytest.mark.parametrize(
    "step", ["redis_restore_posts", "neo4j_reactivate", "redis_reactivate", "mongo_reactivate"]
)
async def test_partial_reactivation_returns_to_suspended(account: Harness, step: str) -> None:
    h = account
    await run(h, await submit(h))
    job = await run(h, await submit(h, "reactivate", fail=step))
    assert job.status == "compensated"
    assert (await store(h).user(h.user.id)).account_status == "suspended"
    assert not await RedisAccountViews(h.resources.redis).presence(h.user.id)
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) is None
    assert await h.counts() == {"post_reactions": 0, "post_comments": 0}


@pytest.mark.parametrize("key", [None, "same-request"])
async def test_simultaneous_duplicate_suspend(account: Harness, key: str | None) -> None:
    h = account
    jobs = await asyncio.gather(submit(h, key=key), submit(h, key=key))
    assert jobs[0].operation_id == jobs[1].operation_id
    await run(h, jobs[0])
    await run(h, jobs[1])
    assert (await store(h).user(h.user.id)).auth_version == 1
    assert len(await store(h).history(h.user.id)) == 1
    assert await h.counts() == {"post_reactions": 0, "post_comments": 0}


async def test_conflicting_payload_rejected(account: Harness) -> None:
    h = account
    await submit(h, key="key")
    response = await h.client.post(
        f"/api/v1/accounts/{h.user.id}/suspend",
        headers={**h.headers(h.admin), "Idempotency-Key": "key"},
        json={"reason": "different"},
    )
    assert response.status_code == 409


async def test_reactivate_while_suspend_pending_is_conflict(account: Harness) -> None:
    h = account
    await submit(h)
    response = await h.client.post(
        f"/api/v1/accounts/{h.user.id}/reactivate",
        headers=h.headers(h.admin),
        json={"reason": "early"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize("method", ["block", "hide_post"])
async def test_transient_uncertain_ack_retries_without_duplicate_effects(
    account: Harness, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    views = RedisAccountViews(h.resources.redis)
    original = getattr(views, method)
    calls = 0

    async def flaky(*args: Any) -> None:
        nonlocal calls
        calls += 1
        await original(*args)
        if calls == 1:
            raise TimeoutError("ack lost")

    monkeypatch.setattr(views, method, flaky)
    job = await submit(h)
    await AccountProcessor(store(h), Neo4jSocialGraphRepository(h.resources.neo4j), views).process(
        job
    )
    assert job.status == "completed" and calls == 2
    assert len(job.failures) == 1
    assert (await store(h).user(h.user.id)).auth_version == 1


@pytest.mark.parametrize("error,attempts", [(TimeoutError, 3), (ValueError, 1)])
async def test_retry_limits_and_functional_failures(
    account: Harness, error: type[Exception], attempts: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    views = RedisAccountViews(h.resources.redis)
    calls = 0

    async def fail(*args: Any) -> None:
        nonlocal calls
        calls += 1
        raise error("test")

    monkeypatch.setattr(views, "block", fail)
    job = await submit(h)
    await AccountProcessor(store(h), Neo4jSocialGraphRepository(h.resources.neo4j), views).process(
        job
    )
    assert calls == attempts and job.status == "compensated"
    assert (await store(h).user(h.user.id)).account_status == "active"


async def test_failed_compensation_persists_and_retry_recovers(
    account: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    views = RedisAccountViews(h.resources.redis)

    async def unavailable(*args: Any) -> None:
        raise TimeoutError("recovery offline")

    monkeypatch.setattr(views, "unblock", unavailable)
    job = await submit(h, fail="redis_remove_posts")
    await AccountProcessor(store(h), Neo4jSocialGraphRepository(h.resources.neo4j), views).process(
        job
    )
    assert job.status == "failed" and job.active
    responses = await asyncio.gather(
        *[
            h.client.post(
                f"/api/v1/accounts/operations/{job.operation_id}/retry", headers=h.headers(h.admin)
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [202, 409]
    assert (await run(h, job)).status == "compensated"
    assert (await store(h).user(h.user.id)).account_status == "active"


class Crash(BaseException):
    pass


@pytest.mark.parametrize("method", ["block", "hide_post"])
async def test_restart_after_effect_before_checkpoint(
    account: Harness, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    views = RedisAccountViews(h.resources.redis)
    original = getattr(views, method)

    async def crash(*args: Any) -> None:
        await original(*args)
        raise Crash()

    monkeypatch.setattr(views, method, crash)
    job = await submit(h)
    with pytest.raises(Crash):
        await AccountProcessor(
            store(h), Neo4jSocialGraphRepository(h.resources.neo4j), views
        ).process(job)
    assert (await run(h, job)).status == "completed"
    assert (await store(h).user(h.user.id)).auth_version == 1


async def test_restart_after_audit_upsert_does_not_duplicate(
    account: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    repository = store(h)
    original = repository.finalize

    async def crash(job: AccountJob) -> None:
        await original(job)
        raise Crash()

    monkeypatch.setattr(repository, "finalize", crash)
    job = await submit(h)
    with pytest.raises(Crash):
        await AccountProcessor(
            repository,
            Neo4jSocialGraphRepository(h.resources.neo4j),
            RedisAccountViews(h.resources.redis),
        ).process(job)
    assert (await run(h, job)).status == "completed"
    assert len(await store(h).history(h.user.id)) == 1


@pytest.mark.parametrize("revert_while_suspended", [False, True])
async def test_p7_and_p8_gates_compose_without_resurrecting_content(
    account: Harness, revert_while_suspended: bool
) -> None:
    h = account
    report_id = await h.report(h.admin)
    hide = await h.run(await h.decision(report_id))
    assert hide.status == "completed"
    await run(h, await submit(h))
    if revert_while_suspended:
        response = await h.client.post(
            f"/api/v1/moderation/reports/{report_id}/revert",
            headers=h.headers(h.admin),
            json={"reason": "P7 allowed"},
        )
        assert response.status_code == 202
        await h.run(ModerationJob.model_validate(response.json()))
    await run(h, await submit(h, "reactivate"))
    detail = await h.client.get(f"/api/v1/posts/{h.post.id}")
    assert detail.status_code == (200 if revert_while_suspended else 404)
    assert await h.counts() == (
        {"post_reactions": 2, "post_comments": 3}
        if revert_while_suspended
        else {"post_reactions": 0, "post_comments": 0}
    )
    score = await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id))
    assert score == (123.5 if revert_while_suspended else None)


async def test_moderate_during_suspension_then_reactivate_keeps_hidden(account: Harness) -> None:
    h = account
    report_id = await h.report(h.admin)
    await run(h, await submit(h))
    await h.run(await h.decision(report_id))
    await run(h, await submit(h, "reactivate"))
    assert (await h.client.get(f"/api/v1/posts/{h.post.id}")).status_code == 404
    assert await h.counts() == {"post_reactions": 0, "post_comments": 0}
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.admin),
        json={"reason": "Allowed again"},
    )
    await h.run(ModerationJob.model_validate(response.json()))
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) == 123.5
    assert await h.counts() == {"post_reactions": 2, "post_comments": 3}


async def test_queued_publication_cannot_restore_suspended_feed(account: Harness) -> None:
    h = account
    await run(h, await submit(h))
    feeds = RedisPublicationFeeds(h.resources.redis, author_id=h.user.id)
    await feeds.stage_batch((h.moderator.id,), h.post.id, 123.5)
    await feeds.commit(h.post.id)
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(h.post.id)) is None
    assert await feeds.visible_ids(h.moderator.id) == ()
    response = await h.client.post(
        "/api/v1/problems/1/publish",
        json={"user_id": str(h.user.id), "text": "not allowed", "interests": ["data"]},
    )
    assert response.status_code == 409


async def test_trace_privacy_and_missing_account(account: Harness) -> None:
    h = account
    assert (await h.client.get(f"/api/v1/accounts/{h.user.id}/trace")).status_code == 401
    assert (
        await h.client.get(f"/api/v1/accounts/{h.admin.id}/trace", headers=h.headers())
    ).status_code == 403
    assert (
        await h.client.get(f"/api/v1/accounts/{uuid4()}/trace", headers=h.headers(h.admin))
    ).status_code == 404


async def test_login_suspended_account_rejected(account: Harness) -> None:
    h = account
    await run(h, await submit(h))
    response = await h.client.post(
        "/api/v1/users/login", json={"username": h.user.username, "password": _PASSWORD}
    )
    assert response.status_code == 401


async def test_old_suspend_replay_does_not_undo_reactivation(account: Harness) -> None:
    h = account
    first = await run(h, await submit(h, key="first"))
    await run(h, await submit(h, "reactivate", key="restore"))
    replay = await submit(h, key="first")
    assert replay.operation_id == first.operation_id and replay.status == "completed"
    assert (await run(h, replay)).status == "completed"
    assert (await store(h).user(h.user.id)).account_status == "active"
    second = await run(h, await submit(h, key="second"))
    assert second.status == "completed" and second.operation_id != first.operation_id
    assert (await store(h).user(h.user.id)).auth_version == 2


async def test_trace_and_suggestions_fail_visibly_on_dependency_outage(
    account: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No fake success/partial trace: an unavailable graph is an explicit error.
    h = account
    from app.api.dependencies.use_cases import get_suspend_trace_use_case
    from app.application.use_cases.problem_08_suspend_and_trace_user import (
        SuspendAndTraceUserUseCase,
    )

    graph = Neo4jSocialGraphRepository(h.resources.neo4j)

    async def unavailable(*args: Any) -> dict[str, object]:
        raise TimeoutError("graph offline")

    monkeypatch.setattr(graph, "trace_relationships", unavailable)
    repository = store(h)
    service = SuspendAndTraceUserUseCase(
        repository,
        graph,
        RedisAccountViews(h.resources.redis),
        h.posts,
        MongoConversationRepository(h.resources.mongo_client[get_settings().mongodb_database]),
    )
    h.app.dependency_overrides[get_suspend_trace_use_case] = lambda: service
    response = await h.client.get(f"/api/v1/accounts/{h.user.id}/trace", headers=h.headers(h.admin))
    assert response.status_code == 503


@pytest.mark.parametrize("action", ["reaction", "comment", "remove"])
async def test_suspended_actor_cannot_use_legacy_interactions(
    account: Harness, action: str
) -> None:
    h = account
    # A different author's post remains visible: rejection must concern the actor.
    from app.domain.entities import Post

    other = Post(user_id=h.admin.id, text="Other active author")
    await h.posts.create(other)
    await run(h, await submit(h))
    payload = {"post_id": str(other.id), "user_id": str(h.user.id)}
    if action == "reaction":
        payload["kind"] = "like"
    if action == "comment":
        payload["text"] = "not allowed"
    response = await h.client.request(
        "DELETE" if action == "remove" else "POST",
        "/api/v1/problems/5/" + ("reaction" if action == "remove" else action),
        json=payload,
    )
    assert response.status_code == 409


async def test_publication_already_in_flight_restored_from_durable_audience(
    account: Harness,
) -> None:
    h = account
    from app.application.services.operation import OperationStatus
    from app.domain.entities import Post
    from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
        MongoPublicationJobs,
    )

    jobs = MongoPublicationJobs(h.resources.mongo_client[get_settings().mongodb_database])
    publication = await jobs.enqueue(
        Post(user_id=h.user.id, text="In-flight P1", interests=("data",)), None, None
    )
    publication.followers = [str(h.moderator.id)]
    await jobs.save(publication)
    await run(h, await submit(h))
    await jobs.stage_post(publication)
    await jobs.activate_post(publication)
    feeds = RedisPublicationFeeds(h.resources.redis, author_id=h.user.id)
    await feeds.stage_batch(
        (h.moderator.id,), publication.post.id, publication.post.published_at.timestamp()
    )
    await feeds.commit(publication.post.id)
    publication.operation.status = OperationStatus.COMPLETED
    await jobs.save(publication)
    assert (
        await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(publication.post.id)) is None
    )
    await run(h, await submit(h, "reactivate"))
    assert (
        await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(publication.post.id))
        == publication.post.published_at.timestamp()
    )
    assert (await h.client.get(f"/api/v1/posts/{publication.post.id}")).status_code == 200


async def test_compensation_removes_only_created_empty_graph_node(account: Harness) -> None:
    h = account
    async with h.resources.neo4j.session() as session:
        result = await session.run("MATCH (u:User {id:$id}) DETACH DELETE u", id=str(h.user.id))
        await result.consume()
    assert not (await Neo4jSocialGraphRepository(h.resources.neo4j).account_snapshot(h.user.id))[
        "exists"
    ]
    job = await run(h, await submit(h, fail="neo4j_suspend"))
    assert job.status == "compensated"
    assert not (await Neo4jSocialGraphRepository(h.resources.neo4j).account_snapshot(h.user.id))[
        "exists"
    ]


async def test_transient_neo4j_ack_retried(
    account: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    graph = Neo4jSocialGraphRepository(h.resources.neo4j)
    original = graph.set_account_status
    calls = 0

    async def flaky(user_id: UUID, status: str) -> None:
        nonlocal calls
        calls += 1
        await original(user_id, status)
        if calls == 1:
            raise TimeoutError("neo4j ack lost")

    monkeypatch.setattr(graph, "set_account_status", flaky)
    job = await submit(h)
    await AccountProcessor(store(h), graph, RedisAccountViews(h.resources.redis)).process(job)
    assert job.status == "completed" and calls == 2
    assert len(job.failures) == 1


async def test_trace_excludes_archived_and_unrelated_conversations(account: Harness) -> None:
    h = account
    database = h.resources.mongo_client[get_settings().mongodb_database]
    await database["conversations"].insert_many(
        [
            {
                "_id": str(uuid4()),
                "participant_ids": [str(h.user.id)],
                "created_at": datetime.now(UTC),
                "archived": True,
            },
            {
                "_id": str(uuid4()),
                "participant_ids": [str(h.admin.id)],
                "created_at": datetime.now(UTC),
            },
        ]
    )
    response = await h.client.get(f"/api/v1/accounts/{h.user.id}/trace", headers=h.headers(h.admin))
    assert response.status_code == 200
    assert len(response.json()["active_conversations"]) == 1


async def test_expired_presence_not_resurrected_on_compensation(account: Harness) -> None:
    h = account
    await h.resources.redis.delete(f"presence:{h.user.id}")
    job = await run(h, await submit(h, fail="redis_remove_posts"))
    assert job.status == "compensated"
    assert not await RedisAccountViews(h.resources.redis).presence(h.user.id)


async def test_retry_completed_operation_is_conflict(account: Harness) -> None:
    h = account
    job = await run(h, await submit(h))
    response = await h.client.post(
        f"/api/v1/accounts/operations/{job.operation_id}/retry", headers=h.headers(h.admin)
    )
    assert response.status_code == 409


async def test_suggestions_do_not_traverse_suspended_intermediate(account: Harness) -> None:
    h = account
    response = await h.client.get(f"/api/v1/problems/4/recommendations/{h.moderator.id}")
    assert str(h.user.id) in response.json()
    response = await h.client.post(
        f"/api/v1/accounts/{h.admin.id}/suspend",
        headers=h.headers(h.moderator),
        json={"reason": "Intermediate suspended"},
    )
    assert response.status_code == 202
    await run(h, AccountJob.model_validate(response.json()))
    assert (await h.client.get(f"/api/v1/problems/4/recommendations/{h.moderator.id}")).json() == []


async def test_publication_delivered_during_reactivation_cutover_is_not_lost(
    account: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = account
    await run(h, await submit(h))
    views = RedisAccountViews(h.resources.redis)
    original = views.unblock
    post_id = uuid4()
    from app.domain.entities import Post

    await h.posts.create(Post(id=post_id, user_id=h.user.id, text="Concurrent P1 cutover"))
    feeds = RedisPublicationFeeds(h.resources.redis, author_id=h.user.id)

    async def cutover(user_id: UUID, operation_id: UUID, restore_presence: bool) -> None:
        # _restore_posts has already scanned. A P1 batch now finishes before gate removal.
        await feeds.stage_batch((h.moderator.id,), post_id, 789.0)
        await feeds.commit(post_id)
        assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(post_id)) is None
        await original(user_id, operation_id, restore_presence)

    monkeypatch.setattr(views, "unblock", cutover)
    job = await submit(h, "reactivate")
    await AccountProcessor(store(h), Neo4jSocialGraphRepository(h.resources.neo4j), views).process(
        job
    )
    assert job.status == "completed"
    assert await h.resources.redis.zscore(f"feed:{h.moderator.id}", str(post_id)) == 789.0
    assert await h.resources.redis.exists(f"account:{h.user.id}:deferred_out") == 0


async def test_deferred_recipient_survives_p7_hide_and_revert(account: Harness) -> None:
    h = account
    from app.application.use_cases.problem_07_moderate_post import ModeratePostUseCase
    from app.domain.entities import Post

    await run(h, await submit(h))
    post = Post(user_id=h.admin.id, text="Deferred to suspended follower")
    await h.posts.create(post)
    feeds = RedisPublicationFeeds(h.resources.redis, author_id=h.admin.id)
    await feeds.stage_batch((h.user.id,), post.id, 456.0)
    await feeds.commit(post.id)
    service = ModeratePostUseCase(h.store, h.views)
    report = await service.report(post.id, h.moderator.id, "spam")
    await h.run(await service.moderate_post(report.id, post.id, h.moderator.id, "hide"))
    await run(h, await submit(h, "reactivate"))
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(post.id)) is None
    revert = await service.reverse_moderation(report.id, post.id, h.moderator.id)
    await h.run(revert)
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(post.id)) == 456.0
