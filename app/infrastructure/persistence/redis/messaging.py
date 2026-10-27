import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from redis.asyncio import Redis

from app.application.ports.messaging import GroupMessage
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock


class ConversationLock:
    """One host/shared volume: authoritative OS lock also works during Redis outages."""

    def __init__(self, client: Redis) -> None:
        self._host = RedisReactionLock(client)

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[None]:
        async with self._host._host_hold(uuid5(NAMESPACE_URL, f"p6:{conversation_id}")):
            yield


class RedisMessagingViews:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @staticmethod
    def key(group_id: UUID, actor: UUID) -> str:
        return f"conversation:{group_id}:unread:{actor}"

    async def set_unread(self, group_id: UUID, actor: UUID, count: int) -> None:
        await self.client.set(self.key(group_id, actor), count)

    async def unread(self, group_id: UUID, actor: UUID) -> int:
        return int(await self.client.get(self.key(group_id, actor)) or 0)

    async def notify(self, message: GroupMessage, recipient: UUID) -> None:
        # Atomic with P8's suspension gate. Retry receipts are monotonic per conversation.
        await cast(Any, self.client).eval(
            """
            if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
            if redis.call('EXISTS', KEYS[2]) == 0 then return 0 end
            local prior = tonumber(redis.call('GET', KEYS[3]) or '0')
            if prior >= tonumber(ARGV[1]) then return 0 end
            redis.call('SET', KEYS[3], ARGV[1])
            redis.call('PUBLISH', KEYS[4], ARGV[2])
            return 1
        """,
            4,
            f"account:{recipient}:suspended",
            f"presence:{recipient}",
            f"conversation:{message.conversation_id}:notified:{recipient}",
            f"user:{recipient}:messages:live",
            message.sequence,
            json.dumps(
                {"message_id": str(message.id), "conversation_id": str(message.conversation_id)}
            ),
        )
