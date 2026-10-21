import time
from typing import Any, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.application.services.feed_page import (
    FeedCandidates,
    FeedExpiredError,
    FeedSession,
    FeedWindow,
)

# Strict (score, UUID) boundary, even if deleted or shared by >200 posts. Binary
# search avoids loading the whole feed or relying on a moving page offset.
_CANDIDATES = """
local lo, hi = 0, redis.call('ZCARD', KEYS[1])
local score = tonumber(ARGV[1])
while lo < hi do
    local mid = math.floor((lo + hi) / 2)
    local row = redis.call('ZREVRANGE', KEYS[1], mid, mid, 'WITHSCORES')
    local older = tonumber(row[2]) < score
        or (tonumber(row[2]) == score and row[1] < ARGV[2])
    if older then hi = mid else lo = mid + 1 end
end
return redis.call('ZREVRANGE', KEYS[1], lo, lo + 200, 'WITHSCORES')
"""
_VISIBLE = """
if redis.call('EXISTS', 'account:' .. ARGV[1] .. ':suspended') == 1 then return {} end
local result = {}
for i=2,#ARGV do
    local post = ARGV[i]
    local author = redis.call('GET', 'publication:' .. post .. ':author') or ''
    local follow = redis.call('GET', 'follow:' .. ARGV[1] .. ':' .. author .. ':state')
    if redis.call('ZSCORE', KEYS[1], post)
       and redis.call('GET', 'publication:' .. post .. ':state') == 'published'
       and redis.call('EXISTS', 'moderation:' .. post .. ':hidden') == 0
       and redis.call('EXISTS', 'suspension:' .. post .. ':hidden') == 0
       and redis.call('EXISTS', 'account:' .. author .. ':suspended') == 0
       and (not follow or follow == 'accepted') then table.insert(result, post) end
end
return result
"""


class RedisPersonalizedFeed:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def key(session_id: UUID) -> str:
        return f"feed-page:{session_id}"

    async def start(self, user_id: UUID) -> FeedSession:
        now = time.time()
        session = FeedSession(id=uuid4(), user_id=user_id, expires=int(now) + 900, anchor=now)
        pipe = self._client.pipeline(transaction=True)
        pipe.hset(self.key(session.id), "metadata", session.model_dump_json())
        pipe.expireat(self.key(session.id), session.expires)
        await pipe.execute()
        return session

    async def session(self, session_id: UUID) -> FeedSession:
        raw = await cast(Any, self._client).hget(self.key(session_id), "metadata")
        if raw is None:
            raise FeedExpiredError("La navegacion vencio; refresque el feed")
        return FeedSession.model_validate_json(raw)

    async def window(self, session: FeedSession, index: int) -> FeedWindow | None:
        raw = await cast(Any, self._client).hget(self.key(session.id), f"window:{index}")
        return None if raw is None else FeedWindow.model_validate_json(raw)

    async def save_window(self, session: FeedSession, index: int, window: FeedWindow) -> FeedWindow:
        # Concurrent readers of one cursor share the first saved order.
        raw = await cast(Any, self._client).eval(
            """if redis.call('EXISTS', KEYS[1]) == 0 then return false end
            redis.call('HSETNX', KEYS[1], ARGV[1], ARGV[2])
            return redis.call('HGET', KEYS[1], ARGV[1])""",
            1,
            self.key(session.id),
            f"window:{index}",
            window.model_dump_json(),
        )
        if not raw:
            raise FeedExpiredError("La navegacion vencio; refresque el feed")
        return FeedWindow.model_validate_json(raw)

    async def candidates(self, user_id: UUID, score: float, identifier: str) -> FeedCandidates:
        values = await cast(Any, self._client).eval(
            _CANDIDATES,
            1,
            f"feed:{user_id}",
            score,
            identifier,
        )
        return FeedCandidates(
            rows=[
                (UUID(values[i].decode()), float(values[i + 1]))
                for i in range(0, min(len(values), 400), 2)
            ],
            more=len(values) > 400,
        )

    async def visible(self, user_id: UUID, ids: tuple[UUID, ...]) -> set[UUID]:
        if not ids:
            return set()
        values = await cast(Any, self._client).eval(
            _VISIBLE,
            1,
            f"feed:{user_id}",
            str(user_id),
            *map(str, ids),
        )
        return {UUID(value.decode()) for value in values}
