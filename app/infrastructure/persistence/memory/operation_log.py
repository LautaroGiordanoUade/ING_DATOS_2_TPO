from copy import deepcopy
from uuid import UUID

from app.application.services.operation import OperationContext, OperationStatus


class InMemoryOperationLogRepository:
    """Development/test adapter. Production storage is intentionally a TODO(TP)."""

    def __init__(self) -> None:
        self._operations: dict[UUID, OperationContext] = {}

    async def save(self, operation: OperationContext) -> None:
        self._operations[operation.operation_id] = deepcopy(operation)

    async def get(self, operation_id: UUID) -> OperationContext | None:
        operation = self._operations.get(operation_id)
        return deepcopy(operation) if operation else None

    async def pending(
        self, operation_types: tuple[str, ...] | None = None
    ) -> list[OperationContext]:
        return [
            deepcopy(op)
            for op in self._operations.values()
            if op.status
            in (
                OperationStatus.PENDING,
                OperationStatus.RUNNING,
                OperationStatus.COMPENSATING,
            )
            and (operation_types is None or op.operation_type in operation_types)
        ]
