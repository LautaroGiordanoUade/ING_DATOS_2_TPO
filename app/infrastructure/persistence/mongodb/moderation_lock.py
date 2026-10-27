import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from app.core.exceptions import ConflictError


class ModerationPostLock:
    """Serialize report insertion and Mongo moderation transitions on one shared host.

    API and worker mount the same interaction_locks volume. Do not unlink lock files:
    a waiter must always acquire the same inode, including after a process restart.
    """

    @staticmethod
    def _lock(descriptor: int, release: bool = False) -> None:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK if release else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN if release else fcntl.LOCK_EX | fcntl.LOCK_NB)

    @asynccontextmanager
    async def hold(self, post_id: UUID) -> AsyncIterator[None]:
        directory = Path(os.getenv("P7_LOCK_DIRECTORY", str(Path.home() / "interaction-locks")))
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        descriptor = os.open(directory / f"p7-{post_id}.lock", os.O_CREAT | os.O_RDWR, 0o600)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
        acquired = False
        deadline = asyncio.get_running_loop().time() + 5.0
        try:
            while not acquired:
                try:
                    self._lock(descriptor)
                    acquired = True
                except (BlockingIOError, PermissionError):
                    if asyncio.get_running_loop().time() >= deadline:
                        raise ConflictError(
                            "La publicación tiene otra operación en curso; reintente"
                        ) from None
                    await asyncio.sleep(0.02)
            yield
        finally:
            if acquired:
                self._lock(descriptor, release=True)
            os.close(descriptor)
