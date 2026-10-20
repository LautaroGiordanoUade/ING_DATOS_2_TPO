from app.application.ports.publication_jobs import PublicationJobs
from app.application.services.publication_job import PublicationJob
from app.core.exceptions import InvalidOperationError
from app.domain.entities import Post


class PublishContentUseCase:
    def __init__(self, jobs: PublicationJobs) -> None:
        self._jobs = jobs

    async def execute(
        self, post: Post, idempotency_key: str | None = None, fail_at: str | None = None
    ) -> PublicationJob:
        if not post.interests or any(not interest.strip() for interest in post.interests):
            raise InvalidOperationError("La publicacion requiere al menos un interes no vacio")
        if post.visibility != "public":
            raise InvalidOperationError("Problema 1 admite publicaciones publicas")
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 200:
            raise InvalidOperationError("Idempotency-Key debe tener entre 1 y 200 caracteres")
        allowed = {
            "mongo_create_post",
            "neo4j_load_followers",
            "redis_feed_update",
            "redis_feed_partial",
            "publication_commit",
        }
        if fail_at is not None and fail_at not in allowed:
            raise InvalidOperationError("Paso de falla desconocido para el problema 1")
        return await self._jobs.enqueue(post, idempotency_key, fail_at)
