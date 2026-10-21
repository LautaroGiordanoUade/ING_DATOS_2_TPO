import json
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.application.services.follow_job import FollowJob, FollowSnapshot
from app.infrastructure.persistence.redis.follow_gate import FOLLOW_GATE

_BEGIN = """
local saved = redis.call('GET', KEYS[3])
if not saved then
    local catalog = cjson.decode(ARGV[2])
    for _, post in ipairs(catalog) do
        redis.call('SET', 'publication:' .. post .. ':author', ARGV[1])
    end
    local entries = redis.call('ZRANGE', KEYS[1], 0, -1, 'WITHSCORES')
    if #entries > 200000 then return redis.error_reply('Feed snapshot exceeds 100000 entries') end
    local feeds = {}
    for i=1,#entries,2 do
        if redis.call('GET', 'publication:' .. entries[i] .. ':author') == ARGV[1] then
            feeds[entries[i]] = tonumber(entries[i+1])
        end
    end
    saved = cjson.encode({gate=redis.call('GET', KEYS[2]) or cjson.null, feeds=feeds})
    redis.call('SET', KEYS[3], saved)
end
redis.call('SET', KEYS[2], 'processing:' .. ARGV[3])
return saved
"""
_APPLY = """
if redis.call('GET', KEYS[2]) ~= 'processing:' .. ARGV[3] then
    return redis.error_reply('Follow operation lost ownership')
end
local posts = cjson.decode(ARGV[4])
for post, score in pairs(posts) do
    if ARGV[2] == 'accepted' then
        if redis.call('GET', 'publication:' .. post .. ':state') ~= 'aborted'
           and redis.call('EXISTS', 'moderation:' .. post .. ':hidden') == 0
           and redis.call('EXISTS', 'suspension:' .. post .. ':hidden') == 0 then
            redis.call('SET', 'publication:' .. post .. ':author', ARGV[1])
            redis.call('SADD', 'publication:' .. post .. ':recipients', ARGV[5])
            if redis.call('EXISTS', 'account:' .. ARGV[1] .. ':suspended') == 0
               and redis.call('EXISTS', 'account:' .. ARGV[5] .. ':suspended') == 0 then
                redis.call('ZADD', KEYS[1], score, post)
            else
                redis.call('HSET', KEYS[3], post, score)
            end
        end
    else
        redis.call('ZREM', KEYS[1], post)
        redis.call('HDEL', 'account:' .. ARGV[5] .. ':deferred_in', post)
        redis.call('HDEL', 'account:' .. ARGV[1] .. ':deferred_out', post .. '|' .. ARGV[5])
    end
end
return 1
"""
_FINISH = (
    FOLLOW_GATE
    + """
if redis.call('EXISTS', KEYS[4]) == 1 then return 1 end
local function add(post, score)
    if redis.call('EXISTS', 'moderation:' .. post .. ':hidden') == 1
       or redis.call('EXISTS', 'suspension:' .. post .. ':hidden') == 1 then return end
    if not follow_allows(ARGV[1], ARGV[2], post, score) then return end
    if redis.call('EXISTS', 'account:' .. ARGV[2] .. ':suspended') == 1 then
        redis.call('HSET', 'account:' .. ARGV[2] .. ':deferred_out', post .. '|' .. ARGV[1], score)
    elseif redis.call('EXISTS', 'account:' .. ARGV[1] .. ':suspended') == 1 then
        redis.call('HSET', 'account:' .. ARGV[1] .. ':deferred_in', post, score)
    else
        redis.call('ZADD', KEYS[1], score, post)
    end
end
if ARGV[4] == 'restore' then
    local rows = redis.call('ZRANGE', KEYS[1], 0, -1)
    for _, post in ipairs(rows) do
        if redis.call('GET', 'publication:' .. post .. ':author') == ARGV[2] then
            redis.call('ZREM', KEYS[1], post)
        end
    end
end
if ARGV[3] == '' then redis.call('DEL', KEYS[2]) else redis.call('SET', KEYS[2], ARGV[3]) end
if ARGV[4] == 'restore' then
    for post, score in pairs(cjson.decode(ARGV[5])) do add(post, score) end
end
local deferred = redis.call('HGETALL', KEYS[3])
if ARGV[6] == 'accepted' then
    for i=1,#deferred,2 do add(deferred[i], deferred[i+1]) end
end
redis.call('DEL', KEYS[3])
redis.call('SET', KEYS[4], ARGV[4])
return 1
"""
)


class RedisFollowViews:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def gate(follower_id: UUID, author_id: UUID) -> str:
        return f"follow:{follower_id}:{author_id}:state"

    async def begin(self, job: FollowJob) -> FollowSnapshot:
        result = await cast(Any, self._client).eval(
            _BEGIN,
            3,
            f"feed:{job.follower_id}",
            self.gate(job.follower_id, job.followed_id),
            f"follow:backup:{job.operation_id}",
            str(job.followed_id),
            json.dumps([str(post) for post in job.catalog]),
            str(job.operation_id),
        )
        return FollowSnapshot.model_validate_json(result)

    async def set_counts(self, counts: dict[str, dict[str, int]]) -> None:
        keys, values = [], []
        for identifier, data in counts.items():
            for namespace in ("followers", "following"):
                keys.append(f"{namespace}:{identifier}:count")
                values.append(data[namespace])
        await cast(Any, self._client).eval(
            "for i,key in ipairs(KEYS) do redis.call('SET',key,ARGV[i]) end return 1",
            len(keys),
            *keys,
            *values,
        )

    async def initialize_counts(self, user_id: UUID, counts: dict[str, int]) -> None:
        # Legacy fixtures have graph edges but no counters. NX cannot overwrite
        # a newer value committed by P2 while the canonical graph was being read.
        await cast(Any, self._client).eval(
            "for i,key in ipairs(KEYS) do redis.call('SET',key,ARGV[i],'NX') end return 1",
            2,
            f"followers:{user_id}:count",
            f"following:{user_id}:count",
            counts["followers"],
            counts["following"],
        )

    async def counts(self, user_id: UUID) -> dict[str, int]:
        values = await self._client.mget(
            [f"followers:{user_id}:count", f"following:{user_id}:count"]
        )
        return dict(
            zip(("followers", "following"), (int(value or 0) for value in values), strict=True)
        )

    async def apply_batch(self, job: FollowJob, posts: dict[str, float]) -> None:
        await cast(Any, self._client).eval(
            _APPLY,
            3,
            f"feed:{job.follower_id}",
            self.gate(job.follower_id, job.followed_id),
            f"follow:{job.follower_id}:{job.followed_id}:deferred",
            str(job.followed_id),
            job.desired,
            str(job.operation_id),
            json.dumps(posts),
            str(job.follower_id),
        )

    async def finish(self, job: FollowJob, restore: bool = False) -> None:
        assert job.snapshot is not None and job.graph_snapshot is not None
        previous = job.graph_snapshot["relationship"]
        desired = (
            (previous.get("status", "accepted") if previous else "none") if restore else job.desired
        )
        gate = job.snapshot.gate if restore else job.desired
        await cast(Any, self._client).eval(
            _FINISH,
            4,
            f"feed:{job.follower_id}",
            self.gate(job.follower_id, job.followed_id),
            f"follow:{job.follower_id}:{job.followed_id}:deferred",
            f"follow:{job.operation_id}:finished",
            str(job.follower_id),
            str(job.followed_id),
            gate or "",
            "restore" if restore else "commit",
            json.dumps(job.snapshot.feeds),
            desired,
        )
