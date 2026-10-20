from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import LockError

from app.core.exceptions import ConflictError


class RedisReactionLock:
    """Serialize reaction changes and compensations across API processes.

    No lease expiry: a paused writer must not overlap a second writer. After a
    process crash, reconcile the operation before manually releasing its lock.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    @asynccontextmanager
    async def hold(self, post_id: UUID) -> AsyncIterator[None]:
        lock = self._client.lock(
            f"lock:post_reactions:{post_id}",
            timeout=None,
            blocking_timeout=5,
            thread_local=False,
        )
        if not await lock.acquire():
            raise ConflictError("Hay otra reacción en curso para esta publicación; reintente")
        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError:
                # Never delete a lock owned by another operation.
                raise ConflictError("Se perdió el bloqueo de la publicación") from None
