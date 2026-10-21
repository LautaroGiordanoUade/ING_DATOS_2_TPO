import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import LockError, RedisError

from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)


class RedisReactionLock:
    """One host/shared volume: OS lock is authoritative; Redis lease expires on crash.

    A suspended process keeps its OS lock, so an expired Redis lease cannot let
    a second writer overlap. Mongo-derived counters are repaired by the use case
    on entry; this lock alone does not recover notifications or pending jobs.
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
        self._directory = Path(
            os.getenv("P5_LOCK_DIRECTORY", str(Path.home() / "interaction-locks"))
        )

    @staticmethod
    def _file_lock(descriptor: int, release: bool = False) -> None:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK if release else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN if release else fcntl.LOCK_EX | fcntl.LOCK_NB)

    @asynccontextmanager
    async def _host_hold(self, post_id: UUID) -> AsyncIterator[None]:
        self._directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self._directory / f"{post_id}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
        acquired = False
        deadline = asyncio.get_running_loop().time() + self._blocking_timeout
        try:
            while not acquired:
                try:
                    self._file_lock(descriptor)
                    acquired = True
                except (BlockingIOError, PermissionError):
                    if asyncio.get_running_loop().time() >= deadline:
                        raise ConflictError(
                            "Otra interaccion usa esta publicacion; reintente"
                        ) from None
                    await asyncio.sleep(0.02)
            yield
        finally:
            if acquired:
                self._file_lock(descriptor, release=True)
            os.close(descriptor)

    async def _heartbeat(self, lock: Any, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await lock.reacquire()
            except RedisError:
                logger.warning("P5 Redis lease unavailable; shared host lock remains held")
                return

    @asynccontextmanager
    async def hold(self, post_id: UUID) -> AsyncIterator[None]:
        async with self._host_hold(post_id):
            async with self._redis_hold(post_id):
                yield

    @asynccontextmanager
    async def _redis_hold(self, post_id: UUID) -> AsyncIterator[None]:
        lock_name = f"lock:post_reactions:{post_id}"

        lock = self._client.lock(
            lock_name,
            timeout=self._lease_seconds,
            blocking_timeout=self._blocking_timeout,
            thread_local=False,
        )
        if not await lock.acquire():
            raise ConflictError("Hay otra reacción en curso para esta publicación; reintente")

        heartbeat_task = asyncio.create_task(
            self._heartbeat(lock, max(0.5, self._lease_seconds / 3))
        )
        try:
            yield
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            with contextlib.suppress(LockError):
                await lock.release()
