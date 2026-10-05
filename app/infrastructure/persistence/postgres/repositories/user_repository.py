from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import User


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> User | None:
        # TODO(TP): Implementar SQL de consulta de usuario y definir visibilidad de estados.
        raise FeatureNotImplementedError("PostgresUserRepository.get")

    async def create(self, user: User) -> User:
        # TODO(TP): Implementar alta transaccional y tratamiento de unicidad.
        raise FeatureNotImplementedError("PostgresUserRepository.create")

    async def update_account_status(self, user_id: UUID, status: str) -> None:
        # TODO(TP): Implementar actualización transaccional del estado de cuenta.
        raise FeatureNotImplementedError("PostgresUserRepository.update_account_status")

