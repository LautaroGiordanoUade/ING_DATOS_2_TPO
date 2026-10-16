from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import ModerationReport, User


class MongoUserRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def get(self, user_id: UUID) -> User | None:
        # TODO(TP): Implementar consulta MongoDB de usuario y definir visibilidad de estados.
        raise FeatureNotImplementedError("MongoUserRepository.get")

    async def create(self, user: User) -> User:
        # TODO(TP): Implementar alta en MongoDB y tratamiento de unicidad.
        raise FeatureNotImplementedError("MongoUserRepository.create")

    async def update_account_status(self, user_id: UUID, status: str) -> None:
        # TODO(TP): Implementar actualización en MongoDB del estado de cuenta.
        raise FeatureNotImplementedError("MongoUserRepository.update_account_status")


class MongoModerationRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def create_report(self, report: ModerationReport) -> ModerationReport:
        # TODO(TP): Persistir el reporte con las reglas del workflow de moderación.
        raise FeatureNotImplementedError("MongoModerationRepository.create_report")

    async def resolve_report(self, report_id: UUID, moderator_id: UUID, status: str) -> None:
        # TODO(TP): Resolver el reporte en MongoDB.
        raise FeatureNotImplementedError("MongoModerationRepository.resolve_report")

    async def reverse_resolution(self, report_id: UUID) -> None:
        # TODO(TP): Definir e implementar la reversión del workflow.
        raise FeatureNotImplementedError("MongoModerationRepository.reverse_resolution")

