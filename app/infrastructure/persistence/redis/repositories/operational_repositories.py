from uuid import UUID

from redis.asyncio import Redis

from app.core.exceptions import FeatureNotImplementedError
from app.domain.value_objects import FeedCursor, Page


class RedisFeedRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def add_to_feeds(
        self, user_ids: tuple[UUID, ...], post_id: UUID, score: float
    ) -> None:
        # TODO(TP): Definir fan-out y comandos/estructura Redis del feed.
        raise FeatureNotImplementedError("RedisFeedRepository.add_to_feeds")

    async def remove_from_feeds(self, post_id: UUID) -> None:
        # TODO(TP): Implementar retiro compensable de todos los feeds afectados.
        raise FeatureNotImplementedError("RedisFeedRepository.remove_from_feeds")

    async def get_feed(
        self, user_id: UUID, cursor: FeedCursor | None, limit: int
    ) -> Page[UUID]:
        # TODO(TP): Implementar cursor score/timestamp/UUID y ranking final.
        raise FeatureNotImplementedError("RedisFeedRepository.get_feed")

    async def clear_user_feed(self, user_id: UUID) -> None:
        # TODO(TP): Definir efecto de suspensión sobre el feed materializado.
        raise FeatureNotImplementedError("RedisFeedRepository.clear_user_feed")


class RedisCounterRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def increment(self, namespace: str, entity_id: UUID, amount: int = 1) -> int:
        # TODO(TP): Elegir comando atómico, límites y reconciliación de contadores.
        raise FeatureNotImplementedError("RedisCounterRepository.increment")

    async def get_many(
        self, namespace: str, entity_ids: tuple[UUID, ...]
    ) -> dict[UUID, int]:
        # TODO(TP): Implementar lectura por lote de contadores.
        raise FeatureNotImplementedError("RedisCounterRepository.get_many")


class RedisNotificationRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def publish(self, recipient_id: UUID, event: dict[str, object]) -> None:
        # TODO(TP): Definir persistencia/entrega y comando Redis de notificaciones.
        raise FeatureNotImplementedError("RedisNotificationRepository.publish")

    async def revoke(self, recipient_id: UUID, event_id: UUID) -> None:
        # TODO(TP): Implementar compensación de notificación si el modelo lo permite.
        raise FeatureNotImplementedError("RedisNotificationRepository.revoke")


class RedisIdempotencyRepository:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def reserve(self, key: str, operation_name: str, ttl_seconds: int) -> bool:
        # TODO(TP): Implementar reserva atómica con TTL y ownership de operación.
        raise FeatureNotImplementedError("RedisIdempotencyRepository.reserve")

    async def get_result(self, key: str) -> bytes | None:
        # TODO(TP): Implementar lectura del resultado idempotente.
        raise FeatureNotImplementedError("RedisIdempotencyRepository.get_result")

    async def store_result(self, key: str, result: bytes, ttl_seconds: int) -> None:
        # TODO(TP): Implementar finalización atómica de la clave.
        raise FeatureNotImplementedError("RedisIdempotencyRepository.store_result")

