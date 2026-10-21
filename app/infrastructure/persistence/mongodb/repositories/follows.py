from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.application.services.follow_job import FollowJob
from app.core.exceptions import ConflictError, InvalidOperationError, ResourceNotFoundError
from app.domain.entities import User
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository


class MongoFollowStore:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._jobs = database["follow_jobs"]

    async def ensure_indexes(self) -> None:
        await self._jobs.create_index([("status", ASCENDING), ("created_at", ASCENDING)])
        # A failed recovery retains ownership. Counts of shared users cannot race.
        await self._jobs.create_index(
            [("participant_ids", ASCENDING)],
            unique=True,
            partialFilterExpression={"active": True},
            name="follow_active_participants",
        )

    async def validate_users(self, follower_id: UUID, followed_id: UUID) -> tuple[User, User]:
        repository = MongoUserRepository(self._database)
        follower, followed = await repository.get(follower_id), await repository.get(followed_id)
        if follower is None or followed is None:
            raise ResourceNotFoundError("Usuario no encontrado")
        if follower.account_status != "active" or followed.account_status != "active":
            raise ConflictError("No se puede modificar un seguimiento de cuentas suspendidas")
        if await self._database["account_jobs"].find_one(
            {"user_id": {"$in": [str(follower_id), str(followed_id)]}, "active": True}
        ):
            raise ConflictError("Hay una transición de cuenta pendiente")
        return follower, followed

    @staticmethod
    def _same(existing: FollowJob, job: FollowJob) -> FollowJob:
        fields = ("follower_id", "followed_id", "actor_id", "action", "fail_at")
        if any(getattr(existing, field) != getattr(job, field) for field in fields):
            raise ConflictError("Idempotency-Key usada para otro pedido de seguimiento")
        return existing

    async def enqueue(self, job: FollowJob, keyed: bool) -> FollowJob:
        job.participant_ids = [str(job.follower_id), str(job.followed_id)]
        try:
            await self._jobs.insert_one(
                {"_id": str(job.operation_id), **job.model_dump(mode="json")}
            )
        except DuplicateKeyError as exc:
            existing = await self._jobs.find_one({"_id": str(job.operation_id)})
            if existing is None and not keyed:
                existing = await self._jobs.find_one(
                    {
                        "follower_id": str(job.follower_id),
                        "followed_id": str(job.followed_id),
                        "active": True,
                    }
                )
            if existing is None:
                raise ConflictError(
                    "Otra operación está usando una de estas cuentas; reintente"
                ) from exc
            return self._same(FollowJob.model_validate(existing), job)
        return job

    async def get(self, operation_id: UUID) -> FollowJob:
        doc = await self._jobs.find_one({"_id": str(operation_id)})
        if doc is None:
            raise ResourceNotFoundError("Operación de seguimiento no encontrada")
        return FollowJob.model_validate(doc)

    async def active_pair(self, follower_id: UUID, followed_id: UUID) -> FollowJob | None:
        doc = await self._jobs.find_one(
            {"follower_id": str(follower_id), "followed_id": str(followed_id), "active": True}
        )
        return None if doc is None else FollowJob.model_validate(doc)

    async def save(self, job: FollowJob) -> None:
        job.updated_at = datetime.now(UTC)
        job.active = job.status not in ("completed", "compensated")
        await self._jobs.replace_one(
            {"_id": str(job.operation_id)},
            {"_id": str(job.operation_id), **job.model_dump(mode="json")},
        )

    async def pending(self) -> list[FollowJob]:
        docs = (
            await self._jobs.find(
                {"status": {"$in": ["pending", "running", "committing", "compensating"]}}
            )
            .sort("created_at", 1)
            .limit(10)
            .to_list()
        )
        return [FollowJob.model_validate(doc) for doc in docs]

    async def post_catalog(self, author_id: UUID) -> list[UUID]:
        docs = (
            await self._database["posts"]
            .find({"user_id": str(author_id)}, {"_id": 1})
            .limit(10001)
            .to_list()
        )
        ids = {UUID(str(doc["_id"])) for doc in docs}
        jobs = (
            await self._database["publication_jobs"]
            .find(
                {
                    "post.user_id": str(author_id),
                    "operation.status": {"$in": ["pending", "running"]},
                },
                {"post.id": 1},
            )
            .limit(10001)
            .to_list()
        )
        for job in jobs:
            ids.add(UUID(str(cast(dict[str, Any], job["post"])["id"])))
        if len(ids) > 10000:
            raise InvalidOperationError("P2 soporta hasta 10000 publicaciones por autor")
        return sorted(ids, key=str)

    async def recent_candidates(self, author_id: UUID) -> dict[str, float]:
        posts = (
            await self._database["posts"]
            .find(
                {
                    "user_id": str(author_id),
                    "publication_state": {"$ne": "pending"},
                    "moderation_status": {"$ne": "hidden"},
                    "visibility": "public",
                }
            )
            .sort([("published_at", -1), ("_id", -1)])
            .limit(20)
            .to_list()
        )
        result = {
            str(post["_id"]): cast(datetime, post["published_at"]).timestamp() for post in posts
        }
        # A P1 may have captured its audience before the new follow, even before
        # creating its post document. Its durable payload closes that race.
        jobs = (
            await self._database["publication_jobs"]
            .find(
                {
                    "post.user_id": str(author_id),
                    "operation.status": {"$in": ["pending", "running"]},
                    "rollback": {"$ne": True},
                }
            )
            .limit(10001)
            .to_list()
        )
        if len(jobs) > 10000:
            raise InvalidOperationError("Demasiadas publicaciones pendientes")
        for job in jobs:
            post = cast(dict[str, Any], job["post"])
            result[str(post["id"])] = datetime.fromisoformat(str(post["published_at"])).timestamp()
        return result

    async def retry(self, operation_id: UUID) -> FollowJob:
        job = await self.get(operation_id)
        if job.status != "failed":
            raise ConflictError(
                "Solo se reintenta recuperación fallida; use una clave nueva tras compensated"
            )
        phase: Literal["committing", "compensating"] = (
            "committing" if job.resume_phase == "committing" else "compensating"
        )
        result = await self._jobs.update_one(
            {"_id": str(operation_id), "status": "failed"}, {"$set": {"status": phase}}
        )
        if not result.modified_count:
            raise ConflictError("La recuperación ya fue solicitada")
        return await self.get(operation_id)
