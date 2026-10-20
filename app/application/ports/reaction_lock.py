from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID


class ReactionLock(Protocol):
    def hold(self, post_id: UUID) -> AbstractAsyncContextManager[None]: ...
