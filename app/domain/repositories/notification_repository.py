from typing import Protocol
from uuid import UUID


class NotificationRepository(Protocol):
    async def publish(self, recipient_id: UUID, event: dict[str, object]) -> None: ...
    async def revoke(self, recipient_id: UUID, event_id: UUID) -> None: ...

