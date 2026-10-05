from typing import Protocol
from uuid import UUID

from app.domain.entities import Message


class MessageRepository(Protocol):
    async def create(self, message: Message) -> Message: ...
    async def delete(self, message_id: UUID) -> None: ...
    async def mark_read(self, message_id: UUID, participant_id: UUID) -> None: ...

