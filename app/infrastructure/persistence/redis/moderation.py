from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.application.services.moderation_job import ModerationSnapshot
from app.core.exceptions import InvalidOperationError
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.infrastructure.persistence.redis.keys import RedisKeys

# Atomic per-post transitions, including uncertain acknowledgements. The saved
# counts continue receiving in-flight P5 changes while the public counts stay 0.
_HIDE = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SET', KEYS[1], 'hidden')
    for i=2,#KEYS do
        redis.call('SET', KEYS[i] .. ':moderation_saved', redis.call('GET', KEYS[i]) or '0')
        redis.call('SET', KEYS[i], 0)
    end
end
return 1
"""
_RESTORE = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    for i=2,#KEYS do
        local value = redis.call('GET', KEYS[i] .. ':moderation_saved') or '0'
        redis.call('SET', KEYS[i], value)
        redis.call('DEL', KEYS[i] .. ':moderation_saved')
    end
    redis.call('DEL', KEYS[1])
end
return 1
"""


class RedisModerationViews:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def keys(post_id: UUID) -> list[str]:
        return [
            f"moderation:{post_id}:hidden",
            *[
                RedisKeys.counter(namespace, post_id)
                for namespace in (POST_REACTIONS, POST_COMMENTS)
            ],
        ]

    async def snapshot(self, post_id: UUID) -> ModerationSnapshot:
        client = cast(Any, self._client)
        # No production writer mutates the audience after the P1 job completes.
        feeds: dict[str, float] = {}
        async for key in self._client.scan_iter(match="feed:*"):
            score = await client.zscore(key, str(post_id))
            if score is not None:
                feeds[key.decode() if isinstance(key, bytes) else str(key)] = float(score)
                if len(feeds) > 100_000:
                    raise InvalidOperationError("Moderation supports up to 100000 feed memberships")
        values = await client.mget(self.keys(post_id)[1:])
        return ModerationSnapshot(
            moderation_status="pending",
            feeds=feeds,
            counters={
                name: int(value or 0)
                for name, value in zip((POST_REACTIONS, POST_COMMENTS), values, strict=True)
            },
        )

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
                pipe.zadd(key, {str(post_id): score})
            await pipe.execute()
        keys = self.keys(post_id)
        await cast(Any, self._client).eval(_RESTORE, len(keys), *keys)
