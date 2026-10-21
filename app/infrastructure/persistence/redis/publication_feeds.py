from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis


class RedisPublicationFeeds:
    def __init__(self, client: Redis, author_id: UUID | None = None) -> None:
        self._client = client
        self._author_id = author_id

    @staticmethod
    def state_key(post_id: UUID) -> str:
        return f"publication:{post_id}:state"

    async def stage_batch(self, user_ids: tuple[UUID, ...], post_id: UUID, score: float) -> None:
        # A durable audience in MongoDB identifies every possible partial write.
        # Each ZADD repeats safely. Visibility is gated by one shared commit marker.
        pipe = self._client.pipeline(transaction=False)
        for user_id in user_ids:
            if self._author_id is None:
                pipe.execute_command(
                    "EVAL",
                    _STAGE,
                    3,
                    f"feed:{user_id}",
                    f"account:{user_id}:suspended",
                    f"suspension:{post_id}:hidden",
                    score,
                    str(post_id),
                )
            else:
                pipe.execute_command(
                    "EVAL",
                    _STAGE_AUTHOR,
                    4,
                    f"feed:{user_id}",
                    f"account:{user_id}:suspended",
                    f"account:{self._author_id}:suspended",
                    f"publication:{post_id}:author",
                    score,
                    str(post_id),
                    str(self._author_id),
                )
        await pipe.execute()

    async def commit(self, post_id: UUID) -> None:
        if self._author_id is not None:
            await self._client.set(f"publication:{post_id}:author", str(self._author_id))
        await self._client.set(self.state_key(post_id), "published")

    async def abort(self, post_id: UUID) -> None:
        await self._client.set(self.state_key(post_id), "aborted")

    async def remove_batch(self, user_ids: tuple[UUID, ...], post_id: UUID) -> None:
        pipe = self._client.pipeline(transaction=False)
        for user_id in user_ids:
            pipe.zrem(f"feed:{user_id}", str(post_id))
            pipe.hdel(f"account:{user_id}:deferred_in", str(post_id))
            if self._author_id is not None:
                pipe.hdel(f"account:{self._author_id}:deferred_out", f"{post_id}|{user_id}")
        await pipe.execute()

    async def visible_ids(self, user_id: UUID, limit: int = 20) -> tuple[UUID, ...]:
        """P1 inspection helper; ranking/cursors and counter enrichment belong to P3."""
        client = cast(Any, self._client)
        # One Redis execution observes candidates and their common visibility marker.
        script = """
        if redis.call('EXISTS', KEYS[2]) == 1 then return {} end
        local rows = redis.call('ZREVRANGE', KEYS[1], 0, -1)
        local visible = {}
        for _, id in ipairs(rows) do
            local author = redis.call('GET', 'publication:' .. id .. ':author') or ''
            if redis.call('GET', 'publication:' .. id .. ':state') == 'published'
                and redis.call('EXISTS', 'moderation:' .. id .. ':hidden') == 0
                and redis.call('EXISTS', 'suspension:' .. id .. ':hidden') == 0
                and redis.call('EXISTS', 'account:' .. author .. ':suspended') == 0 then
                table.insert(visible, id)
                if #visible >= tonumber(ARGV[1]) then break end
            end
        end
        return visible
        """
        rows = await client.eval(
            script, 2, f"feed:{user_id}", f"account:{user_id}:suspended", limit
        )
        return tuple(UUID(row.decode() if isinstance(row, bytes) else row) for row in rows)


_STAGE = """
if redis.call('EXISTS', KEYS[2]) == 0 and redis.call('EXISTS', KEYS[3]) == 0 then
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
end
return 1
"""
_STAGE_AUTHOR = """
redis.call('SET', KEYS[4], ARGV[3])
local recipient = string.sub(KEYS[1], 6)
local author_blocked = redis.call('EXISTS', KEYS[3]) == 1
local recipient_blocked = redis.call('EXISTS', KEYS[2]) == 1
if author_blocked then
    redis.call('HSET', 'account:' .. ARGV[3] .. ':deferred_out',
               ARGV[2] .. '|' .. recipient, ARGV[1])
end
if recipient_blocked then
    redis.call('HSET', 'account:' .. recipient .. ':deferred_in', ARGV[2], ARGV[1])
end
if not author_blocked and not recipient_blocked then
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
end
return 1
"""
