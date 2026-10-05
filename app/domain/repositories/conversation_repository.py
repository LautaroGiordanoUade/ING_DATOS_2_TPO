from typing import Protocol
from uuid import UUID

from app.domain.entities import Conversation


class ConversationRepository(Protocol):
    async def get(self, conversation_id: UUID) -> Conversation | None: ...
    async def list_active_for_user(self, user_id: UUID) -> tuple[Conversation, ...]: ...

