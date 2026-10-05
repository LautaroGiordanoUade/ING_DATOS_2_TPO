from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.operation import OperationContext
from app.core.exceptions import FeatureNotImplementedError


class PostgresOperationLogRepository:
    """Production-oriented operation log adapter; SQL remains coursework."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, operation: OperationContext) -> None:
        # TODO(TP): Implementar upsert durable por operation_id y control concurrente.
        raise FeatureNotImplementedError("PostgresOperationLogRepository.save")

    async def get(self, operation_id: UUID) -> OperationContext | None:
        # TODO(TP): Implementar consulta programática del registro de operación.
        raise FeatureNotImplementedError("PostgresOperationLogRepository.get")

