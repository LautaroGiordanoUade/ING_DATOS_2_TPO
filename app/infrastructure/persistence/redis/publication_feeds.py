from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis


class RedisPublicationFeeds:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def state_key(post_id: UUID) -> str:
        return f"publication:{post_id}:state"

    async def stage_batch(self, user_ids: tuple[UUID, ...], post_id: UUID, score: float) -> None:
        # A durable audience in MongoDB identifies every possible partial write.
        # Each ZADD repeats safely. Visibility is gated by one shared commit marker.
        pipe = self._client.pipeline(transaction=False)
        for user_id in user_ids:
            pipe.zadd(f"feed:{user_id}", {str(post_id): score})
        await pipe.execute()

    async def commit(self, post_id: UUID) -> None:
        await self._client.set(self.state_key(post_id), "published")

    async def abort(self, post_id: UUID) -> None:
        await self._client.set(self.state_key(post_id), "aborted")

    async def remove_batch(self, user_ids: tuple[UUID, ...], post_id: UUID) -> None:
        pipe = self._client.pipeline(transaction=False)
        for user_id in user_ids:
            pipe.zrem(f"feed:{user_id}", str(post_id))
        await pipe.execute()

    async def visible_ids(self, user_id: UUID, limit: int = 20) -> tuple[UUID, ...]:
        """P1 inspection helper; ranking/cursors and counter enrichment belong to P3."""
        client = cast(Any, self._client)
        # One Redis execution observes candidates and their common visibility marker.
        script = """
        local rows = redis.call('ZREVRANGE', KEYS[1], 0, -1)
        local visible = {}
        for _, id in ipairs(rows) do
            if redis.call('GET', 'publication:' .. id .. ':state') == 'published' then
                table.insert(visible, id)
                if #visible >= tonumber(ARGV[1]) then break end
            end
        end
        return visible
        """
        rows = await client.eval(script, 1, f"feed:{user_id}", limit)
        return tuple(UUID(row.decode() if isinstance(row, bytes) else row) for row in rows)
