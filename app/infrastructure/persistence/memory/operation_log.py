from copy import deepcopy
from uuid import UUID

from app.application.services.operation import OperationContext


class InMemoryOperationLogRepository:
    """Development/test adapter. Production storage is intentionally a TODO(TP)."""

    def __init__(self) -> None:
        self._operations: dict[UUID, OperationContext] = {}

    async def save(self, operation: OperationContext) -> None:
        self._operations[operation.operation_id] = deepcopy(operation)

    async def get(self, operation_id: UUID) -> OperationContext | None:
        operation = self._operations.get(operation_id)
        return deepcopy(operation) if operation else None

