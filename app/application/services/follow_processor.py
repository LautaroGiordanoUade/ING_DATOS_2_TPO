import logging

from app.application.ports.follows import FollowGraph, FollowStore, FollowViews
from app.application.services.follow_job import FollowJob
from app.application.services.workflow import WorkflowSteps
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)


class FollowProcessor(WorkflowSteps[FollowJob]):
    def __init__(self, store: FollowStore, graph: FollowGraph, views: FollowViews) -> None:
        super().__init__(store)
        self._store, self._graph, self._views = store, graph, views

    async def _counts(self, job: FollowJob) -> None:
        counts = {
            str(user): await self._graph.follow_counts(user)
            for user in (job.follower_id, job.followed_id)
        }
        await self._views.set_counts(counts)

    async def process(self, job: FollowJob) -> None:
        if job.status in ("completed", "compensated", "failed"):
            return
        if job.status == "compensating":
            await self._compensate(job)
            return
        if job.status == "committing":
            await self._commit(job)
            return
        try:
            if job.graph_snapshot is None:
                _, target = await self._store.validate_users(job.follower_id, job.followed_id)
                snapshot = await self._graph.follow_snapshot(job.follower_id, job.followed_id)
                previous = snapshot["relationship"]
                if job.action != "unfollow" and snapshot["blocked"]:
                    raise ConflictError("No se permite seguimiento entre cuentas bloqueadas")
                if job.action == "approve" and previous is None:
                    raise ConflictError("No existe solicitud para aprobar")
                job.desired = (
                    "none"
                    if job.action == "unfollow"
                    else "accepted"
                    if job.action == "approve"
                    or (previous and previous.get("status", "accepted") == "accepted")
                    or target.account_type == "public"
                    else "pending"
                )
                job.catalog = await self._store.post_catalog(job.followed_id)
                job.graph_snapshot = snapshot
                job.status = "running"
                await self._store.save(job)
            if job.snapshot is None:
                job.snapshot = await self._retry(job, "redis_begin", lambda: self._views.begin(job))
                await self._store.save(job)
            await self._step(job, "neo4j_follow", lambda: self._graph.set_follow_state(job))
            await self._step(job, "redis_follow_counters", lambda: self._counts(job))
            if job.candidates is None:
                job.candidates = (
                    await self._store.recent_candidates(job.followed_id)
                    if job.desired == "accepted"
                    else {}
                )
                await self._store.save(job)
            await self._step(job, "redis_follow_feed", lambda: self._feed(job))
            job.status = "committing"
            await self._store.save(job)
        except Exception as exc:
            logger.exception("Follow %s will compensate", job.operation_id)
            job.status, job.error = "compensating", str(exc)
            await self._store.save(job)
            await self._compensate(job)
            return
        await self._commit(job)

    async def _feed(self, job: FollowJob) -> None:
        assert job.snapshot is not None and job.candidates is not None
        entries = list(
            (job.candidates if job.desired == "accepted" else job.snapshot.feeds).items()
        )
        for start in range(0, len(entries), 25):
            await self._views.apply_batch(job, dict(entries[start : start + 25]))
            if job.fail_at == "redis_feed_partial":
                raise RuntimeError("Injected failure after partial follow feed update")

    async def _commit(self, job: FollowJob) -> None:
        try:
            await self._retry(job, "redis_follow_commit", lambda: self._views.finish(job))
            job.status = "completed"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "committing", exc)

    async def _compensate(self, job: FollowJob) -> None:
        try:
            if job.graph_snapshot is not None:
                if job.snapshot is None:
                    job.snapshot = await self._retry(
                        job, "redis_begin", lambda: self._views.begin(job)
                    )
                    await self._store.save(job)
                await self._retry(job, "restore_graph", lambda: self._graph.restore_follow(job))
                await self._retry(job, "restore_counters", lambda: self._counts(job))
                await self._retry(
                    job, "restore_feed", lambda: self._views.finish(job, restore=True)
                )
            job.status = "compensated"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "compensating", exc)

    async def _failed(self, job: FollowJob, phase: str, exc: Exception) -> None:
        job.status, job.resume_phase, job.error = "failed", phase, str(exc)
        await self._store.save(job)
