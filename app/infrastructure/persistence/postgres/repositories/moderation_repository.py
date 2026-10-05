from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import ModerationReport


class PostgresModerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_report(self, report: ModerationReport) -> ModerationReport:
        # TODO(TP): Persistir el reporte con las reglas del workflow de moderación.
        raise FeatureNotImplementedError("PostgresModerationRepository.create_report")

    async def resolve_report(self, report_id: UUID, moderator_id: UUID, status: str) -> None:
        # TODO(TP): Resolver el reporte de manera transaccional.
        raise FeatureNotImplementedError("PostgresModerationRepository.resolve_report")

    async def reverse_resolution(self, report_id: UUID) -> None:
        # TODO(TP): Definir e implementar la reversión del workflow.
        raise FeatureNotImplementedError("PostgresModerationRepository.reverse_resolution")

