"""Snapshot discovery across pipeline boundaries and historical/unindexed recipients."""

import json
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Redis"
)


async def test_snapshot_keeps_live_legacy_deferred_and_remembered_scores(harness: Harness) -> None:
    h = harness
    redis = h.resources.redis
    post = str(h.post.id)
    other_post = str(uuid4())
    expected = {f"feed:{h.user.id}": 123.5, f"feed:{h.moderator.id}": 123.5}
    live = dict(expected)
    keys: list[str] = []
    text_client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        pipe = redis.pipeline(transaction=False)
        # No P1 recipients set: these are deliberately legacy feed memberships.
        await redis.delete(f"publication:{post}:recipients")
        assert not await redis.exists(f"publication:{post}:recipients")
        for index in range(377):
            key = f"feed:{uuid4()}"
            keys.append(key)
            expected[key] = index + 0.125
            live[key] = expected[key]
            pipe.zadd(key, {post: expected[key], other_post: -10})
        for _ in range(27):
            key = f"feed:{uuid4()}"
            keys.append(key)
            pipe.zadd(key, {other_post: 900})
        for index in range(11):
            recipient = str(uuid4())
            key = f"account:{recipient}:deferred_in"
            keys.append(key)
            expected[f"feed:{recipient}"] = index + 500.25
            pipe.hset(key, mapping={post: expected[f"feed:{recipient}"], other_post: -2})
        outgoing = f"account:{uuid4()}:deferred_out"
        keys.append(outgoing)
        fields = {}
        for index in range(333):
            recipient = str(uuid4())
            fields[f"{other_post}|{recipient}"] = -4
            fields[f"{post}|{recipient}"] = index + 700.5
            expected[f"feed:{recipient}"] = index + 700.5
        pipe.hset(outgoing, mapping=fields)
        # Noise keys make the scan traverse multiple pages without changing matches.
        for index in range(2300):
            key = f"snapshot-noise:{post}:{index}"
            keys.append(key)
            pipe.set(key, index)
        remembered = f"suspension:{post}:feeds"
        keys.append(remembered)
        recipient = f"feed:{uuid4()}"
        expected[recipient] = 42.75
        pipe.set(remembered, json.dumps({recipient: 42.75}))
        await pipe.execute()
        for view in (
            RedisModerationViews(redis),
            RedisModerationViews(text_client),
            RedisAccountViews(redis),
        ):
            snapshot = await view.snapshot(h.post.id)
            assert snapshot.feeds == expected
            assert snapshot.counters == {"post_reactions": 2, "post_comments": 3}
        current = await h.views.live_snapshot(h.post.id)
        assert current.feeds == live
    finally:
        if keys:
            await redis.delete(*keys)
        await text_client.aclose()
