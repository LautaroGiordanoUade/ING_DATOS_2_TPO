import json
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.exceptions import FeatureNotImplementedError
from app.domain.value_objects import FeedCursor, Page
from app.infrastructure.persistence.redis.keys import RedisKeys
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds


class RedisFeedRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def add_to_feeds(self, user_ids: tuple[UUID, ...], post_id: UUID, score: float) -> None:
        # TODO(TP): Definir fan-out y comandos/estructura Redis del feed.
        raise FeatureNotImplementedError("RedisFeedRepository.add_to_feeds")

    async def remove_from_feeds(self, post_id: UUID) -> None:
        # TODO(TP): Implementar retiro compensable de todos los feeds afectados.
        raise FeatureNotImplementedError("RedisFeedRepository.remove_from_feeds")

    async def get_feed(self, user_id: UUID, cursor: FeedCursor | None, limit: int) -> Page[UUID]:
        if cursor is not None:
            from app.core.exceptions import InvalidOperationError

            raise InvalidOperationError("Personalized cursors belong to pending P3")
        return Page(items=await RedisPublicationFeeds(self._client).visible_ids(user_id, limit))

    async def clear_user_feed(self, user_id: UUID) -> None:
        # TODO(TP): Definir efecto de suspensión sobre el feed materializado.
        raise FeatureNotImplementedError("RedisFeedRepository.clear_user_feed")


# Suma/resta de forma atómica (un solo comando en el servidor) y nunca baja de 0.
_INCREMENT_NOT_NEGATIVE = """
local key = KEYS[1]
if ARGV[2] ~= '' and (redis.call('EXISTS', ARGV[2]) == 1
    or redis.call('EXISTS', ARGV[3]) == 1) then
    key = key .. ':moderation_saved'
end
local value = redis.call('INCRBY', key, ARGV[1])
if value < 0 then
    redis.call('SET', key, 0)
    return 0
end
return value
"""


class RedisCounterRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def increment(self, namespace: str, entity_id: UUID, amount: int = 1) -> int:
        key = RedisKeys.counter(namespace, entity_id)
        client = cast(Any, self._client)
        gate = (
            f"moderation:{entity_id}:hidden"
            if namespace in ("post_reactions", "post_comments")
            else ""
        )
        result = await client.eval(
            _INCREMENT_NOT_NEGATIVE, 1, key, str(amount), gate, f"suspension:{entity_id}:hidden"
        )
        return int(result)
    
    async def set_value(self, namespace: str, entity_id: UUID, value: int) -> int:
        key = RedisKeys.counter(namespace, entity_id)
        client = cast(Any, self._client)
        clamped = max(0, int(value))
        await client.set(key, str(clamped))
        return clamped

    async def get_many(self, namespace: str, entity_ids: tuple[UUID, ...]) -> dict[UUID, int]:
        if not entity_ids:
            return {}
        keys = [RedisKeys.counter(namespace, entity_id) for entity_id in entity_ids]
        client = cast(Any, self._client)
        values = await client.mget(keys)
        return {
            entity_id: int(value) if value is not None else 0
            for entity_id, value in zip(entity_ids, values, strict=True)
        }


class RedisNotificationRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def publish(self, recipient_id: UUID, event: dict[str, object]) -> None:
        event_id = str(event["event_id"])
        payload = json.dumps(event, default=str)
        client = cast(Any, self._client)
        # Guardada (hash por event_id: repetir el mismo evento no la duplica)...
        await client.hset(RedisKeys.notifications(recipient_id), event_id, payload)
        # ...y entregada al instante a quien esté conectado (Pub/Sub).
        await client.publish(RedisKeys.notification_channel(recipient_id), payload)

    async def revoke(self, recipient_id: UUID, event_id: UUID) -> None:
        client = cast(Any, self._client)
        await client.hdel(RedisKeys.notifications(recipient_id), str(event_id))


class RedisIdempotencyRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def reserve(self, key: str, operation_name: str, ttl_seconds: int) -> bool:
        # SET con NX: solo el primero que llega logra reservar la clave.
        reserved = await self._client.set(
            RedisKeys.idempotency(key), operation_name, nx=True, ex=ttl_seconds
        )
        return bool(reserved)

    async def get_result(self, key: str) -> bytes | None:
        value = await self._client.get(RedisKeys.idempotency_result(key))
        if value is None:
            return None
        return value if isinstance(value, bytes) else str(value).encode()

    async def store_result(self, key: str, result: bytes, ttl_seconds: int) -> None:
        await self._client.set(RedisKeys.idempotency_result(key), result, ex=ttl_seconds)

    async def release(self, key: str) -> None:
        await self._client.delete(RedisKeys.idempotency(key))
        
    async def get_reservation(self, key: str) -> str | None:
        value = await self._client.get(RedisKeys.idempotency(key))
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)
