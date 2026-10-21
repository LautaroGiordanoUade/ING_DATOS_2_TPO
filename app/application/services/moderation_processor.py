import logging
from uuid import uuid5

from app.application.ports.moderation import ModerationStore, ModerationViews
from app.application.services.moderation_job import ModerationJob
from app.application.services.workflow import WorkflowSteps
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)


class ModerationProcessor(WorkflowSteps[ModerationJob]):
    """One OS-locked consumer, persistent snapshots, idempotent effects and recovery."""

    def __init__(self, store: ModerationStore, views: ModerationViews) -> None:
        super().__init__(store)
        self._store, self._views = store, views

    async def process(self, job: ModerationJob) -> None:
        if job.status in ("completed", "compensated", "failed"):
            return
        if job.status == "compensating":
            await self._compensate(job)
            return
        if job.status == "committing":
            await self._commit(job)
            return
        try:
            if job.snapshot is None:
                snapshot = await self._retry(
                    job, "snapshot_post", lambda: self._store.snapshot(job.post_id)
                )
                if job.action == "hide" and snapshot.moderation_status == "hidden":
                    raise ConflictError("Another report already hid this post")
                if job.action == "revert" and snapshot.owner != str(job.report_id):
                    raise ConflictError("This report no longer owns the moderation")
                if job.action != "reject":
                    views = await self._retry(
                        job, "snapshot_views", lambda: self._views.snapshot(job.post_id)
                    )
                    snapshot.feeds, snapshot.counters = views.feeds, views.counters
                job.snapshot = snapshot
                job.status = "running"
                await self._store.save(job)
            if job.action == "hide":
                await self._step(
                    job,
                    "mongo_hide",
                    lambda: self._store.set_post(job.post_id, "hidden", str(job.report_id)),
                )
                await self._step(job, "redis_counters", lambda: self._views.hide(job.post_id))
                snapshot = job.snapshot
                assert snapshot is not None
                await self._step(
                    job, "redis_feed", lambda: self._views.remove_feeds(job.post_id, snapshot)
                )
            elif job.action == "revert":
                restore = job.restore
                assert restore is not None
                # Keep Mongo hidden until every derived representation is restored.
                await self._step(
                    job, "redis_restore", lambda: self._views.restore(job.post_id, restore)
                )
                await self._step(
                    job,
                    "mongo_restore",
                    lambda: self._store.set_post(
                        job.post_id, restore.moderation_status, restore.owner
                    ),
                )
            # A persisted commit decision is never compensated on acknowledgement loss.
            job.status = "committing"
            await self._store.save(job)
        except Exception as exc:
            logger.exception("Moderation %s will compensate", job.operation_id)
            job.error = str(exc)
            job.status = "compensating"
            await self._store.save(job)
            await self._compensate(job)
            return
        await self._commit(job)

    async def _commit(self, job: ModerationJob) -> None:
        try:
            await self._retry(job, "audit", lambda: self._store.finalize(job))
            job.status = "completed"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "committing", exc)

    async def _compensate(self, job: ModerationJob) -> None:
        try:
            snapshot = job.snapshot
            if snapshot is not None and job.action == "hide":
                await self._retry(
                    job, "restore_views", lambda: self._views.restore(job.post_id, snapshot)
                )
                await self._retry(
                    job,
                    "restore_post",
                    lambda: self._store.set_post(
                        job.post_id, snapshot.moderation_status, snapshot.owner
                    ),
                )
            elif snapshot is not None and job.action == "revert":
                # Recreate the hidden state of this same report, without exposing it.
                await self._retry(
                    job,
                    "rehide_post",
                    lambda: self._store.set_post(
                        job.post_id, snapshot.moderation_status, snapshot.owner
                    ),
                )
                await self._retry(job, "rehide_counters", lambda: self._views.hide(job.post_id))
                hide = await self._store.get_job(uuid5(job.report_id, "decision"))
                assert hide is not None and hide.snapshot is not None
                original = hide.snapshot
                await self._retry(
                    job, "rehide_feed", lambda: self._views.remove_feeds(job.post_id, original)
                )
            job.status = "compensated"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "compensating", exc)

    async def _failed(self, job: ModerationJob, phase: str, exc: Exception) -> None:
        logger.exception("Moderation %s requires explicit recovery", job.operation_id)
        job.status, job.resume_phase, job.error = "failed", phase, str(exc)
        await self._store.save(job)
