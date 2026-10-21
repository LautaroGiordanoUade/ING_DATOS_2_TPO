import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.application.ports.reaction_lock import ReactionLock
from app.application.services import (
    CompensationService,
    IdempotencyService,
    OperationContext,
    OperationStatus,
    OperationStep,
)
from app.application.services.idempotency_service import IdempotencyConflictError
from app.core.exceptions import (
    ConflictError,
    InvalidOperationError,
    ResourceNotFoundError,
)
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.entities import Comment, Post, Reaction
from app.domain.entities.models import ModerationStatus
from app.domain.repositories import (
    CommentRepository,
    CounterRepository,
    NotificationRepository,
    PostRepository,
    ReactionRepository,
    UserRepository,
)


@dataclass(slots=True)
class _ReactionState:
    previous: Reaction | None = None
    wrote_mongo: bool = False
    counted: bool = False
    notified: bool = False


@dataclass(slots=True)
class _RemovalState:
    removed: Reaction | None = None
    attempted_delete: bool = False
    counted: bool = False


class InteractWithPostUseCase:
    def __init__(
        self,
        posts: PostRepository,
        reactions: ReactionRepository,
        comments: CommentRepository,
        counters: CounterRepository,
        notifications: NotificationRepository,
        compensation: CompensationService,
        idempotency: IdempotencyService | None = None,
        reaction_lock: ReactionLock | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self._posts = posts
        self._reactions = reactions
        self._comments = comments
        self._counters = counters
        self._notifications = notifications
        self._compensation = compensation
        self._idempotency = idempotency
        self._reaction_lock = reaction_lock
        self._users = users

    async def _get_active_post(self, post_id: UUID) -> Post:
        post = await self._posts.get(post_id)
        if post is None:
            raise ResourceNotFoundError("Publicación no encontrada")
        if post.moderation_status == ModerationStatus.HIDDEN:
            raise InvalidOperationError("La publicación no está disponible")
        return post

    async def _check_actor(self, user_id: UUID) -> None:
        if self._users is not None and await self._users.is_suspended(user_id):
            raise ConflictError("Suspended accounts cannot interact")

    async def _reconcile_reaction_counter(self, post_id: UUID, fallback_delta: int) -> None:
        count_fn = getattr(self._reactions, "count_for_post", None)
        set_fn = getattr(self._counters, "set_value", None)
        if callable(count_fn) and callable(set_fn):
            total = await count_fn(post_id)
            if isinstance(total, int):
                await set_fn(POST_REACTIONS, post_id, total)
                return
        if fallback_delta != 0:
            await self._counters.increment(POST_REACTIONS, post_id, fallback_delta)

    async def _reconcile_comment_counter(self, post_id: UUID, fallback_delta: int) -> None:
        count_fn = getattr(self._comments, "count_for_post", None)
        set_fn = getattr(self._counters, "set_value", None)
        if callable(count_fn) and callable(set_fn):
            total = await count_fn(post_id)
            if isinstance(total, int):
                await set_fn(POST_COMMENTS, post_id, total)
                return
        if fallback_delta != 0:
            await self._counters.increment(POST_COMMENTS, post_id, fallback_delta)

    @staticmethod
    def _comment_fingerprint(comment: Comment) -> str:
        raw = f"{comment.post_id}:{comment.user_id}:{comment.text}".encode()
        return hashlib.sha256(raw).hexdigest()

    async def react(self, reaction: Reaction) -> OperationContext:
        await self._check_actor(reaction.user_id)
        if self._reaction_lock is None:
            raise RuntimeError("ReactionLock es obligatorio para modificar reacciones")
        async with self._reaction_lock.hold(reaction.post_id):
            return await self._react(reaction)

    async def _react(self, reaction: Reaction) -> OperationContext:
        post = await self._get_active_post(reaction.post_id)
        state = _ReactionState()
        event_id = reaction.id

        async def save_reaction() -> None:
            state.wrote_mongo = True
            state.previous = await self._reactions.upsert(reaction)

        async def restore_reaction() -> None:
            if not state.wrote_mongo:
                return
            if state.previous is None:
                await self._reactions.delete_for_user(reaction.post_id, reaction.user_id)
            else:
                await self._reactions.upsert(state.previous)

        async def count_reaction() -> None:
            if state.previous is None:
                state.counted = True
                await self._counters.increment(POST_REACTIONS, reaction.post_id, 1)

        async def uncount_reaction() -> None:
            if state.counted:
                await self._reconcile_reaction_counter(reaction.post_id, -1)

        async def notify_author() -> None:
            if state.previous is None and post.user_id != reaction.user_id:
                state.notified = True
                await self._notifications.publish(
                    post.user_id,
                    {
                        "event_id": str(event_id),
                        "type": "reaction",
                        "post_id": str(post.id),
                        "actor_id": str(reaction.user_id),
                        "kind": reaction.kind,
                    },
                )

        async def revoke_notification() -> None:
            if state.notified:
                await self._notifications.revoke(post.user_id, event_id)

        operation = OperationContext(operation_type="problem_05_react")
        return await self._compensation.execute(
            operation,
            [
                OperationStep(
                    "mongo_upsert_reaction",
                    save_reaction,
                    restore_reaction,
                    compensate_on_failure=True,
                ),
                OperationStep(
                    "redis_increment_reaction_counter",
                    count_reaction,
                    uncount_reaction,
                    compensate_on_failure=True,
                ),
                OperationStep(
                    "redis_publish_notification",
                    notify_author,
                    revoke_notification,
                    compensate_on_failure=True,
                ),
            ],
        )

    async def remove_reaction(self, post_id: UUID, user_id: UUID) -> OperationContext:
        await self._check_actor(user_id)
        if self._reaction_lock is None:
            raise RuntimeError("ReactionLock es obligatorio para modificar reacciones")
        async with self._reaction_lock.hold(post_id):
            return await self._remove_reaction(post_id, user_id)

    async def _remove_reaction(self, post_id: UUID, user_id: UUID) -> OperationContext:
        await self._get_active_post(post_id)
        state = _RemovalState()

        async def delete_reaction() -> None:
            state.attempted_delete = True
            state.removed = await self._reactions.delete_for_user(post_id, user_id)

        async def restore_reaction() -> None:
            if state.removed is not None:
                await self._reactions.upsert(state.removed)

        async def uncount_reaction() -> None:
            if state.removed is not None:
                state.counted = True
                await self._counters.increment(POST_REACTIONS, post_id, -1)

        async def recount_reaction() -> None:
            if state.counted:
                await self._reconcile_reaction_counter(post_id, 1)

        operation = OperationContext(operation_type="problem_05_remove_reaction")
        return await self._compensation.execute(
            operation,
            [
                OperationStep(
                    "mongo_delete_reaction",
                    delete_reaction,
                    restore_reaction,
                    compensate_on_failure=True,
                ),
                OperationStep(
                    "redis_decrement_reaction_counter",
                    uncount_reaction,
                    recount_reaction,
                    compensate_on_failure=True,
                ),
            ],
        )

    async def comment(
        self, comment: Comment, idempotency_key: str | None = None
    ) -> OperationContext:
        await self._check_actor(comment.user_id)
        post = await self._get_active_post(comment.post_id)

        scoped_key: str | None = None
        fingerprint = self._comment_fingerprint(comment)
        if idempotency_key is not None and self._idempotency is not None:
            scoped_key = f"comment:{comment.user_id}:{idempotency_key}"
            try:
                previous = await self._idempotency.begin(
                    scoped_key, "problem_05_comment", fingerprint=fingerprint
                )
            except IdempotencyConflictError as exc:
                raise ConflictError(str(exc)) from exc
            if previous is not None:
                return OperationContext(
                    operation_type="problem_05_comment",
                    operation_id=UUID(previous.decode()),
                    status=OperationStatus.COMPLETED,
                )

        wrote_comment = False
        counted_comment = False
        notified_author = False

        async def save_comment() -> None:
            nonlocal wrote_comment
            wrote_comment = True
            await self._comments.create(comment)

        async def delete_comment() -> None:
            if wrote_comment:
                await self._comments.delete(comment.id)

        async def count_comment() -> None:
            nonlocal counted_comment
            counted_comment = True
            await self._counters.increment(POST_COMMENTS, comment.post_id, 1)

        async def uncount_comment() -> None:
            if counted_comment:
                await self._reconcile_comment_counter(comment.post_id, -1)

        async def notify_author() -> None:
            nonlocal notified_author
            if post.user_id != comment.user_id:
                notified_author = True
                await self._notifications.publish(
                    post.user_id,
                    {
                        "event_id": str(comment.id),
                        "type": "comment",
                        "post_id": str(post.id),
                        "actor_id": str(comment.user_id),
                        "comment_id": str(comment.id),
                    },
                )

        async def revoke_notification() -> None:
            if notified_author and post.user_id != comment.user_id:
                await self._notifications.revoke(post.user_id, comment.id)

        operation = OperationContext(operation_type="problem_05_comment")
        try:
            await self._compensation.execute(
                operation,
                [
                    OperationStep(
                        "mongo_create_comment",
                        save_comment,
                        delete_comment,
                        compensate_on_failure=True,
                    ),
                    OperationStep(
                        "redis_increment_comment_counter",
                        count_comment,
                        uncount_comment,
                        compensate_on_failure=True,
                    ),
                    OperationStep(
                        "redis_publish_notification",
                        notify_author,
                        revoke_notification,
                        compensate_on_failure=True,
                    ),
                ],
            )
        except Exception:
            if scoped_key is not None and self._idempotency is not None:
                await self._idempotency.release(scoped_key)
            raise
        if scoped_key is not None and self._idempotency is not None:
            await self._idempotency.complete(
                scoped_key,
                str(operation.operation_id).encode(),
                fingerprint=fingerprint,
            )
        return operation