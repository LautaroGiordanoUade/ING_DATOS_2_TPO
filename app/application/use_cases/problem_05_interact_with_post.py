from app.application.services import CompensationService
from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Comment, Reaction
from app.domain.repositories import (
    CommentRepository,
    CounterRepository,
    NotificationRepository,
    PostRepository,
    ReactionRepository,
)


class InteractWithPostUseCase:
    def __init__(
        self,
        posts: PostRepository,
        reactions: ReactionRepository,
        comments: CommentRepository,
        counters: CounterRepository,
        notifications: NotificationRepository,
        compensation: CompensationService,
    ) -> None:
        self._posts = posts
        self._reactions = reactions
        self._comments = comments
        self._counters = counters
        self._notifications = notifications
        self._compensation = compensation

    async def react(self, reaction: Reaction) -> None:
        # TODO(TP): Orquestar upsert único, delta atómico, notificación y compensación.
        raise FeatureNotImplementedError("Problema 5: reacción")

    async def comment(self, comment: Comment) -> None:
        # TODO(TP): Orquestar comentario, contador, notificación e idempotencia.
        raise FeatureNotImplementedError("Problema 5: comentario")
