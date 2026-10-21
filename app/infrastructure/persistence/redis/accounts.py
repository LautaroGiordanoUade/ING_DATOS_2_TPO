import json
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.application.services.moderation_job import ModerationSnapshot
from app.core.exceptions import ConflictError
from app.infrastructure.persistence.redis.follow_gate import FOLLOW_GATE
from app.infrastructure.persistence.redis.moderation import (
    _ADD_VISIBLE,
    _HIDE,
    _RESTORE,
    RedisModerationViews,
)

_BLOCK = """
if redis.call('EXISTS', KEYS[4]) == 0 then
    local backup = {feed=redis.call('ZRANGE', KEYS[2], 0, -1, 'WITHSCORES'),
        presence=redis.call('GET', KEYS[3]) or '', expires=redis.call('PEXPIRETIME', KEYS[3])}
    redis.call('SET', KEYS[4], cjson.encode(backup))
end
redis.call('SET', KEYS[1], 'suspended')
redis.call('DEL', KEYS[2], KEYS[3])
return 1
"""
_HEARTBEAT = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('SET', KEYS[2], 'online', 'EX', 120)
return 1
"""
_UNBLOCK = (
    FOLLOW_GATE
    + """
redis.call('DEL', KEYS[1])
local function deliver(post, recipient, score)
    if redis.call('EXISTS', 'moderation:' .. post .. ':hidden') == 1
       or redis.call('EXISTS', 'suspension:' .. post .. ':hidden') == 1 then return end
    local author = redis.call('GET', 'publication:' .. post .. ':author') or ''
    if not follow_allows(recipient, author, post, score) then return end
    if redis.call('EXISTS', 'account:' .. author .. ':suspended') == 1 then return end
    if redis.call('EXISTS', 'account:' .. recipient .. ':suspended') == 1 then
        redis.call('HSET', 'account:' .. recipient .. ':deferred_in', post, score)
    else
        redis.call('ZADD', 'feed:' .. recipient, score, post)
    end
end
local incoming = redis.call('HGETALL', KEYS[3])
for i=1,#incoming,2 do deliver(incoming[i], ARGV[4], incoming[i+1]) end
redis.call('DEL', KEYS[3])
local outgoing = redis.call('HGETALL', KEYS[4])
for i=1,#outgoing,2 do
    local post, recipient = string.match(outgoing[i], '([^|]+)|(.+)')
    deliver(post, recipient, outgoing[i+1])
end
redis.call('DEL', KEYS[4])
if ARGV[1] ~= '' and tonumber(ARGV[2]) > tonumber(ARGV[3]) then
    redis.call('SET', KEYS[2], ARGV[1], 'NX', 'PXAT', ARGV[2])
end
return 1
"""
)


class RedisAccountViews:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def keys(post_id: UUID) -> list[str]:
        keys = RedisModerationViews.keys(post_id)
        return [keys[1], keys[0], *keys[2:]]

    async def block(self, user_id: UUID, operation_id: UUID) -> None:
        await cast(Any, self._client).eval(
            _BLOCK,
            4,
            f"account:{user_id}:suspended",
            f"feed:{user_id}",
            f"presence:{user_id}",
            f"account:{user_id}:backup:{operation_id}",
        )

    async def unblock(self, user_id: UUID, operation_id: UUID, restore_presence: bool) -> None:
        client = cast(Any, self._client)
        raw = await client.get(f"account:{user_id}:backup:{operation_id}")
        if raw:
            backup = json.loads(raw)
            feed = backup["feed"]
            for start in range(0, len(feed), 500):
                pipe = self._client.pipeline(transaction=False)
                for index in range(start, min(start + 500, len(feed)), 2):
                    post_id = feed[index]
                    # Do not resurrect another moderation/suspension in the account's own feed.
                    pipe.execute_command(
                        "EVAL",
                        _RESTORE_FEED,
                        3,
                        f"feed:{user_id}",
                        f"moderation:{post_id}:hidden",
                        f"suspension:{post_id}:hidden",
                        feed[index + 1],
                        post_id,
                    )
                await pipe.execute()
            presence = backup["presence"] if restore_presence else ""
            expires = backup["expires"]
        else:
            presence, expires = "", 0
        seconds, micros = await client.time()
        await client.eval(
            _UNBLOCK,
            4,
            f"account:{user_id}:suspended",
            f"presence:{user_id}",
            f"account:{user_id}:deferred_in",
            f"account:{user_id}:deferred_out",
            presence,
            expires,
            int(seconds) * 1000 + int(micros) // 1000,
            str(user_id),
        )

    async def snapshot(self, post_id: UUID) -> ModerationSnapshot:
        return await RedisModerationViews(self._client).snapshot(post_id)

    async def hide_post(self, post_id: UUID, snapshot: ModerationSnapshot) -> None:
        await self._client.set(f"suspension:{post_id}:feeds", json.dumps(snapshot.feeds), nx=True)
        keys = self.keys(post_id)
        await cast(Any, self._client).eval(_HIDE, len(keys), *keys)
        await RedisModerationViews(self._client).remove_feeds(post_id, snapshot)

    async def restore_post(self, post_id: UUID, snapshot: ModerationSnapshot) -> None:
        items = list(snapshot.feeds.items())
        for start in range(0, len(items), 250):
            pipe = self._client.pipeline(transaction=False)
            for key, score in items[start : start + 250]:
                pipe.execute_command(
                    "EVAL",
                    _ADD_VISIBLE,
                    2,
                    key,
                    f"moderation:{post_id}:hidden",
                    score,
                    str(post_id),
                )
            await pipe.execute()
        keys = self.keys(post_id)
        await cast(Any, self._client).eval(_RESTORE, len(keys), *keys)
        await self._client.delete(f"suspension:{post_id}:feeds")

    async def heartbeat(self, user_id: UUID) -> None:
        accepted = await cast(Any, self._client).eval(
            _HEARTBEAT, 2, f"account:{user_id}:suspended", f"presence:{user_id}"
        )
        if not accepted:
            raise ConflictError("Suspended accounts cannot open presence")

    async def presence(self, user_id: UUID) -> bool:
        client = cast(Any, self._client)
        result = await client.eval(
            """
            if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
            return redis.call('EXISTS', KEYS[2])
        """,
            2,
            f"account:{user_id}:suspended",
            f"presence:{user_id}",
        )
        return bool(result)


_RESTORE_FEED = (
    FOLLOW_GATE
    + """
if redis.call('EXISTS', KEYS[2]) == 0 and redis.call('EXISTS', KEYS[3]) == 0 then
    local recipient = string.sub(KEYS[1], 6)
    local author = redis.call('GET', 'publication:' .. ARGV[2] .. ':author') or ''
    if not follow_allows(recipient, author, ARGV[2], ARGV[1]) then return 1 end
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
end
return 1
"""
)
