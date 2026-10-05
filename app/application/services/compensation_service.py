import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from app.application.ports.failure_injector import FailureInjector
from app.application.ports.operation_log import OperationLogRepository
from app.application.services.operation import OperationContext, OperationStatus

type AsyncAction = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class OperationStep:
    name: str
    execute: AsyncAction
    compensate: AsyncAction | None = None


class CompensationService:
    def __init__(
        self,
        operation_log: OperationLogRepository,
        failure_injector: FailureInjector,
    ) -> None:
        self._operation_log = operation_log
        self._failure_injector = failure_injector
        self._logger = logging.getLogger(__name__)

    async def execute(
        self, operation: OperationContext, steps: Sequence[OperationStep]
    ) -> OperationContext:
        operation.status = OperationStatus.RUNNING
        await self._operation_log.save(operation)
        completed: list[OperationStep] = []
        try:
            for step in steps:
                operation.current_step = step.name
                operation.touch()
                await self._operation_log.save(operation)
                await self._failure_injector.checkpoint(step.name)
                await step.execute()
                completed.append(step)
                operation.completed_steps.append(step.name)
                operation.touch()
                await self._operation_log.save(operation)
        except Exception as exc:
            operation.error = str(exc)
            await self._compensate(operation, completed)
            raise
        operation.current_step = None
        operation.status = OperationStatus.COMPLETED
        operation.touch()
        await self._operation_log.save(operation)
        return operation

    async def _compensate(
        self, operation: OperationContext, completed: Sequence[OperationStep]
    ) -> None:
        if not completed:
            operation.status = OperationStatus.FAILED
            operation.touch()
            await self._operation_log.save(operation)
            return
        operation.status = OperationStatus.COMPENSATING
        operation.touch()
        await self._operation_log.save(operation)
        compensation_failed = False
        for step in reversed(completed):
            if step.compensate is None:
                continue
            try:
                await step.compensate()
            except Exception:
                compensation_failed = True
                self._logger.exception("Compensation failed", extra={"step": step.name})
        operation.status = (
            OperationStatus.FAILED if compensation_failed else OperationStatus.COMPENSATED
        )
        operation.touch()
        await self._operation_log.save(operation)

