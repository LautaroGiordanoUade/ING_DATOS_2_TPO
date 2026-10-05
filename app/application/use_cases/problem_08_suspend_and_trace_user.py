from uuid import UUID

from app.application.dto import UserTrace
from app.application.services import CompensationService
from app.core.exceptions import FeatureNotImplementedError
from app.domain.repositories import (
    ConversationRepository,
    FeedRepository,
    PostRepository,
    SocialGraphRepository,
    UserRepository,
)


class SuspendAndTraceUserUseCase:
    def __init__(
        self,
        users: UserRepository,
        posts: PostRepository,
        graph: SocialGraphRepository,
        feeds: FeedRepository,
        conversations: ConversationRepository,
        compensation: CompensationService,
    ) -> None:
        self._users = users
        self._posts = posts
        self._graph = graph
        self._feeds = feeds
        self._conversations = conversations
        self._compensation = compensation

    async def suspend_user(self, user_id: UUID, reason: str) -> None:
        # TODO(TP): Coordinar estado SQL y efectos Mongo/Redis/Neo4j con compensaciones.
        raise FeatureNotImplementedError("Problema 8: suspensión")

    async def trace_user(self, user_id: UUID) -> UserTrace:
        # TODO(TP): Integrar realmente perfil, relaciones, posts y conversaciones.
        raise FeatureNotImplementedError("Problema 8: trazabilidad multi-motor")

