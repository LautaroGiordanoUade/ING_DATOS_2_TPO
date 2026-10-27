from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from app.application.services.operation import OperationContext


class OperationLogRepository(Protocol):
    async def save(self, operation: OperationContext) -> None: ...
    async def get(self, operation_id: UUID) -> OperationContext | None: ...
    async def pending(
        self, operation_types: tuple[str, ...] | None = None
    ) -> list[OperationContext]: ...
