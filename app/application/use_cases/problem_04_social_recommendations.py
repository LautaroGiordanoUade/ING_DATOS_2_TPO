from uuid import UUID

from app.domain.repositories import SocialGraphRepository, UserRepository


class SocialRecommendationsUseCase:
    def __init__(self, graph: SocialGraphRepository, users: UserRepository) -> None:
        self._graph = graph
        self._users = users

    async def mutual_friends(self, user_id: UUID, other_user_id: UUID) -> tuple[UUID, ...]:
        if user_id == other_user_id:
            return ()
        if await self._users.is_suspended(user_id) or await self._users.is_suspended(other_user_id):
            return ()
        candidates = await self._graph.get_mutual_friends(user_id, other_user_id)
        return await self._users.active_ids(candidates)

    async def recommendations(self, user_id: UUID) -> tuple[UUID, ...]:
        if await self._users.is_suspended(user_id):
            return ()
        candidates = await self._graph.get_suggested_accounts(user_id, 10)
        return await self._users.active_ids(candidates)
