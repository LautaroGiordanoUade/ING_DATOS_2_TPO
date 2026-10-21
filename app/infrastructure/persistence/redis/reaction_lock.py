import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import LockError

from app.core.exceptions import ConflictError


class RedisReactionLock:
    """Serializa los cambios de reacciones y las compensaciones entre procesos de la API.

    Utiliza un bloqueo con tiempo de expiración limitado y una renovación
    periódica en segundo plano mientras el proceso de la API sigue activo.
    Si la API falla, el bloqueo abandonado expira y activa una reconciliación
    automática del estado antes de que el siguiente proceso pueda modificarlo.
    """

    def __init__(
        self,
        client: Redis,
        lease_seconds: float = 30.0,
        blocking_timeout: float = 5.0,
    ) -> None:
        self._client = client
        self._lease_seconds = lease_seconds
        self._blocking_timeout = blocking_timeout

    async def _heartbeat(self, lock: Any, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            with contextlib.suppress(LockError):
                await lock.reacquire()

    @asynccontextmanager
    async def hold(self, post_id: UUID) -> AsyncIterator[None]:
        lock_name = f"lock:post_reactions:{post_id}"
        owner_marker = f"lock_active:post_reactions:{post_id}"
        client = cast(Any, self._client)

        lock = self._client.lock(
            lock_name,
            timeout=self._lease_seconds,
            blocking_timeout=self._blocking_timeout,
            thread_local=False,
        )
        if not await lock.acquire():
            raise ConflictError(
                "Hay otra reacción en curso para esta publicación; reintente"
            )

        heartbeat_task = asyncio.create_task(
            self._heartbeat(lock, max(0.5, self._lease_seconds / 3))
        )
        try:
            if hasattr(client, "set"):
                await client.set(
                    owner_marker, "1", ex=int(max(1, self._lease_seconds * 2))
                )
            yield
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            try:
                if hasattr(client, "delete"):
                    await client.delete(owner_marker)
                await lock.release()
            except LockError:
                raise ConflictError("Se perdió el bloqueo de la publicación") from None