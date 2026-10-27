import json
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.application.services.moderation_job import ModerationSnapshot
from app.core.exceptions import InvalidOperationError
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.infrastructure.persistence.redis.follow_gate import FOLLOW_GATE
from app.infrastructure.persistence.redis.keys import RedisKeys

# Atomic per-post transitions, including uncertain acknowledgements. The saved
# counts continue receiving in-flight P5 changes while the public counts stay 0.
_HIDE = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    if redis.call('EXISTS', KEYS[2]) == 0 then
        for i=3,#KEYS do
            redis.call('SET', KEYS[i] .. ':moderation_saved', redis.call('GET', KEYS[i]) or '0')
            redis.call('SET', KEYS[i], 0)
        end
    end
    redis.call('SET', KEYS[1], 'hidden')
end
return 1
"""
_RESTORE = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    redis.call('DEL', KEYS[1])
    if redis.call('EXISTS', KEYS[2]) == 0 then
        for i=3,#KEYS do
            redis.call('SET', KEYS[i], redis.call('GET', KEYS[i] .. ':moderation_saved') or '0')
            redis.call('DEL', KEYS[i] .. ':moderation_saved')
        end
    end
end
return 1
"""
_ADD_VISIBLE = (
    FOLLOW_GATE
    + """
if redis.call('EXISTS', KEYS[2]) == 0 then
    local recipient = string.sub(KEYS[1], 6)
    local author = redis.call('GET', 'publication:' .. ARGV[2] .. ':author') or ''
    if not follow_allows(recipient, author, ARGV[2], ARGV[1]) then return 1 end
    if redis.call('EXISTS', 'account:' .. author .. ':suspended') == 1 then
        redis.call('HSET', 'account:' .. author .. ':deferred_out',
                   ARGV[2] .. '|' .. recipient, ARGV[1])
    elseif redis.call('EXISTS', 'account:' .. recipient .. ':suspended') == 1 then
        redis.call('HSET', 'account:' .. recipient .. ':deferred_in', ARGV[2], ARGV[1])
    else
        redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
        redis.call('HDEL', 'account:' .. recipient .. ':deferred_in', ARGV[2])
    end
end
return 1
"""
)


class RedisModerationViews:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def _score_batch(
        self, keys: list[bytes | str], post_id: UUID, hash_values: bool
    ) -> dict[str, float]:
        pipe = self._client.pipeline(transaction=False)
        for key in keys:
            if hash_values:
                pipe.hget(key.decode() if isinstance(key, bytes) else key, str(post_id))
            else:
                pipe.zscore(key, str(post_id))
        scores = await pipe.execute()
        return {
            key.decode() if isinstance(key, bytes) else key: float(score)
            for key, score in zip(keys, scores, strict=True)
            if score is not None
        }

    async def _membership_scores(
        self, pattern: str, post_id: UUID, *, hash_values: bool = False
    ) -> AsyncIterator[tuple[str, float]]:
        # SCAN's count is a hint, not a bound. Bound the read pipeline separately.
        # Keep full discovery: historical feeds can lack P1 recipient bookkeeping.
        keys: list[bytes | str] = []
        async for key in self._client.scan_iter(match=pattern, count=1000):
            keys.append(key)
            if len(keys) == 250:
                for item in (await self._score_batch(keys, post_id, hash_values)).items():
                    yield item
                keys = []
        if keys:
            for item in (await self._score_batch(keys, post_id, hash_values)).items():
                yield item

    @staticmethod
    def keys(post_id: UUID) -> list[str]:
        return [
            f"moderation:{post_id}:hidden",
            f"suspension:{post_id}:hidden",
            *[
                RedisKeys.counter(namespace, post_id)
                for namespace in (POST_REACTIONS, POST_COMMENTS)
            ],
        ]

    async def snapshot(self, post_id: UUID) -> ModerationSnapshot:
        client = cast(Any, self._client)
        # Discover current memberships, including historical feeds and deferred deliveries.
        feeds: dict[str, float] = {}
        async for key, score in self._membership_scores("feed:*", post_id):
            feeds[key] = score
            if len(feeds) > 100_000:
                raise InvalidOperationError("Moderation supports up to 100000 feed memberships")
        # A suspended recipient/author may have deferred P1 deliveries. P7 must
        # preserve those references too, even though they are not public feed rows yet.
        async for key, score in self._membership_scores(
            "account:*:deferred_in", post_id, hash_values=True
        ):
            feeds[f"feed:{key.split(':')[1]}"] = score
        async for key in self._client.scan_iter(match="account:*:deferred_out", count=1000):
            async for field, score in client.hscan_iter(key, match=f"{post_id}|*", count=1000):
                text = field.decode() if isinstance(field, bytes) else str(field)
                feeds[f"feed:{text.split('|')[1]}"] = float(score)
        if len(feeds) > 100_000:
            raise InvalidOperationError("Moderation supports up to 100000 feed memberships")
        remembered = await client.get(f"suspension:{post_id}:feeds")
        if remembered:
            feeds = {**json.loads(remembered), **feeds}
        values = await client.mget(self.keys(post_id)[2:])
        return ModerationSnapshot(
            moderation_status="pending",
            feeds=feeds,
            counters={
                name: int(value or 0)
                for name, value in zip((POST_REACTIONS, POST_COMMENTS), values, strict=True)
            },
        )

    async def live_snapshot(self, post_id: UUID) -> ModerationSnapshot:
        snapshot = await self.snapshot(post_id)
        present: dict[str, float] = {}
        client = cast(Any, self._client)
        for key in snapshot.feeds:
            score = await client.zscore(key, str(post_id))
            if score is not None:
                present[key] = float(score)
        snapshot.feeds = present
        return snapshot

    async def hide(self, post_id: UUID) -> None:
        keys = self.keys(post_id)
        await cast(Any, self._client).eval(_HIDE, len(keys), *keys)

    async def remove_feeds(self, post_id: UUID, snapshot: ModerationSnapshot) -> None:
        feeds = list(snapshot.feeds)
        for start in range(0, len(feeds), 250):
            pipe = self._client.pipeline(transaction=False)
            for key in feeds[start : start + 250]:
                pipe.zrem(key, str(post_id))
            await pipe.execute()

    async def restore(self, post_id: UUID, snapshot: ModerationSnapshot) -> None:
        feeds = list(snapshot.feeds.items())
        for start in range(0, len(feeds), 250):
            pipe = self._client.pipeline(transaction=False)
            for key, score in feeds[start : start + 250]:
                pipe.execute_command(
                    "EVAL",
                    _ADD_VISIBLE,
                    2,
                    key,
                    f"suspension:{post_id}:hidden",
                    score,
                    str(post_id),
                )
            await pipe.execute()
        keys = self.keys(post_id)
        await cast(Any, self._client).eval(_RESTORE, len(keys), *keys)
