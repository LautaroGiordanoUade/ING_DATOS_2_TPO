from copy import deepcopy
from uuid import UUID

import pytest

from app.application.ports import ConfigurableFailureInjector
from app.application.services import (
    CompensationService,
    OperationContext,
    OperationStatus,
    OperationStep,
)


class FakeOperationLog:
    def __init__(self) -> None:
        self.items: dict[UUID, OperationContext] = {}

    async def save(self, operation: OperationContext) -> None:
        self.items[operation.operation_id] = deepcopy(operation)

    async def get(self, operation_id: UUID) -> OperationContext | None:
        return self.items.get(operation_id)

    async def pending(
        self, operation_types: tuple[str, ...] | None = None
    ) -> list[OperationContext]:
        return [
            deepcopy(op)
            for op in self.items.values()
            if op.status
            in (OperationStatus.PENDING, OperationStatus.RUNNING, OperationStatus.COMPENSATING)
            and (operation_types is None or op.operation_type in operation_types)
        ]


@pytest.mark.asyncio
async def test_completed_steps_are_compensated_in_reverse_order() -> None:
    events: list[str] = []
    log = FakeOperationLog()
    service = CompensationService(log, ConfigurableFailureInjector("second"))

    async def first() -> None:
        events.append("first")

    async def compensate_first() -> None:
        events.append("undo-first")

    async def second() -> None:
        events.append("second")

    operation = OperationContext("test")
    with pytest.raises(RuntimeError, match="second"):
        await service.execute(
            operation,
            (
                OperationStep("first", first, compensate_first),
                OperationStep("second", second),
            ),
        )

    assert events == ["first", "undo-first"]
    assert operation.status is OperationStatus.COMPENSATED
    assert operation.completed_steps == ["first"]
