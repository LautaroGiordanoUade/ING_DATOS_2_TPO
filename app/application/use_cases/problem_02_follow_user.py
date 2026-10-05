from uuid import UUID

from app.application.services import CompensationService
from app.core.exceptions import FeatureNotImplementedError, InvalidOperationError
from app.domain.repositories import (
    CounterRepository,
    FeedRepository,
    SocialGraphRepository,
    UserRepository,
)


class FollowUserUseCase:
    def __init__(
        self,
        users: UserRepository,
        graph: SocialGraphRepository,
        counters: CounterRepository,
        feeds: FeedRepository,
        compensation: CompensationService,
    ) -> None:
        self._users = users
        self._graph = graph
        self._counters = counters
        self._feeds = feeds
        self._compensation = compensation

    async def follow(self, user_id: UUID, followed_user_id: UUID) -> None:
        if user_id == followed_user_id:
            raise InvalidOperationError("Un usuario no puede seguirse a sí mismo")
        # TODO(TP): Resolver cuenta privada, duplicados, compensación, contadores y feed.
        raise FeatureNotImplementedError("Problema 2: follow")

    async def unfollow(self, user_id: UUID, followed_user_id: UUID) -> None:
        # TODO(TP): Implementar unfollow idempotente y sus efectos derivados.
        raise FeatureNotImplementedError("Problema 2: unfollow")

