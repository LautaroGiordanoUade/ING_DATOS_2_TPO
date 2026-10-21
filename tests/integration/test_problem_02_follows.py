"""P2 against real MongoDB, Neo4j and Redis; isolated records per test."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from app.application.services.follow_job import FollowJob
from app.application.services.follow_processor import FollowProcessor
from app.application.services.publication_processor import PublicationProcessor
from app.application.use_cases.problem_02_follow_user import FollowUserUseCase
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.domain.entities import Post
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.repositories.follows import MongoFollowStore
from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
    MongoPublicationJobs,
)
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.follows import RedisFollowViews
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


@dataclass
class SocialHarness:
    h: Harness
    store: MongoFollowStore
    graph: Neo4jSocialGraphRepository
    views: RedisFollowViews
    service: FollowUserUseCase

    async def run(self, job: FollowJob) -> FollowJob:
        await FollowProcessor(self.store, self.graph, self.views).process(
            await self.store.get(job.operation_id)
        )
        return await self.store.get(job.operation_id)

    async def follow(self, **kwargs: str) -> FollowJob:
        return await self.run(await self.service.follow(self.h.user.id, self.h.admin.id, **kwargs))


@pytest.fixture
async def social(harness: Harness) -> AsyncIterator[SocialHarness]:
    h = harness
    database = h.resources.mongo_client[get_settings().mongodb_database]
    store, graph, views = (
        MongoFollowStore(database),
        Neo4jSocialGraphRepository(h.resources.neo4j),
        RedisFollowViews(h.resources.redis),
    )
    from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository

    service = FollowUserUseCase(MongoUserRepository(database), graph, store, views)
    try:
        yield SocialHarness(h, store, graph, views, service)
    finally:
        async for job in database["follow_jobs"].find({}):
            keys = [key async for key in h.resources.redis.scan_iter(match=f"*{job['_id']}*")]
            if keys:
                await h.resources.redis.delete(*keys)
        async with h.resources.neo4j.session() as session:
            result = await session.run(
                "MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u",
                ids=[str(actor.id) for actor in (h.user, h.moderator, h.admin)],
            )
            await result.consume()


async def test_public_follow_change_feed_and_idempotent_unfollow(social: SocialHarness) -> None:
    h = social.h
    result = await social.follow(key="first")
    assert result.status == "completed" and result.desired == "accepted"
    assert (await social.graph.follow_snapshot(h.user.id, h.admin.id))["relationship"][
        "status"
    ] == "accepted"
    assert (await social.views.counts(h.user.id))["following"] == 1
    assert (await social.views.counts(h.admin.id))["followers"] == 1
    replay = await social.service.follow(h.user.id, h.admin.id, "first")
    assert replay.operation_id == result.operation_id
    await social.follow(key="again")
    assert (await social.views.counts(h.user.id))["following"] == 1
    for _ in range(2):
        result = await social.run(await social.service.unfollow(h.user.id, h.admin.id))
        assert result.status == "completed"
        assert (await social.views.counts(h.admin.id))["followers"] == 0
        assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None


async def test_private_follow_waits_for_owner_approval_and_cancellation(
    social: SocialHarness,
) -> None:
    h = social.h
    await social.store._database["users"].update_one(
        {"_id": str(h.admin.id)}, {"$set": {"account_type": "private"}}
    )
    await h.resources.redis.zrem(f"feed:{h.user.id}", str(h.post.id))
    result = await social.follow()
    assert result.desired == "pending" and result.status == "completed"
    assert await social.service.requests(h.admin.id) == (h.user.id,)
    assert (await social.views.counts(h.admin.id))["followers"] == 0
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None
    result = await social.run(await social.service.approve(h.user.id, h.admin.id))
    assert result.status == "completed" and result.desired == "accepted"
    assert await social.service.requests(h.admin.id) == ()
    assert (await social.views.counts(h.admin.id))["followers"] == 1
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is not None
    await social.run(await social.service.unfollow(h.user.id, h.admin.id))
    await social.follow()
    await social.run(await social.service.unfollow(h.user.id, h.admin.id))
    assert await social.service.requests(h.admin.id) == ()


async def test_new_follow_adds_only_twenty_recent_visible_posts(social: SocialHarness) -> None:
    h = social.h
    await h.resources.redis.zrem(f"feed:{h.user.id}", str(h.post.id))
    posts = [
        Post(user_id=h.admin.id, text=f"recent {i}", moderation_status=ModerationStatus.APPROVED)
        for i in range(25)
    ]
    for post in posts:
        await h.posts.create(post)
        await RedisPublicationFeeds(h.resources.redis, h.admin.id).commit(post.id)
    await social.follow()
    members = await h.resources.redis.zrange(f"feed:{h.user.id}", 0, -1)
    assert len(members) == 20
    other = Post(user_id=h.moderator.id, text="other author")
    await h.posts.create(other)
    await h.resources.redis.zadd(f"feed:{h.user.id}", {str(other.id): 1})
    await social.run(await social.service.unfollow(h.user.id, h.admin.id))
    assert await h.resources.redis.zrange(f"feed:{h.user.id}", 0, -1) == [str(other.id).encode()]


@pytest.mark.parametrize(
    "step", ["neo4j_follow", "redis_follow_counters", "redis_follow_feed", "redis_feed_partial"]
)
@pytest.mark.parametrize("action", ["follow", "unfollow", "approve"])
async def test_failure_compensates_graph_counts_and_exact_feed(
    social: SocialHarness, step: str, action: str
) -> None:
    h = social.h
    if action == "unfollow":
        await social.follow()
    elif action == "approve":
        await social.store._database["users"].update_one(
            {"_id": str(h.admin.id)}, {"$set": {"account_type": "private"}}
        )
        await social.follow()
    before_graph = await social.graph.follow_snapshot(h.user.id, h.admin.id)
    before_feed = await h.resources.redis.zrange(f"feed:{h.user.id}", 0, -1, withscores=True)
    method = getattr(social.service, action)
    job = await method(h.user.id, h.admin.id, fail_at=step)
    result = await social.run(job)
    assert result.status == "compensated", result.error
    assert await social.graph.follow_snapshot(h.user.id, h.admin.id) == before_graph
    assert (
        await h.resources.redis.zrange(f"feed:{h.user.id}", 0, -1, withscores=True) == before_feed
    )
    expected = 1 if action == "unfollow" else 0
    assert (await social.views.counts(h.admin.id))["followers"] == expected


async def test_concurrent_commands_keys_and_participant_exclusion(social: SocialHarness) -> None:
    h = social.h
    jobs = await asyncio.gather(
        *[social.service.follow(h.user.id, h.admin.id, "same-key") for _ in range(10)]
    )
    assert len({job.operation_id for job in jobs}) == 1
    with pytest.raises(ConflictError):
        await social.service.unfollow(h.user.id, h.admin.id, "same-key")
    with pytest.raises(ConflictError):
        await social.service.follow(h.moderator.id, h.admin.id, "different-pair")
    await social.run(jobs[0])
    assert (await social.views.counts(h.admin.id))["followers"] == 1


async def test_authenticated_routes_and_private_operation(social: SocialHarness) -> None:
    h = social.h
    payload = {"user_id": str(h.user.id), "followed_user_id": str(h.admin.id)}
    assert (await h.client.post("/api/v1/problems/2/follow", json=payload)).status_code == 401
    assert (
        await h.client.post("/api/v1/social/follows", json=payload, headers=h.headers(h.moderator))
    ).status_code == 403
    response = await h.client.post("/api/v1/social/follows", json=payload, headers=h.headers())
    assert response.status_code == 202, response.text
    job = FollowJob.model_validate(response.json())
    assert (
        await h.client.get(
            f"/api/v1/social/operations/{job.operation_id}", headers=h.headers(h.moderator)
        )
    ).status_code == 200
    await social.store._database["users"].update_one(
        {"_id": str(h.moderator.id)}, {"$set": {"role": "user"}}
    )
    assert (
        await h.client.get(
            f"/api/v1/social/operations/{job.operation_id}", headers=h.headers(h.moderator)
        )
    ).status_code == 403
    assert (
        await h.client.post("/api/v1/social/follows/approve", json=payload, headers=h.headers())
    ).status_code == 403
    await social.run(job)
    counts = await h.client.get(f"/api/v1/social/counts/{h.admin.id}", headers=h.headers())
    assert counts.status_code == 200 and counts.json()["followers"] == 1


async def test_blocked_and_suspended_users_cannot_follow(social: SocialHarness) -> None:
    h = social.h
    async with h.resources.neo4j.session() as session:
        result = await session.run(
            "MERGE (f:User {id:$f}) MERGE (a:User {id:$a}) MERGE (f)-[:BLOCKS]->(a)",
            f=str(h.user.id),
            a=str(h.admin.id),
        )
        await result.consume()
    assert (await social.follow()).status == "compensated"
    await social.store._database["users"].update_one(
        {"_id": str(h.admin.id)}, {"$set": {"account_status": "suspended"}}
    )
    with pytest.raises(ConflictError):
        await social.service.follow(h.user.id, h.admin.id)


async def test_stale_p1_and_p7_restore_cannot_resurrect_unfollowed_posts(
    social: SocialHarness,
) -> None:
    h = social.h
    await social.follow()
    snapshot = await RedisModerationViews(h.resources.redis).snapshot(h.post.id)
    await social.run(await social.service.unfollow(h.user.id, h.admin.id))
    await RedisPublicationFeeds(h.resources.redis, h.admin.id).stage_batch(
        (h.user.id,), h.post.id, 999
    )
    await RedisModerationViews(h.resources.redis).restore(h.post.id, snapshot)
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None
    assert h.post.id not in await RedisPublicationFeeds(h.resources.redis).visible_ids(h.user.id)


async def test_pending_p1_not_in_original_audience_is_delivered_and_aborted_cleanly(
    social: SocialHarness,
) -> None:
    h = social.h
    jobs = MongoPublicationJobs(social.store._database)
    pending = await jobs.enqueue(
        Post(user_id=h.admin.id, text="in flight", interests=("data",)), "in-flight", None
    )
    await jobs.stage_post(pending)
    pending.followers = []  # P1 read its audience before P2 created the relation.
    await jobs.save(pending)
    await social.follow()
    assert pending.post.id not in await RedisPublicationFeeds(h.resources.redis).visible_ids(
        h.user.id
    )
    await PublicationProcessor(
        jobs, social.graph, RedisPublicationFeeds(h.resources.redis, h.admin.id)
    ).process(pending)
    assert pending.post.id in await RedisPublicationFeeds(h.resources.redis).visible_ids(h.user.id)
    feeds = RedisPublicationFeeds(h.resources.redis, h.admin.id)
    await feeds.abort(pending.post.id)
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(pending.post.id)) is None


async def test_p1_delivery_during_follow_rollback_is_not_lost(social: SocialHarness) -> None:
    h = social.h
    await social.follow()
    job = await social.service.unfollow(h.user.id, h.admin.id)
    job.graph_snapshot = await social.graph.follow_snapshot(h.user.id, h.admin.id)
    job.catalog = await social.store.post_catalog(h.admin.id)
    job.status, job.desired = "running", "none"
    await social.store.save(job)
    job.snapshot = await social.views.begin(job)
    await social.store.save(job)
    new = Post(user_id=h.admin.id, text="concurrent")
    await h.posts.create(new)
    feeds = RedisPublicationFeeds(h.resources.redis, h.admin.id)
    await feeds.stage_batch((h.user.id,), new.id, new.published_at.timestamp())
    await feeds.commit(new.id)
    assert new.id not in await feeds.visible_ids(h.user.id)
    job.status = "compensating"
    await social.store.save(job)
    assert (await social.run(job)).status == "compensated"
    assert new.id in await feeds.visible_ids(h.user.id)
    # Replaying a lost compensation acknowledgement must not erase this delivery.
    await social.views.finish(await social.store.get(job.operation_id), restore=True)
    assert new.id in await feeds.visible_ids(h.user.id)


class ProcessCrash(BaseException):
    pass


async def test_legacy_graph_counts_are_initialized_without_overwriting_newer_values(
    social: SocialHarness,
) -> None:
    h = social.h
    await social.graph.follow(h.user.id, h.admin.id)
    assert (await social.service.counts(h.admin.id))["followers"] == 1
    await social.views.initialize_counts(h.admin.id, {"followers": 0, "following": 0})
    assert (await social.views.counts(h.admin.id))["followers"] == 1


@pytest.mark.parametrize(
    "component,method",
    [
        ("views", "begin"),
        ("graph", "set_follow_state"),
        ("views", "set_counts"),
        ("views", "apply_batch"),
        ("views", "finish"),
    ],
)
async def test_restart_after_effect_before_checkpoint(
    social: SocialHarness, component: str, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = await social.service.follow(social.h.user.id, social.h.admin.id)
    target = getattr(social, component)
    original = getattr(target, method)

    async def crash(*args: Any, **kwargs: Any) -> Any:
        await original(*args, **kwargs)
        raise ProcessCrash()

    with monkeypatch.context() as patch:
        patch.setattr(target, method, crash)
        with pytest.raises(ProcessCrash):
            await FollowProcessor(social.store, social.graph, social.views).process(job)
    # New processor reads only the durable checkpoint, as a restarted consumer does.
    assert (await social.run(job)).status == "completed"
    assert (await social.views.counts(social.h.admin.id))["followers"] == 1
    assert social.h.post.id in await RedisPublicationFeeds(social.h.resources.redis).visible_ids(
        social.h.user.id
    )


async def test_failed_compensation_keeps_ownership_until_explicit_retry(
    social: SocialHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = social.h
    job = await social.service.follow(h.user.id, h.admin.id, fail_at="redis_follow_feed")

    async def unavailable(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("Graph temporarily unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(social.graph, "restore_follow", unavailable)
        result = await social.run(job)
    assert result.status == "failed" and result.active
    assert len(result.failures) == 3
    with pytest.raises(ConflictError):
        await social.service.unfollow(h.user.id, h.admin.id)
    retried = await social.service.retry(job.operation_id)
    assert (await social.run(retried)).status == "compensated"
    assert (await social.views.counts(h.admin.id))["followers"] == 0
    assert (await social.follow()).status == "completed"


async def test_lost_begin_acknowledgement_preserves_original_backup(
    social: SocialHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = social.views.begin
    calls = 0

    async def uncertain(job: FollowJob) -> Any:
        nonlocal calls
        result = await original(job)
        calls += 1
        if calls == 1:
            raise ConnectionError("Redis reply lost after write")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(social.views, "begin", uncertain)
        result = await social.follow(fail_at="redis_follow_feed")
    assert result.status == "compensated" and calls == 2
    assert result.snapshot is not None and result.snapshot.gate is None
    assert str(social.h.post.id) in result.snapshot.feeds


async def test_account_reactivation_respects_later_unfollow(social: SocialHarness) -> None:
    h = social.h
    await social.follow()
    accounts = RedisAccountViews(h.resources.redis)
    snapshot = await accounts.snapshot(h.post.id)
    operation_id = uuid4()
    await accounts.block(h.user.id, operation_id)
    await social.run(await social.service.unfollow(h.user.id, h.admin.id))
    # Both P8 backup paths may contain references captured before the unfollow.
    await accounts.restore_post(h.post.id, snapshot)
    await accounts.unblock(h.user.id, operation_id, restore_presence=False)
    assert await h.resources.redis.zscore(f"feed:{h.user.id}", str(h.post.id)) is None


async def test_registration_supports_private_account_without_role_escalation(
    social: SocialHarness,
) -> None:
    response = await social.h.client.post(
        "/api/v1/users",
        json={
            "username": "private_p2",
            "full_name": "Private account",
            "email": "private@p2.test",
            "password": "private-password-p2",
            "account_type": "private",
            "role": "admin",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["account_type"] == "private"
    assert response.json()["role"] == "user"
