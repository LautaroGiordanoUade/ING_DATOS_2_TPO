from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID


class ConversationLock(Protocol):
    def hold(
        self,
        conversation_id: UUID,
    ) -> AbstractAsyncContextManager[None]:
        ...