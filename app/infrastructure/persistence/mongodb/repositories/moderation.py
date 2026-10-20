from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.application.services.moderation_job import ModerationJob, ModerationSnapshot
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.domain.entities import ModerationReport, Post
from app.infrastructure.persistence.mongodb.mappers.post_mapper import document_to_post


class MongoModerationRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._reports = database["moderation_reports"]
        self._jobs = database["moderation_jobs"]

    async def ensure_indexes(self) -> None:
        await self._reports.create_index([("post_id", 1), ("reporter_id", 1)], unique=True)
        await self._reports.create_index([("resolution_status", 1), ("reported_at", -1)])
        await self._reports.create_index("moderator_id")
        await self._jobs.create_index(
            "post_id", unique=True, partialFilterExpression={"active": True}
        )
        await self._jobs.create_index([("status", 1), ("created_at", 1)])
        await self._database["moderation_history"].create_index([("post_id", 1), ("created_at", 1)])

    async def create_report(self, report: ModerationReport) -> ModerationReport:
        await self.ensure_indexes()
        doc = asdict(report)
        doc["_id"] = str(doc.pop("id"))
        doc["post_id"], doc["reporter_id"] = str(report.post_id), str(report.reporter_id)
        doc["target_type"] = "post"
        try:
            await self._reports.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ConflictError("This user already reported this post") from exc
        return report

    async def report(self, report_id: UUID) -> dict[str, object]:
        doc = await self._reports.find_one({"_id": str(report_id)})
        if doc is None:
            raise ResourceNotFoundError("Report not found")
        doc["id"] = doc.pop("_id")
        return doc

    async def reports(self, status: str | None = None) -> list[dict[str, object]]:
        query = {} if status is None else {"resolution_status": status}
        docs = await self._reports.find(query).sort("reported_at", -1).limit(100).to_list()
        for doc in docs:
            doc["id"] = doc.pop("_id")
        return docs

    async def history(self, post_id: UUID) -> list[dict[str, object]]:
        docs = (
            await self._database["moderation_history"]
            .find({"post_id": str(post_id)})
            .sort("created_at", 1)
            .limit(100)
            .to_list()
        )
        for doc in docs:
            doc["operation_id"] = doc.pop("_id")
        return docs

    async def post(self, post_id: UUID) -> Post:
        doc = await self._database["posts"].find_one(
            {"_id": str(post_id), "publication_state": {"$ne": "pending"}}
        )
        if doc is None:
            raise ResourceNotFoundError("Post not found or not published")
        publication = await self._database["publication_jobs"].find_one({"post.id": str(post_id)})
        if (
            publication
            and cast(dict[str, object], publication.get("operation", {})).get("status")
            != "completed"
        ):
            raise ConflictError("Publication is still being committed")
        return document_to_post(doc)

    async def snapshot(self, post_id: UUID) -> ModerationSnapshot:
        await self.post(post_id)
        doc = await self._database["posts"].find_one({"_id": str(post_id)})
        assert doc is not None
        return ModerationSnapshot(
            moderation_status=str(doc["moderation_status"]), owner=doc.get("moderation_owner")
        )

    async def set_post(self, post_id: UUID, status: str, owner: str | None) -> None:
        result = await self._database["posts"].update_one(
            {"_id": str(post_id)},
            {"$set": {"moderation_status": status, "moderation_owner": owner}},
        )
        if not result.matched_count:
            raise ResourceNotFoundError("Post disappeared during moderation")

    async def get_job(self, operation_id: UUID) -> ModerationJob | None:
        doc = await self._jobs.find_one({"_id": str(operation_id)})
        return None if doc is None else ModerationJob.model_validate(doc)

    async def enqueue(self, job: ModerationJob) -> ModerationJob:
        await self.ensure_indexes()
        doc = job.model_dump(mode="json")
        doc["_id"] = str(job.operation_id)
        try:
            await self._jobs.insert_one(doc)
        except DuplicateKeyError as exc:
            previous = await self.get_job(job.operation_id)
            if previous is None:
                raise ConflictError("Another moderation operation is active on this post") from exc
            if (previous.action, previous.reason, previous.fail_at) != (
                job.action,
                job.reason,
                job.fail_at,
            ):
                raise ConflictError("Report already has a different decision/request") from exc
            return previous
        return job

    async def save(self, job: ModerationJob) -> None:
        job.updated_at = datetime.now(UTC)
        job.active = job.status not in ("completed", "compensated")
        await self._jobs.replace_one(
            {"_id": str(job.operation_id)},
            {"_id": str(job.operation_id), **job.model_dump(mode="json")},
        )

    async def pending(self) -> list[ModerationJob]:
        docs = (
            await self._jobs.find(
                {"status": {"$in": ["pending", "running", "committing", "compensating"]}}
            )
            .sort("created_at", 1)
            .limit(10)
            .to_list()
        )
        return [ModerationJob.model_validate(doc) for doc in docs]

    async def finalize(self, job: ModerationJob) -> None:
        status = {"hide": "approved", "reject": "rejected", "revert": "reverted"}[job.action]
        await self._reports.update_one(
            {"_id": str(job.report_id)},
            {
                "$set": {
                    "resolution_status": status,
                    "moderator_id": str(job.moderator_id),
                    "resolved_at": job.updated_at,
                    "decision": job.action,
                    "decision_reason": job.reason,
                    "operation_id": str(job.operation_id),
                }
            },
        )
        await self._database["moderation_history"].update_one(
            {"_id": str(job.operation_id)},
            {
                "$setOnInsert": {
                    "post_id": str(job.post_id),
                    "report_id": str(job.report_id),
                    "moderator_id": str(job.moderator_id),
                    "action": job.action,
                    "reason": job.reason,
                    "created_at": job.updated_at,
                    "previous_state": (
                        job.snapshot.model_dump(mode="json") if job.snapshot else None
                    ),
                    "new_status": status,
                }
            },
            upsert=True,
        )

    async def retry(self, operation_id: UUID) -> ModerationJob:
        job = await self.get_job(operation_id)
        if job is None:
            raise ResourceNotFoundError("Operation not found")
        if job.status not in ("failed", "compensated"):
            raise ConflictError("Only failed or compensated operations can be retried")
        changes: dict[str, object] = {"status": job.resume_phase, "active": True}
        if job.status == "compensated":
            # Explicit new attempt of the same durable command, after full rollback.
            changes.update(
                status="pending", snapshot=None, completed_steps=[], fail_at=None, error=None
            )
        try:
            result = await self._jobs.update_one(
                {"_id": str(operation_id), "status": job.status}, {"$set": changes}
            )
        except DuplicateKeyError as exc:
            raise ConflictError("Another operation is active on this post") from exc
        if not result.modified_count:
            raise ConflictError("Recovery already resumed")
        updated = await self.get_job(operation_id)
        assert updated is not None
        return updated
