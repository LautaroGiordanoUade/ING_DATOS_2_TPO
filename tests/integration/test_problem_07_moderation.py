"""Real MongoDB/Redis tests, isolated database and UUID keys; no repository substitutes."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.services.moderation_job import ModerationJob
from app.application.services.moderation_processor import ModerationProcessor
from app.application.use_cases.problem_07_moderate_post import ModeratePostUseCase
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.core.lifespan import Resources
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.entities import Post, User
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoPostRepository,
)
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
)
from app.infrastructure.security.password import PasswordHasher
from app.infrastructure.security.tokens import TokenService
from app.main import create_app

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB and Redis"
)
_PASSWORD = "integration-password-07"
_DIGEST = PasswordHasher().hash(_PASSWORD)


@dataclass
class Harness:
    app: FastAPI
    client: httpx.AsyncClient
    resources: Resources
    store: MongoModerationRepository
    views: RedisModerationViews
    posts: MongoPostRepository
    user: User
    moderator: User
    admin: User
    post: Post

    def headers(self, actor: User | None = None) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + TokenService().create_access_token((actor or self.user).id)
        }

    async def report(self, actor: User | None = None) -> UUID:
        response = await self.client.post(
            "/api/v1/moderation/reports",
            headers=self.headers(actor),
            json={"post_id": str(self.post.id), "reason": "spam", "description": "P7 test"},
        )
        assert response.status_code == 201, response.text
        return UUID(response.json()["id"])

    async def decision(self, report_id: UUID, action: str = "hide", **kwargs: Any) -> ModerationJob:
        response = await self.client.post(
            f"/api/v1/moderation/reports/{report_id}/decision",
            headers={**self.headers(self.moderator), **kwargs},
            json={"decision": action, "reason": "Confirmed test"},
        )
        assert response.status_code == 202, response.text
        return ModerationJob.model_validate(response.json())

    async def run(self, job: ModerationJob) -> ModerationJob:
        # Reconstruct repository and processor each time, as after a worker restart.
        store = MongoModerationRepository(
            self.resources.mongo_client[get_settings().mongodb_database]
        )
        current = await store.get_job(job.operation_id)
        assert current is not None
        await ModerationProcessor(store, RedisModerationViews(self.resources.redis)).process(
            current
        )
        result = await store.get_job(job.operation_id)
        assert result is not None
        return result

    async def counts(self) -> dict[str, int]:
        repository = RedisCounterRepository(self.resources.redis)
        return {
            name: (await repository.get_many(name, (self.post.id,)))[self.post.id]
            for name in (POST_REACTIONS, POST_COMMENTS)
        }


@pytest.fixture
async def harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    database_name = "test_p7_" + uuid4().hex
    monkeypatch.setenv("MONGODB_DATABASE", database_name)
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    settings = get_settings()
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    neo4j = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    database = mongo[database_name]
    resources = Resources(mongo, redis, neo4j, MongoOperationLogRepository(database))
    app = create_app()
    app.state.resources = resources
    await ensure_mongo_indexes(database)
    users = MongoUserRepository(database)
    user, moderator, admin = [
        User(
            username="p7_" + role,
            full_name=role,
            email=role + "@p7.test",
            password_hash=_DIGEST,
            role=role,
        )
        for role in ("user", "moderator", "admin")
    ]
    for actor in (user, moderator, admin):
        await users.create(actor)
    posts = MongoPostRepository(database)
    post = Post(
        user_id=admin.id, text="P7 real content", moderation_status=ModerationStatus.APPROVED
    )
    await posts.create(post)
    feed = RedisPublicationFeeds(redis)
    await feed.stage_batch((user.id, moderator.id), post.id, 123.5)
    await feed.commit(post.id)
    counters = RedisCounterRepository(redis)
    await counters.increment(POST_REACTIONS, post.id, 2)
    await counters.increment(POST_COMMENTS, post.id, 3)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield Harness(
                app,
                client,
                resources,
                MongoModerationRepository(database),
                RedisModerationViews(redis),
                posts,
                user,
                moderator,
                admin,
                post,
            )
    finally:
        ids = [str(actor.id) for actor in (user, moderator, admin)]
        ids += [str(doc["_id"]) async for doc in database["posts"].find({})]
        for identifier in ids:
            keys = [key async for key in redis.scan_iter(match=f"*{identifier}*")]
            if keys:
                await redis.delete(*keys)
        assert database_name.startswith("test_p7_")
        await mongo.drop_database(database_name)
        await mongo.close()
        await redis.aclose()
        await neo4j.close()
        get_settings.cache_clear()


async def test_report_persists_and_survives_new_context(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    repository = MongoModerationRepository(
        h.resources.mongo_client[get_settings().mongodb_database]
    )
    report = await repository.report(report_id)
    assert report["resolution_status"] == "pending"
    assert report["reporter_id"] == str(h.user.id)
    assert report["description"] == "P7 test"
    response = await h.client.get(f"/api/v1/moderation/reports/{report_id}", headers=h.headers())
    assert response.status_code == 200
    assert response.json()["id"] == str(report_id)
    assert response.json()["target_type"] == "post"


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"post_id": "invalid", "reason": "spam"}, 422),
        ({"post_id": str(uuid4()), "reason": "invalid"}, 422),
        ({"post_id": str(uuid4()), "reason": "spam"}, 404),
        ({"reason": "spam"}, 422),
    ],
)
async def test_invalid_report(harness: Harness, payload: dict[str, str], status: int) -> None:
    response = await harness.client.post(
        "/api/v1/moderation/reports", json=payload, headers=harness.headers()
    )
    assert response.status_code == status


async def test_duplicate_report_is_conflict(harness: Harness) -> None:
    await harness.report()
    response = await harness.client.post(
        "/api/v1/moderation/reports",
        headers=harness.headers(),
        json={"post_id": str(harness.post.id), "reason": "other"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "credential,expected",
    [
        ("missing", 401),
        ("invalid", 401),
        ("expired", 401),
        ("user", 403),
        ("moderator", 202),
        ("admin", 202),
    ],
)
async def test_roles(
    harness: Harness, credential: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    report_id = await h.report()
    headers: dict[str, str] = {}
    if credential == "expired":
        monkeypatch.setattr("app.infrastructure.security.tokens.time.time", lambda: 0)
        headers = h.headers(h.moderator)
        monkeypatch.undo()
    elif credential == "invalid":
        headers = {"Authorization": "Bearer broken.token"}
    elif credential != "missing":
        headers = h.headers(getattr(h, credential))
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/decision",
        headers=headers,
        json={"decision": "hide", "reason": "test"},
    )
    assert response.status_code == expected


@pytest.mark.parametrize("path", ["/api/v1/moderation/decisions", "/api/v1/problems/7/moderate"])
@pytest.mark.parametrize("role,expected", [("missing", 401), ("user", 403), ("moderator", 403)])
async def test_legacy_routes_cannot_bypass_auth(
    harness: Harness, path: str, role: str, expected: int
) -> None:
    h = harness
    response = await h.client.post(
        path,
        headers={} if role == "missing" else h.headers(getattr(h, role)),
        json={
            "post_id": str(h.post.id),
            "report_id": str(uuid4()),
            "moderator_id": str(h.admin.id),
            "decision": "hide",
        },
    )
    assert response.status_code == expected


async def test_hide_all_reads_counts_audit_snapshot_and_revert(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    job = await h.run(await h.decision(report_id))
    assert job.status == "completed"
    assert job.snapshot is not None
    assert job.snapshot.moderation_status == "approved"
    assert job.snapshot.feeds[f"feed:{h.user.id}"] == 123.5
    assert job.snapshot.counters == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.posts.get(h.post.id) is None
    assert await h.posts.get_many((h.post.id,)) == ()
    assert await h.posts.list_recent_by_user(h.admin.id, 100) == ()
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}
    report = await h.store.report(report_id)
    assert report["resolution_status"] == "approved"
    assert report["moderator_id"] == str(h.moderator.id)
    for path in (f"/api/v1/feeds/{h.user.id}", f"/api/v1/problems/3/feed/{h.user.id}"):
        response = await h.client.get(path)
        assert response.status_code == 200
        assert response.json()["items"] == []
    response = await h.client.get(f"/api/v1/posts/{h.post.id}")
    assert response.status_code == 404
    assert (await h.client.get(f"/api/v1/posts/by-user/{h.admin.id}")).json() == []
    preview = await h.client.get(f"/api/v1/problems/1/feed-preview/{h.user.id}")
    assert preview.json()["post_ids"] == []
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None
    assert (await h.store.history(h.post.id))[0]["moderator_id"] == str(h.moderator.id)
    duplicate = await h.decision(report_id)
    assert duplicate.operation_id == job.operation_id
    assert (await h.run(duplicate)).status == "completed"
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.admin),
        json={"reason": "Allowed"},
    )
    assert response.status_code == 202
    revert = await h.run(ModerationJob.model_validate(response.json()))
    assert revert.status == "completed"
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) == 123.5
    assert (await h.store.report(report_id))["resolution_status"] == "reverted"
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.admin),
        json={"reason": "Allowed"},
    )
    assert (
        await h.run(ModerationJob.model_validate(response.json()))
    ).operation_id == revert.operation_id
    assert await h.resources.redis.zcard(f"feed:{h.user.id}") == 1
    assert len(await h.store.history(h.post.id)) == 2


async def test_reject_has_no_derived_effects(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    assert (await h.run(await h.decision(report_id, "reject"))).status == "completed"
    assert (await h.store.report(report_id))["resolution_status"] == "rejected"
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) == 123.5


@pytest.mark.parametrize("step", ["mongo_hide", "redis_counters", "redis_feed"])
async def test_partial_hide_compensates_real_storages(harness: Harness, step: str) -> None:
    h = harness
    job = await h.run(await h.decision(await h.report(), **{"X-Fail-At-Step": step}))
    assert job.status == "compensated"
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) == 123.5
    assert "Injected failure" in str(job.error)


@pytest.mark.parametrize("method", ["hide", "remove_feeds"])
async def test_transient_retry_and_uncertain_ack(
    harness: Harness, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    original = getattr(h.views, method)
    calls = 0

    async def fail_after_effect(*args: Any) -> None:
        nonlocal calls
        calls += 1
        await original(*args)
        if calls == 1:
            raise TimeoutError("Lost acknowledgement")

    monkeypatch.setattr(h.views, method, fail_after_effect)
    job = await h.decision(await h.report())
    await ModerationProcessor(h.store, h.views).process(job)
    assert job.status == "completed"
    assert calls == 2
    assert len(job.failures) == 1
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}


@pytest.mark.parametrize("error,expected_calls", [(TimeoutError, 3), (ValueError, 1)])
async def test_retry_limit_and_functional_error(
    harness: Harness, error: type[Exception], expected_calls: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    calls = 0

    async def fail(post_id: UUID) -> None:
        nonlocal calls
        calls += 1
        raise error("deliberate failure")

    monkeypatch.setattr(h.views, "hide", fail)
    job = await h.decision(await h.report())
    await ModerationProcessor(h.store, h.views).process(job)
    assert job.status == "compensated"
    assert calls == expected_calls
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}


async def test_failed_compensation_persists_and_explicit_retry_recovers(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    job = await h.decision(await h.report(), **{"X-Fail-At-Step": "redis_feed"})

    async def fail(*args: Any) -> None:
        raise TimeoutError("Redis unavailable during recovery")

    monkeypatch.setattr(h.views, "restore", fail)
    await ModerationProcessor(h.store, h.views).process(job)
    assert job.status == "failed" and job.active
    assert await h.posts.get(h.post.id) is None
    persisted = await h.store.get_job(job.operation_id)
    assert persisted is not None and persisted.resume_phase == "compensating"
    monkeypatch.undo()
    response = await h.client.post(
        f"/api/v1/moderation/operations/{job.operation_id}/retry", headers=h.headers(h.moderator)
    )
    assert response.status_code == 202
    assert (await h.run(ModerationJob.model_validate(response.json()))).status == "compensated"
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}


async def test_two_moderators_conflicting_decisions(harness: Harness) -> None:
    h = harness
    report_id = await h.report()

    async def request(action: str) -> httpx.Response:
        return await h.client.post(
            f"/api/v1/moderation/reports/{report_id}/decision",
            headers=h.headers(h.moderator if action == "hide" else h.admin),
            json={"decision": action, "reason": "Concurrent"},
        )

    responses = await asyncio.gather(request("hide"), request("reject"))
    assert sorted(response.status_code for response in responses) == [202, 409]
    accepted = next(response for response in responses if response.status_code == 202)
    job = await h.run(ModerationJob.model_validate(accepted.json()))
    assert job.status == "completed"
    assert len(await h.store.history(h.post.id)) == 1


async def test_two_reports_same_post_reserve_one_active_operation(harness: Harness) -> None:
    h = harness
    first, second = await h.report(), await h.report(h.admin)
    service = ModeratePostUseCase(h.store, h.views)
    results = await asyncio.gather(
        *[
            service.moderate_post(report, h.post.id, h.moderator.id, "hide")
            for report in (first, second)
        ],
        return_exceptions=True,
    )
    assert sum(isinstance(result, ModerationJob) for result in results) == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    job = next(result for result in results if isinstance(result, ModerationJob))
    await h.run(job)
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}


async def test_duplicate_concurrent_requests_and_reverts(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    jobs = await asyncio.gather(h.decision(report_id), h.decision(report_id))
    assert jobs[0].operation_id == jobs[1].operation_id
    assert len(await h.store.pending()) == 1
    await h.run(jobs[0])

    async def revert() -> httpx.Response:
        return await h.client.post(
            f"/api/v1/moderation/reports/{report_id}/revert",
            headers=h.headers(h.moderator),
            json={"reason": "revert"},
        )

    responses = await asyncio.gather(revert(), revert())
    assert [r.status_code for r in responses] == [202, 202]
    assert responses[0].json()["operation_id"] == responses[1].json()["operation_id"]
    await h.run(ModerationJob.model_validate(responses[0].json()))
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.resources.redis.zcard(f"feed:{h.user.id}") == 1


async def test_revert_while_hide_pending_is_conflict(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    await h.decision(report_id)
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.moderator),
        json={"reason": "Too early"},
    )
    assert response.status_code == 409


async def test_inflight_counter_changes_are_preserved_while_hidden(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    await h.run(await h.decision(report_id))
    counters = RedisCounterRepository(h.resources.redis)
    await counters.increment(POST_REACTIONS, h.post.id, 1)
    await counters.increment(POST_COMMENTS, h.post.id, -1)
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.moderator),
        json={"reason": "Restore"},
    )
    await h.run(ModerationJob.model_validate(response.json()))
    assert await h.counts() == {POST_REACTIONS: 3, POST_COMMENTS: 2}


@pytest.mark.parametrize("kind", ["reaction", "comment"])
async def test_hidden_post_rejects_interactions(harness: Harness, kind: str) -> None:
    h = harness
    await h.run(await h.decision(await h.report()))
    payload = {
        "post_id": str(h.post.id),
        "user_id": str(h.user.id),
        **({"kind": "like"} if kind == "reaction" else {"text": "comment"}),
    }
    response = await h.client.post(f"/api/v1/problems/5/{kind}", json=payload)
    assert response.status_code == 404


async def test_not_in_feed_before_hide_is_not_added_on_revert(harness: Harness) -> None:
    h = harness
    await h.resources.redis.zrem(f"feed:{h.user.id}", str(h.post.id))
    report_id = await h.report()
    await h.run(await h.decision(report_id))
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.moderator),
        json={"reason": "Restore"},
    )
    await h.run(ModerationJob.model_validate(response.json()))
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None


async def test_login_and_role_loaded_server_side(harness: Harness) -> None:
    h = harness
    response = await h.client.post(
        "/api/v1/users/login", json={"username": h.moderator.username, "password": _PASSWORD}
    )
    assert response.status_code == 200
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert (await h.client.get("/api/v1/moderation/reports", headers=headers)).status_code == 200
    database = h.resources.mongo_client[get_settings().mongodb_database]
    await database["users"].update_one({"_id": str(h.moderator.id)}, {"$set": {"role": "user"}})
    assert (await h.client.get("/api/v1/moderation/reports", headers=headers)).status_code == 403
    response = await h.client.post(
        "/api/v1/users/login", json={"username": h.moderator.username, "password": "wrong"}
    )
    assert response.status_code == 401


async def test_read_report_not_owned_is_forbidden(harness: Harness) -> None:
    h = harness
    report_id = await h.report(h.admin)
    response = await h.client.get(f"/api/v1/moderation/reports/{report_id}", headers=h.headers())
    assert response.status_code == 403


async def test_queues_and_inspection_are_role_protected(harness: Harness) -> None:
    h = harness
    for path in (
        "/api/v1/moderation/reports",
        f"/api/v1/moderation/posts/{h.post.id}/state",
        f"/api/v1/moderation/history/{h.post.id}",
    ):
        assert (await h.client.get(path)).status_code == 401
        assert (await h.client.get(path, headers=h.headers())).status_code == 403
        assert (await h.client.get(path, headers=h.headers(h.moderator))).status_code == 200


async def test_openapi_has_security_examples_and_recovery_routes(harness: Harness) -> None:
    schema = (await harness.client.get("/openapi.json")).json()
    decision = schema["paths"]["/api/v1/moderation/reports/{report_id}/decision"]["post"]
    assert decision["security"] == [{"HTTPBearer": []}]
    assert "202" in decision["responses"] and "403" in decision["responses"]
    assert schema["components"]["schemas"]["ReportCreate"]["examples"][0]["reason"] == "spam"


class ProcessCrash(BaseException):
    """Simulate termination outside normal exception/compensation handling."""


@pytest.mark.parametrize("method", ["hide", "remove_feeds"])
async def test_crash_after_redis_effect_before_checkpoint_resumes(
    harness: Harness, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    original = getattr(h.views, method)

    async def crash(*args: Any) -> None:
        await original(*args)
        raise ProcessCrash()

    monkeypatch.setattr(h.views, method, crash)
    job = await h.decision(await h.report())
    with pytest.raises(ProcessCrash):
        await ModerationProcessor(h.store, h.views).process(job)
    assert await h.posts.get(h.post.id) is None
    recovered = await h.run(job)
    assert recovered.status == "completed"
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}
    assert len(await h.store.history(h.post.id)) == 1


async def test_crash_after_commit_decision_replays_audit_without_rollback(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    original = h.store.finalize

    async def crash(job: ModerationJob) -> None:
        await original(job)
        raise ProcessCrash()

    monkeypatch.setattr(h.store, "finalize", crash)
    job = await h.decision(await h.report())
    with pytest.raises(ProcessCrash):
        await ModerationProcessor(h.store, h.views).process(job)
    persisted = await h.store.get_job(job.operation_id)
    assert persisted is not None and persisted.status == "committing"
    assert (await h.run(job)).status == "completed"
    assert await h.posts.get(h.post.id) is None
    assert len(await h.store.history(h.post.id)) == 1


async def test_compensation_crash_after_restore_is_idempotent(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    original = h.views.restore

    async def crash(*args: Any) -> None:
        await original(*args)
        raise ProcessCrash()

    monkeypatch.setattr(h.views, "restore", crash)
    job = await h.decision(await h.report(), **{"X-Fail-At-Step": "redis_feed"})
    with pytest.raises(ProcessCrash):
        await ModerationProcessor(h.store, h.views).process(job)
    assert (await h.run(job)).status == "compensated"
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}
    assert await h.resources.redis.zcard(f"feed:{h.user.id}") == 1


@pytest.mark.parametrize("step", ["redis_restore", "mongo_restore"])
async def test_partial_revert_is_compensated_then_can_retry(harness: Harness, step: str) -> None:
    h = harness
    report_id = await h.report()
    await h.run(await h.decision(report_id))
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers={**h.headers(h.moderator), "X-Fail-At-Step": step},
        json={"reason": "Restore"},
    )
    job = await h.run(ModerationJob.model_validate(response.json()))
    assert job.status == "compensated"
    assert await h.posts.get(h.post.id) is None
    assert await h.counts() == {POST_REACTIONS: 0, POST_COMMENTS: 0}
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None
    assert (await h.store.report(report_id))["resolution_status"] == "approved"
    response = await h.client.post(
        f"/api/v1/moderation/operations/{job.operation_id}/retry", headers=h.headers(h.admin)
    )
    assert response.status_code == 202
    assert (await h.run(ModerationJob.model_validate(response.json()))).status == "completed"
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}


async def test_two_retries_reserve_once(harness: Harness) -> None:
    h = harness
    job = await h.run(await h.decision(await h.report(), **{"X-Fail-At-Step": "redis_feed"}))

    async def retry() -> httpx.Response:
        return await h.client.post(
            f"/api/v1/moderation/operations/{job.operation_id}/retry",
            headers=h.headers(h.moderator),
        )

    responses = await asyncio.gather(retry(), retry())
    assert sorted(response.status_code for response in responses) == [202, 409]
    assert (await h.run(job)).status == "completed"


async def test_hide_replay_during_revert_does_not_hide_again(harness: Harness) -> None:
    h = harness
    report_id = await h.report()
    hide = await h.run(await h.decision(report_id))
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers=h.headers(h.moderator),
        json={"reason": "Restore"},
    )
    assert response.status_code == 202
    replay = await h.decision(report_id)
    assert replay.operation_id == hide.operation_id and replay.status == "completed"
    await h.run(ModerationJob.model_validate(response.json()))
    await h.run(replay)
    assert await h.posts.get(h.post.id) is not None
    assert await h.counts() == {POST_REACTIONS: 2, POST_COMMENTS: 3}


@pytest.mark.parametrize("action", ["revert", "conflicting", "wrong_post", "missing"])
async def test_invalid_decision_transitions(harness: Harness, action: str) -> None:
    h = harness
    report_id = await h.report()
    if action == "revert":
        response = await h.client.post(
            f"/api/v1/moderation/reports/{report_id}/revert",
            headers=h.headers(h.moderator),
            json={"reason": "never hidden"},
        )
        assert response.status_code == 409
    elif action == "conflicting":
        await h.run(await h.decision(report_id, "reject"))
        response = await h.client.post(
            f"/api/v1/moderation/reports/{report_id}/decision",
            headers=h.headers(h.moderator),
            json={"decision": "hide", "reason": "different"},
        )
        assert response.status_code == 409
    elif action == "wrong_post":
        response = await h.client.post(
            "/api/v1/problems/7/moderate",
            headers=h.headers(h.moderator),
            json={
                "report_id": str(report_id),
                "post_id": str(uuid4()),
                "moderator_id": str(h.moderator.id),
                "decision": "hide",
            },
        )
        assert response.status_code == 409
    else:
        response = await h.client.post(
            f"/api/v1/moderation/reports/{uuid4()}/decision",
            headers=h.headers(h.moderator),
            json={"decision": "hide", "reason": "missing"},
        )
        assert response.status_code == 404


async def test_demo_mode_cannot_bypass_real_moderation(harness: Harness) -> None:
    h = harness
    get_settings().app_demo_mode = True
    before = await h.client.get(f"/api/v1/problems/8/trace/{h.admin.id}")
    assert [post["id"] for post in before.json()["recent_posts"]] == [str(h.post.id)]
    report_id = await h.report()
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/decision",
        headers=h.headers(),
        json={"decision": "hide", "reason": "test"},
    )
    assert response.status_code == 403
    await h.run(await h.decision(report_id))
    assert (await h.client.get(f"/api/v1/feeds/{h.user.id}")).json()["items"] == []
    assert (await h.client.get(f"/api/v1/problems/3/feed/{h.user.id}")).json()["items"] == []

    after = await h.client.get(f"/api/v1/problems/8/trace/{h.admin.id}")
    assert after.json()["recent_posts"] == []


async def test_publication_commit_does_not_override_moderation_gate(harness: Harness) -> None:
    h = harness
    await h.run(await h.decision(await h.report()))
    await RedisPublicationFeeds(h.resources.redis).commit(h.post.id)
    assert await RedisPublicationFeeds(h.resources.redis).visible_ids(h.user.id) == ()


async def test_pending_publication_cannot_be_reported(harness: Harness) -> None:
    h = harness
    database = h.resources.mongo_client[get_settings().mongodb_database]
    await database["posts"].update_one(
        {"_id": str(h.post.id)}, {"$set": {"publication_state": "pending"}}
    )
    response = await h.client.post(
        "/api/v1/moderation/reports",
        headers=h.headers(),
        json={"post_id": str(h.post.id), "reason": "spam"},
    )
    assert response.status_code == 404


async def test_mongo_gate_prevents_feed_leak_before_redis_update(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness
    original = h.views.hide

    async def check(post_id: UUID) -> None:
        assert await h.resources.redis.get(f"moderation:{post_id}:hidden") is None
        for path in (f"/api/v1/feeds/{h.user.id}", f"/api/v1/problems/1/feed-preview/{h.user.id}"):
            response = await h.client.get(path)
            assert response.json().get("items", response.json().get("post_ids")) == []
        await original(post_id)

    monkeypatch.setattr(h.views, "hide", check)
    job = await h.decision(await h.report())
    await ModerationProcessor(h.store, h.views).process(job)
    assert job.status == "completed"


async def test_reject_does_not_depend_on_redis(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = harness

    async def unavailable(*args: Any) -> None:
        raise TimeoutError("Redis unavailable")

    monkeypatch.setattr(h.views, "snapshot", unavailable)
    job = await h.decision(await h.report(), "reject")
    await ModerationProcessor(h.store, h.views).process(job)
    assert job.status == "completed"
    assert (await h.store.report(job.report_id))["resolution_status"] == "rejected"
