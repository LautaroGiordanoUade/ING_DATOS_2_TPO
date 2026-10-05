from uuid import UUID

from app.application.services import CompensationService
from app.core.exceptions import FeatureNotImplementedError
from app.domain.repositories import (
    CounterRepository,
    FeedRepository,
    ModerationRepository,
    PostRepository,
)


class ModeratePostUseCase:
    def __init__(
        self,
        moderation: ModerationRepository,
        posts: PostRepository,
        feeds: FeedRepository,
        counters: CounterRepository,
        compensation: CompensationService,
    ) -> None:
        self._moderation = moderation
        self._posts = posts
        self._feeds = feeds
        self._counters = counters
        self._compensation = compensation

    async def moderate_post(
        self, report_id: UUID, post_id: UUID, moderator_id: UUID, decision: str
    ) -> None:
        # TODO(TP): Definir orden multi-motor, ocultamiento, contadores y compensaciones.
        raise FeatureNotImplementedError("Problema 7: moderar publicación")

    async def reverse_moderation(self, report_id: UUID, post_id: UUID) -> None:
        # TODO(TP): Reconstruir feed/contadores sin introducir duplicados.
        raise FeatureNotImplementedError("Problema 7: revertir moderación")

