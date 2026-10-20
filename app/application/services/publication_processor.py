from uuid import UUID

from app.application.ports.publication_feeds import PublicationFeeds
from app.application.ports.publication_jobs import PublicationJobs
from app.application.services.operation import OperationStatus
from app.application.services.publication_job import PublicationJob
from app.domain.repositories import SocialGraphRepository


class PublicationProcessor:
    """Single durable consumer; effects can be repeated after a process crash."""

    def __init__(
        self,
        jobs: PublicationJobs,
        graph: SocialGraphRepository,
        feeds: PublicationFeeds,
        batch_size: int = 250,
    ) -> None:
        self._jobs, self._graph, self._feeds = jobs, graph, feeds
        self._batch_size = batch_size

    async def _step(self, job: PublicationJob, name: str) -> None:
        job.operation.current_step = name
        await self._jobs.save(job)
        if job.fail_at == name:
            raise RuntimeError(f"Falla inyectada: {name}")

    async def _done(self, job: PublicationJob, name: str) -> None:
        if name not in job.operation.completed_steps:
            job.operation.completed_steps.append(name)
        await self._jobs.save(job)

    async def process(self, job: PublicationJob) -> None:
        if job.operation.status in (OperationStatus.COMPLETED, OperationStatus.COMPENSATED):
            return
        if job.rollback:
            await self._rollback(job)
            return
        job.operation.status = OperationStatus.RUNNING
        try:
            if "publication_commit" not in job.operation.completed_steps:
                await self._step(job, "mongo_create_post")
                await self._jobs.stage_post(job)
                await self._done(job, "mongo_create_post")
                if job.followers is None:
                    await self._step(job, "neo4j_load_followers")
                    followers = await self._graph.follower_ids(job.post.user_id)
                    if len(followers) > 100_000:
                        raise RuntimeError("Audiencia mayor al límite de 100000 de esta entrega")
                    job.followers = [str(user) for user in sorted(set(followers), key=str)]
                    await self._done(job, "neo4j_load_followers")
                await self._step(job, "redis_feed_update")
                while job.offset < len(job.followers):
                    batch = tuple(
                        UUID(user)
                        for user in job.followers[job.offset : job.offset + self._batch_size]
                    )
                    await self._feeds.stage_batch(
                        batch, job.post.id, job.post.published_at.timestamp()
                    )
                    if job.fail_at == "redis_feed_partial":
                        raise RuntimeError("Falla inyectada después de distribuir un lote")
                    job.offset += len(batch)
                    await self._jobs.save(job)
                await self._done(job, "redis_feed_update")
                await self._step(job, "publication_commit")
                # Durable commit decision precedes visibility. Restart completes it.
                await self._done(job, "publication_commit")
        except Exception as exc:
            job.rollback = True
            job.operation.error = str(exc)
            job.operation.status = OperationStatus.COMPENSATING
            await self._jobs.save(job)
            await self._rollback(job)
            return
        # Never roll back after committing: some clients may already have read it.
        await self._jobs.activate_post(job)
        await self._feeds.commit(job.post.id)
        job.operation.status = OperationStatus.COMPLETED
        job.operation.current_step = None
        await self._jobs.save(job)

    async def _rollback(self, job: PublicationJob) -> None:
        job.operation.status = OperationStatus.COMPENSATING
        job.operation.current_step = "rollback"
        await self._jobs.save(job)
        await self._feeds.abort(job.post.id)
        audience = job.followers or []
        # Include the batch whose acknowledgement or cursor save may have been lost.
        for start in range(0, len(audience), self._batch_size):
            await self._feeds.remove_batch(
                tuple(UUID(user) for user in audience[start : start + self._batch_size]),
                job.post.id,
            )
        await self._jobs.delete_post(job)
        job.operation.status = OperationStatus.COMPENSATED
        job.operation.current_step = None
        await self._jobs.save(job)
