import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import TypeAdapter
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.application.services.operation import OperationContext
from app.application.services.publication_job import PublicationJob
from app.core.exceptions import ConflictError
from app.domain.entities import Post
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)

_adapter = TypeAdapter(PublicationJob)


class MongoPublicationJobs:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._jobs = database["publication_jobs"]
        self._log = MongoOperationLogRepository(database)

    async def ensure_indexes(self) -> None:
        await self._jobs.create_index(
            [("operation.status", 1), ("operation.created_at", 1)], name="publication_pending"
        )
        await self._jobs.create_index("post.id", name="ix_publication_post")
        await self._jobs.create_index(
            [("post.user_id", 1), ("operation.status", 1)], name="ix_publication_author_status"
        )

    async def enqueue(self, post: Post, key: str | None, fail_at: str | None) -> PublicationJob:
        author = await self._database["users"].find_one(
            {"_id": str(post.user_id), "account_status": "suspended"}
        )
        if author:
            raise ConflictError("Suspended accounts cannot publish")
        payload = post_to_document(post)
        for name in ("_id", "published_at", "moderation_status"):
            payload.pop(name)
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        operation_id = (
            uuid4() if key is None else uuid5(NAMESPACE_URL, f"publish:{post.user_id}:{key}")
        )
        post.id = uuid5(operation_id, "post")
        job = PublicationJob(
            post=post,
            operation=OperationContext("problem_01_publish_content", operation_id=operation_id),
            fingerprint=fingerprint,
            fail_at=fail_at,
        )
        document = _adapter.dump_python(job, mode="json")
        document["_id"] = str(operation_id)
        try:
            await self._jobs.insert_one(document)
        except DuplicateKeyError:
            existing = await self._jobs.find_one({"_id": str(operation_id)})
            if existing is None:
                raise
            existing.pop("_id")
            job = _adapter.validate_python(existing)
            if job.fingerprint != fingerprint or job.fail_at != fail_at:
                raise ConflictError(
                    "Idempotency-Key ya usada con otro contenido o escenario"
                ) from None
        return job

    async def pending(self) -> tuple[PublicationJob, ...]:
        docs = (
            await self._jobs.find({"operation.status": {"$nin": ["completed", "compensated"]}})
            .sort("operation.created_at", 1)
            .limit(10)
            .to_list()
        )
        for doc in docs:
            doc.pop("_id")
        return tuple(_adapter.validate_python(doc) for doc in docs)

    async def get(self, operation_id: UUID) -> PublicationJob | None:
        document = await self._jobs.find_one({"_id": str(operation_id)})
        if document is None:
            return None
        document.pop("_id")
        return _adapter.validate_python(document)

    async def save(self, job: PublicationJob) -> None:
        job.operation.touch()
        await self._log.save(job.operation)
        document = _adapter.dump_python(job, mode="json")
        document["_id"] = str(job.operation.operation_id)
        await self._jobs.replace_one({"_id": document["_id"]}, document)

    async def stage_post(self, job: PublicationJob) -> None:
        document = post_to_document(job.post)
        document["publication_state"] = "pending"
        await self._database["posts"].update_one(
            {"_id": str(job.post.id)}, {"$setOnInsert": document}, upsert=True
        )

    async def activate_post(self, job: PublicationJob) -> None:
        await self._database["posts"].update_one(
            {"_id": str(job.post.id)}, {"$set": {"publication_state": "published"}}
        )

    async def delete_post(self, job: PublicationJob) -> None:
        await self._database["posts"].delete_one({"_id": str(job.post.id)})
