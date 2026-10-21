from typing import Literal
from uuid import UUID, uuid4, uuid5

from app.application.ports.follows import FollowGraph, FollowStore, FollowViews
from app.application.services.follow_job import FollowJob
from app.core.exceptions import InvalidOperationError
from app.domain.repositories import UserRepository


class FollowUserUseCase:
    def __init__(
        self, users: UserRepository, graph: FollowGraph, store: FollowStore, views: FollowViews
    ) -> None:
        self._users, self._graph, self._store, self._views = users, graph, store, views

    async def _enqueue(
        self,
        follower_id: UUID,
        followed_id: UUID,
        actor_id: UUID,
        action: Literal["follow", "unfollow", "approve"],
        key: str | None,
        fail_at: str | None,
    ) -> FollowJob:
        if follower_id == followed_id:
            raise InvalidOperationError("Un usuario no puede seguirse a si mismo")
        if key is not None and not 1 <= len(key) <= 200:
            raise InvalidOperationError("Idempotency-Key debe tener entre 1 y 200 caracteres")
        if fail_at is not None and fail_at not in {
            "neo4j_follow",
            "redis_follow_counters",
            "redis_follow_feed",
            "redis_feed_partial",
        }:
            raise InvalidOperationError("Paso de falla P2 desconocido")
        await self._store.validate_users(follower_id, followed_id)
        return await self._store.enqueue(
            FollowJob(
                operation_id=uuid4() if key is None else uuid5(actor_id, f"p2:{key}"),
                follower_id=follower_id,
                followed_id=followed_id,
                actor_id=actor_id,
                action=action,
                fail_at=fail_at,
            ),
            keyed=key is not None,
        )

    async def follow(
        self,
        user_id: UUID,
        followed_user_id: UUID,
        key: str | None = None,
        fail_at: str | None = None,
    ) -> FollowJob:
        return await self._enqueue(user_id, followed_user_id, user_id, "follow", key, fail_at)

    async def unfollow(
        self,
        user_id: UUID,
        followed_user_id: UUID,
        key: str | None = None,
        fail_at: str | None = None,
    ) -> FollowJob:
        return await self._enqueue(user_id, followed_user_id, user_id, "unfollow", key, fail_at)

    async def approve(
        self,
        follower_id: UUID,
        owner_id: UUID,
        key: str | None = None,
        fail_at: str | None = None,
    ) -> FollowJob:
        return await self._enqueue(follower_id, owner_id, owner_id, "approve", key, fail_at)

    async def job(self, operation_id: UUID) -> FollowJob:
        return await self._store.get(operation_id)

    async def retry(self, operation_id: UUID) -> FollowJob:
        return await self._store.retry(operation_id)

    async def requests(self, owner_id: UUID) -> tuple[UUID, ...]:
        return await self._users.active_ids(await self._graph.incoming_requests(owner_id))

    async def relationship(self, follower_id: UUID, author_id: UUID) -> dict[str, object]:
        active = await self._store.active_pair(follower_id, author_id)
        if active:
            return {
                "status": "processing",
                "operation_id": str(active.operation_id),
                "operation_status": active.status,
            }
        snapshot = await self._graph.follow_snapshot(follower_id, author_id)
        previous = snapshot["relationship"]
        return {"status": previous.get("status", "accepted") if previous else "none"}

    async def counts(self, user_id: UUID) -> dict[str, int]:
        await self._store.validate_users(user_id, user_id)
        await self._views.initialize_counts(user_id, await self._graph.follow_counts(user_id))
        return await self._views.counts(user_id)
