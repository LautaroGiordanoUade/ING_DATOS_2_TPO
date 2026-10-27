import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.application.ports.operation_log import OperationLogRepository
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
    snapshot_known: bool = False


@dataclass(slots=True)
class _RemovalState:
    removed: Reaction | None = None
    attempted_delete: bool = False
    counted: bool = False
    snapshot_known: bool = False


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
        operation_log: OperationLogRepository | None = None,
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
        self._operation_log = operation_log or getattr(compensation, "_operation_log", None)

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

    async def own_reaction(self, post_id: UUID, user_id: UUID) -> Reaction | None:
        await self._get_active_post(post_id)
        return await self._reactions.get_for_user(post_id, user_id)

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

    async def _repair_counters(self, post_id: UUID) -> None:
        # Called under the common post lock before any new writer.
        # Resolves any crashed or pending operation for this post first,
        # ensuring orphaned notifications and reserved idempotency keys are recovered.
        await self._recover_pending_locked(post_id)
        await self._reconcile_reaction_counter(post_id, 0)
        await self._reconcile_comment_counter(post_id, 0)

    async def react(self, reaction: Reaction) -> OperationContext:
        await self._check_actor(reaction.user_id)
        if self._reaction_lock is None:
            raise RuntimeError("ReactionLock es obligatorio para modificar reacciones")
        async with self._reaction_lock.hold(reaction.post_id):
            return await self._react(reaction)

    async def _react(self, reaction: Reaction) -> OperationContext:
        post = await self._get_active_post(reaction.post_id)
        await self._repair_counters(reaction.post_id)
        state = _ReactionState()
        event_id = reaction.id

        operation = OperationContext(
            operation_type="problem_05_react",
            metadata={
                "post_id": str(reaction.post_id),
                "user_id": str(reaction.user_id),
                "author_id": str(post.user_id),
                "event_id": str(event_id),
                "kind": reaction.kind,
            },
        )

        async def save_reaction() -> None:
            snapshot = await self._reactions.get_for_user(reaction.post_id, reaction.user_id)
            if snapshot is None or isinstance(snapshot, Reaction):
                state.previous, state.snapshot_known = snapshot, True
            state.wrote_mongo = True
            previous = await self._reactions.upsert(reaction)
            if not state.snapshot_known and isinstance(previous, Reaction):
                state.previous = previous
            if state.previous is not None:
                operation.metadata["previous_id"] = str(state.previous.id)
                operation.metadata["previous_kind"] = state.previous.kind

        async def restore_reaction() -> None:
            if not state.wrote_mongo:
                return
            if state.previous is None:
                await self._reactions.delete_for_user(reaction.post_id, reaction.user_id)
            else:
                await self._reactions.upsert(state.previous)
            # Reverse order compensation reaches Mongo last. Only now is its
            # count the final rollback state, including an uncertain Redis write.
            await self._reconcile_reaction_counter(reaction.post_id, -1 if state.counted else 0)

        async def count_reaction() -> None:
            if state.previous is None:
                state.counted = True
                await self._counters.increment(POST_REACTIONS, reaction.post_id, 1)

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
        await self._repair_counters(post_id)
        state = _RemovalState()

        operation = OperationContext(
            operation_type="problem_05_remove_reaction",
            metadata={
                "post_id": str(post_id),
                "user_id": str(user_id),
            },
        )

        async def delete_reaction() -> None:
            snapshot = await self._reactions.get_for_user(post_id, user_id)
            if snapshot is None or isinstance(snapshot, Reaction):
                state.removed, state.snapshot_known = snapshot, True
            state.attempted_delete = True
            removed = await self._reactions.delete_for_user(post_id, user_id)
            if not state.snapshot_known and isinstance(removed, Reaction):
                state.removed = removed
            if state.removed is not None:
                operation.metadata["removed_id"] = str(state.removed.id)
                operation.metadata["removed_kind"] = state.removed.kind

        async def restore_reaction() -> None:
            if not state.attempted_delete:
                return
            if state.removed is not None:
                await self._reactions.upsert(state.removed)
            await self._reconcile_reaction_counter(post_id, 1 if state.counted else 0)

        async def uncount_reaction() -> None:
            if state.removed is not None:
                state.counted = True
                await self._counters.increment(POST_REACTIONS, post_id, -1)

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
                    compensate_on_failure=True,
                ),
            ],
        )

    async def comment(
        self, comment: Comment, idempotency_key: str | None = None
    ) -> OperationContext:
        await self._check_actor(comment.user_id)
        if self._reaction_lock is None:
            raise RuntimeError("ReactionLock es obligatorio para modificar comentarios")
        async with self._reaction_lock.hold(comment.post_id):
            return await self._comment(comment, idempotency_key)

    async def _comment(self, comment: Comment, idempotency_key: str | None) -> OperationContext:
        post = await self._get_active_post(comment.post_id)
        await self._repair_counters(comment.post_id)

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
                await self._reconcile_comment_counter(comment.post_id, -1 if counted_comment else 0)

        async def count_comment() -> None:
            nonlocal counted_comment
            counted_comment = True
            await self._counters.increment(POST_COMMENTS, comment.post_id, 1)

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

        operation = OperationContext(
            operation_type="problem_05_comment",
            metadata={
                "post_id": str(comment.post_id),
                "user_id": str(comment.user_id),
                "author_id": str(post.user_id),
                "comment_id": str(comment.id),
                "text": comment.text,
                "scoped_key": scoped_key,
                "fingerprint": fingerprint,
            },
        )
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

    async def recover_pending(self, post_id: UUID | None = None) -> list[OperationContext]:
        if self._operation_log is None or not hasattr(self._operation_log, "pending"):
            return []
        pending_ops = await self._operation_log.pending(
            ("problem_05_react", "problem_05_remove_reaction", "problem_05_comment")
        )
        if post_id is not None:
            pending_ops = [op for op in pending_ops if op.metadata.get("post_id") == str(post_id)]
        recovered: list[OperationContext] = []
        for op in pending_ops:
            recovered.append(await self.recover_operation(op))
        return recovered

    async def _recover_pending_locked(self, post_id: UUID) -> list[OperationContext]:
        if self._operation_log is None or not hasattr(self._operation_log, "pending"):
            return []
        pending_ops = await self._operation_log.pending(
            ("problem_05_react", "problem_05_remove_reaction", "problem_05_comment")
        )
        recovered: list[OperationContext] = []
        for op in pending_ops:
            if op.metadata.get("post_id") == str(post_id):
                recovered.append(await self._recover_operation_locked(op, post_id))
        return recovered

    async def recover_operation(self, operation: OperationContext) -> OperationContext:
        if operation.status in (OperationStatus.COMPLETED, OperationStatus.FAILED):
            return operation
        post_id_str = operation.metadata.get("post_id")
        if not post_id_str:
            return operation
        post_id = UUID(post_id_str)

        if self._reaction_lock is None:
            raise RuntimeError("ReactionLock es obligatorio para recuperar operaciones")

        async with self._reaction_lock.hold(post_id):
            return await self._recover_operation_locked(operation, post_id)

    async def _recover_operation_locked(
        self, operation: OperationContext, post_id: UUID
    ) -> OperationContext:
        if operation.status in (OperationStatus.COMPLETED, OperationStatus.FAILED):
            return operation

        if operation.operation_type == "problem_05_react":
            user_id = UUID(operation.metadata["user_id"])
            author_id = UUID(operation.metadata["author_id"])
            event_id = UUID(operation.metadata["event_id"])
            kind = str(operation.metadata.get("kind", "like"))
            previous_kind = operation.metadata.get("previous_kind")
            previous_id = operation.metadata.get("previous_id")

            if operation.status == OperationStatus.COMPENSATING:
                current = await self._reactions.get_for_user(post_id, user_id)
                if previous_kind is not None:
                    restored_id = UUID(str(previous_id)) if previous_id else event_id
                    await self._reactions.upsert(
                        Reaction(
                            id=restored_id,
                            post_id=post_id,
                            user_id=user_id,
                            kind=str(previous_kind),
                        )
                    )
                elif current is not None and current.id == event_id:
                    await self._reactions.delete_for_user(post_id, user_id)
                await self._reconcile_reaction_counter(post_id, 0)
                if previous_kind is None and author_id != user_id:
                    await self._notifications.revoke(author_id, event_id)
                operation.status = OperationStatus.COMPENSATED
            else:
                current = await self._reactions.get_for_user(post_id, user_id)
                if current is not None and current.id == event_id:
                    await self._reconcile_reaction_counter(post_id, 0)
                    if previous_kind is None and author_id != user_id:
                        await self._notifications.publish(
                            author_id,
                            {
                                "event_id": str(event_id),
                                "type": "reaction",
                                "post_id": str(post_id),
                                "actor_id": str(user_id),
                                "kind": kind,
                            },
                        )
                    operation.status = OperationStatus.COMPLETED
                elif current is not None and current.kind == kind:
                    await self._reconcile_reaction_counter(post_id, 0)
                    operation.status = OperationStatus.COMPLETED
                else:
                    await self._reconcile_reaction_counter(post_id, 0)
                    operation.status = OperationStatus.FAILED

        elif operation.operation_type == "problem_05_remove_reaction":
            user_id = UUID(operation.metadata["user_id"])
            removed_kind = operation.metadata.get("removed_kind")
            removed_id = operation.metadata.get("removed_id")
            current = await self._reactions.get_for_user(post_id, user_id)

            if operation.status == OperationStatus.COMPENSATING:
                if current is None and removed_kind is not None:
                    restored_id = UUID(str(removed_id)) if removed_id else operation.operation_id
                    await self._reactions.upsert(
                        Reaction(
                            id=restored_id,
                            post_id=post_id,
                            user_id=user_id,
                            kind=str(removed_kind),
                        )
                    )
                await self._reconcile_reaction_counter(post_id, 0)
                operation.status = OperationStatus.COMPENSATED
            else:
                await self._reconcile_reaction_counter(post_id, 0)
                operation.status = (
                    OperationStatus.COMPLETED if current is None else OperationStatus.FAILED
                )

        elif operation.operation_type == "problem_05_comment":
            user_id = UUID(operation.metadata["user_id"])
            author_id = UUID(operation.metadata["author_id"])
            comment_id = UUID(operation.metadata["comment_id"])
            scoped_key = operation.metadata.get("scoped_key")
            fingerprint = operation.metadata.get("fingerprint")

            has_comment = False
            if hasattr(self._comments, "get"):
                has_comment = (await self._comments.get(comment_id)) is not None
            elif hasattr(self._comments, "_collection"):
                has_comment = (
                    await self._comments._collection.find_one({"_id": str(comment_id)})
                ) is not None

            if operation.status == OperationStatus.COMPENSATING:
                if has_comment:
                    await self._comments.delete(comment_id)
                await self._reconcile_comment_counter(post_id, 0)
                if author_id != user_id:
                    await self._notifications.revoke(author_id, comment_id)
                if scoped_key and self._idempotency:
                    await self._idempotency.release(scoped_key)
                operation.status = OperationStatus.COMPENSATED
            else:
                if has_comment:
                    await self._reconcile_comment_counter(post_id, 0)
                    if author_id != user_id:
                        await self._notifications.publish(
                            author_id,
                            {
                                "event_id": str(comment_id),
                                "type": "comment",
                                "post_id": str(post_id),
                                "actor_id": str(user_id),
                                "comment_id": str(comment_id),
                            },
                        )
                    if scoped_key and self._idempotency:
                        await self._idempotency.complete(
                            scoped_key,
                            str(operation.operation_id).encode(),
                            fingerprint=fingerprint,
                        )
                    operation.status = OperationStatus.COMPLETED
                else:
                    if scoped_key and self._idempotency:
                        await self._idempotency.release(scoped_key)
                    await self._reconcile_comment_counter(post_id, 0)
                    operation.status = OperationStatus.FAILED

        operation.touch()
        if self._operation_log:
            await self._operation_log.save(operation)
        return operation
