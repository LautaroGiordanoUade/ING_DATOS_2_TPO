"""P3 pagination/ranking/privacy against real MongoDB, Redis and Neo4j."""

import asyncio
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.problem_03_get_feed import GetFeedUseCase
from app.domain.entities import Post
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.personalized_feed import RedisPersonalizedFeed
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
)
from app.infrastructure.security.feed_cursor import FeedCursorCodec
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


@dataclass
class FeedHarness:
    h: Harness
    store: RedisPersonalizedFeed
    graph: Neo4jSocialGraphRepository
    service: GetFeedUseCase

    async def posts(self, count: int, tied: bool = False) -> list[Post]:
        now = datetime.now(UTC) - timedelta(minutes=5)
        posts = [
            Post(
                user_id=self.h.admin.id,
                text=f"P3 {i}",
                published_at=now - timedelta(seconds=0 if tied else i * 60),
                moderation_status=ModerationStatus.APPROVED,
            )
            for i in range(count)
        ]
        if posts:
            await self.h.posts._collection.insert_many([post_to_document(post) for post in posts])
        pipe = self.h.resources.redis.pipeline(transaction=False)
        for post in posts:
            pipe.zadd(f"feed:{self.h.user.id}", {str(post.id): post.published_at.timestamp()})
            pipe.set(f"publication:{post.id}:state", "published")
            pipe.set(f"publication:{post.id}:author", str(post.user_id))
        await pipe.execute()
        return posts

    async def page(self, cursor: str | None = None) -> dict[str, Any]:
        response = await self.h.client.get(
            f"/api/v1/feeds/{self.h.user.id}",
            headers=self.h.headers(),
            params={} if cursor is None else {"cursor": cursor},
        )
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
async def feed(harness: Harness) -> AsyncIterator[FeedHarness]:
    h = harness
    graph = Neo4jSocialGraphRepository(h.resources.neo4j)
    await graph.follow(h.user.id, h.admin.id)
    await h.resources.redis.zrem(f"feed:{h.user.id}", str(h.post.id))
    store = RedisPersonalizedFeed(h.resources.redis)
    service = GetFeedUseCase(store, h.posts, RedisCounterRepository(h.resources.redis), graph)
    try:
        yield FeedHarness(h, store, graph, service)
    finally:
        # Large cases create thousands of posts. Remove their known keys in
        # batches instead of making the shared fixture SCAN Redis for each UUID.
        assert h.posts._database.name.startswith("test_p7_")
        generated = [
            str(doc["_id"])
            async for doc in h.posts._collection.find(
                {"_id": {"$ne": str(h.post.id)}},
                {"_id": 1},
            )
        ]
        for start in range(0, len(generated), 100):
            keys = []
            for identifier in generated[start : start + 100]:
                keys.extend(
                    [
                        f"publication:{identifier}:state",
                        f"publication:{identifier}:author",
                        f"publication:{identifier}:recipients",
                        f"moderation:{identifier}:hidden",
                        f"suspension:{identifier}:hidden",
                        f"post_reactions:{identifier}:count",
                        f"post_comments:{identifier}:count",
                    ]
                )
            await h.resources.redis.delete(*keys)
        if generated:
            await h.posts._collection.delete_many({"_id": {"$in": generated}})
        async for key in h.resources.redis.scan_iter(match="feed-page:*"):
            raw = await cast(Any, h.resources.redis).hget(key, "metadata")
            if raw and str(h.user.id).encode() in raw:
                await h.resources.redis.delete(key)
        async with h.resources.neo4j.session() as session:
            result = await session.run(
                "MATCH (u:User) WHERE u.id IN $ids OR u.qa_p3=$run DETACH DELETE u",
                ids=[str(actor.id) for actor in (h.user, h.moderator, h.admin)],
                run=str(h.user.id),
            )
            await result.consume()


@pytest.mark.parametrize(
    "count,tied", [(0, False), (20, False), (45, False), (205, False), (260, True)]
)
async def test_all_pages_twenty_unique_and_history_across_windows(
    feed: FeedHarness,
    count: int,
    tied: bool,
) -> None:
    posts = await feed.posts(count, tied)
    expected = [
        str(post.id)
        for post in sorted(posts, key=lambda p: (p.published_at, str(p.id)), reverse=True)
    ]
    found: list[str] = []
    cursor = None
    for _ in range(20):
        page = await feed.page(cursor)
        ids = [post["id"] for post in page["items"]]
        assert len(ids) <= 20
        found.extend(ids)
        cursor = page["next_cursor"]
        if cursor is None:
            break
    else:
        pytest.fail("Pagination did not terminate")
    assert found == expected


async def test_activity_boost_is_capped_and_comments_weigh_more(feed: FeedHarness) -> None:
    posts = await feed.posts(80)
    redis = feed.h.resources.redis
    await redis.set(f"post_reactions:{posts[4].id}:count", 10)
    await redis.set(f"post_comments:{posts[6].id}:count", 10)
    await redis.set(f"post_reactions:{posts[69].id}:count", 100000)
    page = await feed.page()
    ids = [post["id"] for post in page["items"]]
    assert ids[0:2] == [str(posts[6].id), str(posts[4].id)]
    assert ids.index(str(posts[69].id)) > ids.index(str(posts[0].id))
    assert page["items"][0]["comment_count"] == 10


async def test_cursor_order_is_frozen_but_counts_are_live(feed: FeedHarness) -> None:
    posts = await feed.posts(45)
    cursor = (await feed.page())["next_cursor"]
    before = await feed.page(cursor)
    await feed.h.resources.redis.set(f"post_reactions:{posts[25].id}:count", 40)
    after = await feed.page(cursor)
    assert [p["id"] for p in after["items"]] == [p["id"] for p in before["items"]]
    item = next(p for p in after["items"] if p["id"] == str(posts[25].id))
    assert item["reaction_count"] == 40
    assert (await feed.page())["items"][0]["id"] == str(posts[25].id)


async def test_new_posts_only_enter_refreshed_navigation(feed: FeedHarness) -> None:
    await feed.posts(45)
    first = await feed.page()
    new = (await feed.posts(1))[0]
    # Ensure a genuinely new publication, newer than the session anchor.
    now = datetime.now(UTC)
    await feed.h.posts._collection.update_one({"_id": str(new.id)}, {"$set": {"published_at": now}})
    await feed.h.resources.redis.zadd(f"feed:{feed.h.user.id}", {str(new.id): now.timestamp()})
    next_page = await feed.page(first["next_cursor"])
    assert str(new.id) not in [p["id"] for p in next_page["items"]]
    assert (await feed.page())["items"][0]["id"] == str(new.id)


async def test_deleted_boundary_and_concurrent_same_cursor_are_stable(feed: FeedHarness) -> None:
    posts = await feed.posts(250, tied=True)
    page = await feed.page()
    for _ in range(9):
        cursor = page["next_cursor"]
        assert cursor
        page = await feed.page(cursor)
    cursor = page["next_cursor"]
    position = FeedCursorCodec().decode(cursor, feed.h.user.id)
    assert position.window == 1 and position.offset == 0
    previous = await feed.store.window(await feed.store.session(position.session_id), 0)
    assert previous is not None
    await feed.h.resources.redis.zrem(f"feed:{feed.h.user.id}", previous.boundary_id)
    results = await asyncio.gather(*(feed.page(cursor) for _ in range(4)))
    assert all(result == results[0] for result in results)
    ordered = sorted(posts, key=lambda p: str(p.id), reverse=True)
    assert [p["id"] for p in results[0]["items"]] == [str(p.id) for p in ordered[200:220]]


@pytest.mark.parametrize(
    "reason", ["moderated", "suspended", "unfollow", "blocked", "pending", "private_post"]
)
async def test_saved_window_never_grants_access_after_state_change(
    feed: FeedHarness, reason: str
) -> None:
    posts = await feed.posts(45)
    cursor = (await feed.page())["next_cursor"]
    h = feed.h
    if reason in ("moderated", "private_post"):
        field, value = (
            ("moderation_status", "hidden") if reason == "moderated" else ("visibility", "private")
        )
        await h.posts._collection.update_many(
            {"_id": {"$in": [str(p.id) for p in posts[20:]]}}, {"$set": {field: value}}
        )
    elif reason == "suspended":
        await h.posts._database["users"].update_one(
            {"_id": str(h.admin.id)}, {"$set": {"account_status": "suspended"}}
        )
    elif reason == "unfollow":
        await feed.graph.unfollow(h.user.id, h.admin.id)
    else:
        async with h.resources.neo4j.session() as session:
            query = (
                "MATCH (u:User {id:$u})-[r:FOLLOWS]->(a:User {id:$a}) SET r.status='pending'"
                if reason == "pending"
                else "MATCH (u:User {id:$u}),(a:User {id:$a}) MERGE (a)-[:BLOCKS]->(u)"
            )
            result = await session.run(query, u=str(h.user.id), a=str(h.admin.id))
            await result.consume()
    assert (await feed.page(cursor))["items"] == []


@pytest.mark.parametrize(
    "gate",
    [
        "processing:operation",
        "none",
        "pending",
        "moderation",
        "suspension",
        "uncommitted",
        "aborted",
    ],
)
async def test_redis_gates_are_checked_on_saved_pages(feed: FeedHarness, gate: str) -> None:
    posts = await feed.posts(45)
    cursor = (await feed.page())["next_cursor"]
    redis = feed.h.resources.redis
    for post in posts[20:]:
        if gate in ("moderation", "suspension"):
            await redis.set(f"{gate}:{post.id}:hidden", "yes")
        elif gate in ("uncommitted", "aborted"):
            await redis.set(
                f"publication:{post.id}:state", "pending" if gate == "uncommitted" else "aborted"
            )
        else:
            await redis.set(f"follow:{feed.h.user.id}:{feed.h.admin.id}:state", gate)
    assert (await feed.page(cursor))["items"] == []


async def test_authentication_cursor_tampering_owner_and_expiration(feed: FeedHarness) -> None:
    await feed.posts(25)
    h = feed.h
    path = f"/api/v1/feeds/{h.user.id}"
    assert (await h.client.get(path)).status_code == 401
    assert (await h.client.get(path, headers=h.headers(h.admin))).status_code == 403
    cursor = (await feed.page())["next_cursor"]
    for token in ("bad", cursor + "x", cursor + "ñ"):
        assert (
            await h.client.get(path, headers=h.headers(), params={"cursor": token})
        ).status_code == 422
    assert (
        await h.client.get(
            f"/api/v1/feeds/{h.moderator.id}",
            headers=h.headers(h.moderator),
            params={"cursor": cursor},
        )
    ).status_code == 422
    position = FeedCursorCodec().decode(cursor, h.user.id)
    position.expires = int(time.time()) - 1
    expired = FeedCursorCodec().encode(position)
    assert (
        await h.client.get(path, headers=h.headers(), params={"cursor": expired})
    ).status_code == 410
    position = FeedCursorCodec().decode(cursor, h.user.id)
    ttl = await h.resources.redis.ttl(feed.store.key(position.session_id))
    assert 0 < ttl <= 900
    await h.resources.redis.delete(feed.store.key(position.session_id))
    assert (
        await h.client.get(path, headers=h.headers(), params={"cursor": cursor})
    ).status_code == 410


async def test_problem_alias_matches_and_empty_feed_is_final(feed: FeedHarness) -> None:
    h = feed.h
    response = await h.client.get(f"/api/v1/problems/3/feed/{h.user.id}", headers=h.headers())
    assert response.status_code == 200 and response.json() == {"items": [], "next_cursor": None}


async def test_thousands_of_follows_use_bounded_candidate_queries(
    feed: FeedHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await feed.posts(250)
    h = feed.h
    async with h.resources.neo4j.session() as session:
        result = await session.run(
            """MATCH (r:User {id:$reader}) UNWIND range(1,2000) AS n
            CREATE (a:User {id:$prefix+toString(n), qa_p3:$reader})
            CREATE (r)-[:FOLLOWS {status:'accepted'}]->(a)""",
            reader=str(h.user.id),
            prefix=str(uuid4()) + ":",
        )
        await result.consume()
    sizes: list[int] = []
    original = h.posts.get_many

    async def measured(ids: tuple[UUID, ...]) -> tuple[Post, ...]:
        sizes.append(len(ids))
        return await original(ids)

    monkeypatch.setattr(h.posts, "get_many", measured)
    started = time.perf_counter()
    page = await feed.service.execute(h.user.id)
    elapsed = (time.perf_counter() - started) * 1000
    assert len(cast(list[Any], page["items"])) == 20
    assert len(sizes) == 3 and max(sizes) <= 200
    print(f"P3: 2001 follows, 250 posts; first page {elapsed:.1f} ms; Mongo batches {sizes}")


async def test_scan_budget_returns_continuation_instead_of_dropping_older_posts(
    feed: FeedHarness,
) -> None:
    posts = await feed.posts(2025)
    await feed.h.posts._collection.update_many(
        {"_id": {"$in": [str(post.id) for post in posts[:2000]]}},
        {"$set": {"moderation_status": "hidden"}},
    )
    page = await feed.page()
    assert page["items"] == [] and page["next_cursor"]
    next_page = await feed.page(page["next_cursor"])
    assert [item["id"] for item in next_page["items"]] == [
        str(post.id) for post in posts[2000:2020]
    ]


@pytest.mark.parametrize("engine", ["mongo", "redis", "neo4j"])
async def test_dependency_outage_is_503_without_a_partial_success(
    feed: FeedHarness,
    engine: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await feed.posts(25)

    async def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("P3 dependency unavailable")

    target: Any
    if engine == "mongo":
        target, method = feed.h.posts, "get_many"
    elif engine == "redis":
        target, method = feed.store, "visible"
    else:
        target, method = feed.graph, "eligible_authors"
    monkeypatch.setattr(target, method, unavailable)
    # Inject the real service with the selected dependency temporarily unavailable.
    from app.api.dependencies.use_cases import get_feed_use_case

    feed.h.app.dependency_overrides[get_feed_use_case] = lambda: feed.service
    response = await feed.h.client.get(f"/api/v1/feeds/{feed.h.user.id}", headers=feed.h.headers())
    assert response.status_code == 503 and "items" not in response.json()
