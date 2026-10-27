from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.application.services.account_job import AccountJob
from app.application.services.moderation_job import ModerationSnapshot
from app.core.exceptions import ConflictError, InvalidOperationError, ResourceNotFoundError
from app.domain.entities import User
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository


class MongoAccountStore:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._jobs = database["account_jobs"]

    async def ensure_indexes(self) -> None:
        await self._jobs.create_index(
            "user_id", unique=True, partialFilterExpression={"active": True}
        )
        await self._jobs.create_index([("status", 1), ("created_at", 1)])
        await self._database["account_post_snapshots"].create_index(
            [("operation_id", 1), ("post_id", 1)], unique=True
        )
        await self._database["account_history"].create_index([("user_id", 1), ("created_at", 1)])
        await self._database["posts"].create_index([("user_id", 1), ("published_at", -1)])
        await self._database["posts"].create_index(
            [("user_id", 1), ("published_at", -1), ("_id", -1)],
            name="ix_post_author_published_id",
        )
        await self._database["conversations"].create_index("participant_ids")
        await self._database["conversations"].create_index(
            [("participant_ids", 1), ("created_at", -1)],
            name="ix_conversation_participant_created",
        )

    async def user(self, user_id: UUID) -> User:
        user = await MongoUserRepository(self._database).get(user_id)
        if user is None:
            raise ResourceNotFoundError("Account not found")
        return user

    async def get(self, operation_id: UUID) -> AccountJob:
        doc = await self._jobs.find_one({"_id": str(operation_id)})
        if doc is None:
            raise ResourceNotFoundError("Account operation not found")
        return AccountJob.model_validate(doc)

    async def latest(self, user_id: UUID, action: str) -> AccountJob | None:
        doc = await self._jobs.find_one(
            {"user_id": str(user_id), "action": action, "status": "completed"},
            sort=[("created_at", -1)],
        )
        return None if doc is None else AccountJob.model_validate(doc)

    @staticmethod
    def _same(previous: AccountJob, job: AccountJob) -> AccountJob:
        if (previous.action, previous.reason, previous.fail_at) != (
            job.action,
            job.reason,
            job.fail_at,
        ):
            raise ConflictError("Request key or current transition has a different payload")
        return previous

    async def enqueue(self, job: AccountJob, keyed: bool) -> AccountJob:
        await self.ensure_indexes()
        existing = await self._jobs.find_one({"_id": str(job.operation_id)})
        if existing:
            return self._same(AccountJob.model_validate(existing), job)
        user = await self.user(job.user_id)
        desired = "suspended" if job.action == "suspend" else "active"
        if user.account_status == desired:
            previous = await self.latest(job.user_id, job.action)
            if previous and not keyed:
                return self._same(previous, job)
            raise ConflictError("Account already has the requested state")
        if job.action == "reactivate":
            suspension = await self.latest(job.user_id, "suspend")
            if suspension is None:
                raise ConflictError("No completed suspension snapshot exists")
            job.restore_from = suspension.operation_id
        try:
            await self._jobs.insert_one(
                {"_id": str(job.operation_id), **job.model_dump(mode="json")}
            )
        except DuplicateKeyError as exc:
            prior_doc = await self._jobs.find_one({"_id": str(job.operation_id)})
            if prior_doc is None and not keyed:
                prior_doc = await self._jobs.find_one({"user_id": str(job.user_id), "active": True})
            if prior_doc is None:
                raise ConflictError("Another account transition is active") from exc
            return self._same(AccountJob.model_validate(prior_doc), job)
        return job

    async def save(self, job: AccountJob) -> None:
        job.updated_at = datetime.now(UTC)
        job.active = job.status not in ("completed", "compensated")
        await self._jobs.replace_one(
            {"_id": str(job.operation_id)},
            {"_id": str(job.operation_id), **job.model_dump(mode="json")},
        )

    async def pending(self) -> list[AccountJob]:
        docs = (
            await self._jobs.find(
                {"status": {"$in": ["pending", "running", "committing", "compensating"]}}
            )
            .sort("created_at", 1)
            .limit(10)
            .to_list()
        )
        return [AccountJob.model_validate(doc) for doc in docs]

    async def post_ids(self, user_id: UUID) -> list[UUID]:
        docs = (
            await self._database["posts"]
            .find({"user_id": str(user_id)}, {"_id": 1})
            .limit(10001)
            .to_list()
        )
        if len(docs) > 10000:
            raise InvalidOperationError("Account workflow supports up to 10000 posts per account")
        return [UUID(str(doc["_id"])) for doc in docs]

    async def transition(self, job: AccountJob, status: str) -> None:
        marker = f"{job.operation_id}:{job.attempt}:{status}"
        # Account state and token revocation are one atomic write, repeated safely.
        await self._database["users"].update_one(
            {"_id": str(job.user_id), "last_account_operation": {"$ne": marker}},
            {
                "$set": {"account_status": status, "last_account_operation": marker},
                "$inc": {"auth_version": 1 if status == "suspended" else 0},
            },
        )

    async def save_post(self, job: AccountJob, post_id: UUID, snapshot: ModerationSnapshot) -> None:
        await self._database["account_post_snapshots"].update_one(
            {"operation_id": str(job.operation_id), "post_id": str(post_id)},
            {"$setOnInsert": {"snapshot": snapshot.model_dump(mode="json")}},
            upsert=True,
        )

    async def post_snapshot(self, job_id: UUID, post_id: UUID) -> ModerationSnapshot | None:
        doc = await self._database["account_post_snapshots"].find_one(
            {"operation_id": str(job_id), "post_id": str(post_id)}
        )
        return None if doc is None else ModerationSnapshot.model_validate(doc["snapshot"])

    async def fallback_feeds(self, post_id: UUID) -> dict[str, float]:
        # P7 may already have removed references. Preserve its earlier audience so
        # reverting P7 while P8 is suspended can be completed upon reactivation.
        post = await self._database["posts"].find_one({"_id": str(post_id)})
        if post is None:
            return {}
        owner = post.get("moderation_owner")
        if owner:
            moderation = await self._database["moderation_jobs"].find_one(
                {"report_id": owner, "action": "hide", "status": "completed"}
            )
            if moderation and moderation.get("snapshot"):
                snapshot = ModerationSnapshot.model_validate(moderation["snapshot"])
                return snapshot.feeds
        # A P1 already in flight may commit while account fan-out is gated.
        publication = await self._database["publication_jobs"].find_one(
            {"post.id": str(post_id), "operation.status": "completed"}
        )
        if not publication:
            return {}
        payload = cast(dict[str, object], publication["post"])
        score = datetime.fromisoformat(str(payload["published_at"])).timestamp()
        return {
            f"feed:{follower}": score
            for follower in cast(list[str], publication.get("followers") or [])
        }

    async def finalize(self, job: AccountJob) -> None:
        await self._database["account_history"].update_one(
            {"_id": str(job.operation_id)},
            {
                "$setOnInsert": {
                    "user_id": str(job.user_id),
                    "actor_id": str(job.actor_id),
                    "action": job.action,
                    "reason": job.reason,
                    "previous_status": job.previous_status,
                    "new_status": "suspended" if job.action == "suspend" else "active",
                    "created_at": job.updated_at,
                    "posts_count": len(job.post_ids),
                }
            },
            upsert=True,
        )

    async def history(self, user_id: UUID) -> list[dict[str, object]]:
        docs = (
            await self._database["account_history"]
            .find({"user_id": str(user_id)})
            .sort("created_at", 1)
            .limit(100)
            .to_list()
        )
        for doc in docs:
            doc["operation_id"] = doc.pop("_id")
        return docs

    async def retry(self, operation_id: UUID) -> AccountJob:
        job = await self.get(operation_id)
        if job.status not in ("failed", "compensated"):
            raise ConflictError("Only failed or compensated operations can be retried")
        changes: dict[str, object] = {"status": job.resume_phase, "active": True}
        if job.status == "compensated":
            # A new attempt keeps its own immutable per-post snapshots/Redis backup.
            raise ConflictError(
                "Compensation completed; submit a new Idempotency-Key for a new attempt"
            )
        result = await self._jobs.update_one(
            {"_id": str(operation_id), "status": "failed"}, {"$set": changes}
        )
        if not result.modified_count:
            raise ConflictError("Recovery already resumed")
        return await self.get(operation_id)

    async def trace_posts(self, user_id: UUID) -> list[dict[str, object]]:
        docs = (
            await self._database["posts"]
            .find({"user_id": str(user_id)}, {"text": 0, "media": 0})
            .sort("published_at", -1)
            .limit(100)
            .to_list()
        )
        for doc in docs:
            doc["id"] = doc.pop("_id")
        return docs
