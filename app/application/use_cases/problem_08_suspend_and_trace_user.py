from dataclasses import asdict
from uuid import UUID, uuid4, uuid5

from app.application.ports.accounts import AccountGraph, AccountStore, AccountViews
from app.application.services.account_job import AccountJob
from app.core.exceptions import ConflictError, InvalidOperationError
from app.domain.repositories import ConversationRepository, PostRepository


class SuspendAndTraceUserUseCase:
    def __init__(
        self,
        store: AccountStore,
        graph: AccountGraph,
        views: AccountViews,
        posts: PostRepository,
        conversations: ConversationRepository,
    ) -> None:
        self._store, self._graph, self._views = store, graph, views
        self._posts, self._conversations = posts, conversations

    async def suspend_user(
        self,
        user_id: UUID,
        reason: str,
        actor_id: UUID,
        key: str | None = None,
        fail_at: str | None = None,
        action: str = "suspend",
    ) -> AccountJob:
        if user_id == actor_id:
            raise ConflictError("Self-suspension/reactivation is not allowed")
        if action not in ("suspend", "reactivate"):
            raise InvalidOperationError("Invalid account action")
        if not reason.strip() or len(reason) > 1000:
            raise InvalidOperationError("Reason must contain 1 to 1000 characters")
        if key is not None and not 1 <= len(key) <= 200:
            raise InvalidOperationError("Idempotency-Key must contain 1 to 200 characters")
        allowed = {
            "mongo_suspend",
            "redis_close_presence",
            "neo4j_suspend",
            "redis_remove_posts",
            "redis_restore_posts",
            "neo4j_reactivate",
            "redis_reactivate",
            "mongo_reactivate",
        }
        if fail_at is not None and fail_at not in allowed:
            raise InvalidOperationError("Unknown failure step")
        await self._store.user(user_id)
        return await self._store.enqueue(
            AccountJob(
                operation_id=uuid4() if key is None else uuid5(user_id, f"account:{action}:{key}"),
                user_id=user_id,
                actor_id=actor_id,
                action=action,
                reason=reason.strip(),
                fail_at=fail_at,
            ),
            keyed=key is not None,
        )

    async def trace_user(self, user_id: UUID) -> dict[str, object]:
        user = await self._store.user(user_id)
        relationships = await self._graph.trace_relationships(user_id)
        posts = await self._posts.list_recent_by_user(user_id, 100)
        conversations = await self._conversations.list_active_for_user(user_id)
        states = await self._store.trace_posts(user_id)
        for state in states:
            state["suspension_hidden"] = user.account_status == "suspended"
            state["publicly_visible"] = (
                user.account_status == "active"
                and state.get("moderation_status") != "hidden"
                and state.get("publication_state") != "pending"
                and state.get("visibility", "public") == "public"
            )
        return {
            "user_id": user_id,
            "profile": asdict(user),
            "relationships": relationships,
            "recent_posts": [asdict(post) for post in posts],
            "active_conversations": [asdict(conversation) for conversation in conversations],
            "post_states": states,
            "presence": user.account_status == "active" and await self._views.presence(user_id),
            "account_history": await self._store.history(user_id),
        }

    async def job(self, operation_id: UUID) -> AccountJob:
        return await self._store.get(operation_id)

    async def retry(self, operation_id: UUID) -> AccountJob:
        return await self._store.retry(operation_id)

    async def history(self, user_id: UUID) -> list[dict[str, object]]:
        await self._store.user(user_id)
        return await self._store.history(user_id)

    async def heartbeat(self, user_id: UUID) -> None:
        await self._views.heartbeat(user_id)

    async def presence(self, user_id: UUID) -> bool:
        user = await self._store.user(user_id)
        return user.account_status == "active" and await self._views.presence(user_id)
