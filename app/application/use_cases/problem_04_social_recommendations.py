from uuid import UUID

from app.core.exceptions import FeatureNotImplementedError
from app.domain.repositories import SocialGraphRepository, UserRepository


class SocialRecommendationsUseCase:
    def __init__(self, graph: SocialGraphRepository, users: UserRepository) -> None:
        self._graph = graph
        self._users = users

    async def mutual_friends(self, user_id: UUID, other_user_id: UUID) -> tuple[UUID, ...]:
        return await self._graph.get_mutual_friends(user_id, other_user_id)

    async def recommendations(self, user_id: UUID) -> tuple[UUID, ...]:
        # TODO(TP): Filtrar suspendidos desde MongoDB sin degradar a N+1.
        # TODO(TP): Justificar score de segundo grado/intereses y máximo 10.
        raise FeatureNotImplementedError("Problema 4: recomendaciones")

