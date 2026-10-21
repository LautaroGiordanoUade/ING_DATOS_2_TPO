import logging
from functools import partial

from app.application.ports.accounts import AccountGraph, AccountStore, AccountViews
from app.application.services.account_job import AccountJob
from app.application.services.workflow import WorkflowSteps
from app.core.exceptions import ConflictError

logger = logging.getLogger(__name__)


class AccountProcessor(WorkflowSteps[AccountJob]):
    """Runs in the same OS-locked consumer as P7: post effects cannot overlap."""

    def __init__(self, store: AccountStore, graph: AccountGraph, views: AccountViews) -> None:
        super().__init__(store)
        self._store, self._graph, self._views = store, graph, views

    async def process(self, job: AccountJob) -> None:
        if job.status in ("completed", "compensated", "failed"):
            return
        if job.status == "compensating":
            await self._compensate(job)
            return
        if job.status == "committing":
            await self._commit(job)
            return
        try:
            if job.previous_status is None:
                user = await self._store.user(job.user_id)
                expected = "active" if job.action == "suspend" else "suspended"
                if user.account_status != expected:
                    raise ConflictError("Account state changed before processing")
                job.post_ids = await self._retry(
                    job, "posts_snapshot", lambda: self._store.post_ids(job.user_id)
                )
                job.graph_snapshot = await self._retry(
                    job, "graph_snapshot", lambda: self._graph.account_snapshot(job.user_id)
                )
                job.previous_status = user.account_status.value
                job.status = "running"
                await self._store.save(job)
            if job.action == "suspend":
                await self._step(
                    job, "mongo_suspend", lambda: self._store.transition(job, "suspended")
                )
                await self._step(
                    job,
                    "redis_close_presence",
                    lambda: self._views.block(job.user_id, job.operation_id),
                )
                await self._step(
                    job,
                    "neo4j_suspend",
                    lambda: self._graph.set_account_status(job.user_id, "suspended"),
                )
                await self._step(job, "redis_remove_posts", lambda: self._hide_posts(job))
            else:
                await self._step(job, "redis_restore_posts", lambda: self._restore_posts(job))
                await self._step(
                    job,
                    "neo4j_reactivate",
                    lambda: self._graph.set_account_status(job.user_id, "active"),
                )
                assert job.restore_from is not None
                restore_from = job.restore_from
                await self._step(
                    job,
                    "redis_reactivate",
                    lambda: self._views.unblock(job.user_id, restore_from, False),
                )
                await self._step(
                    job, "mongo_reactivate", lambda: self._store.transition(job, "active")
                )
            job.status = "committing"
            await self._store.save(job)
        except Exception as exc:
            logger.exception("Account %s will compensate", job.operation_id)
            job.error, job.status = str(exc), "compensating"
            await self._store.save(job)
            await self._compensate(job)
            return
        await self._commit(job)

    async def _hide_posts(self, job: AccountJob) -> None:
        job.post_ids = sorted(
            set(job.post_ids) | set(await self._store.post_ids(job.user_id)), key=str
        )
        await self._store.save(job)
        for post_id in job.post_ids:
            snapshot = await self._store.post_snapshot(job.operation_id, post_id)
            if snapshot is None:
                snapshot = await self._views.snapshot(post_id)
                fallback = await self._store.fallback_feeds(post_id)
                snapshot.feeds = {**fallback, **snapshot.feeds}
                await self._store.save_post(job, post_id, snapshot)
            await self._views.hide_post(post_id, snapshot)

    async def _restore_posts(self, job: AccountJob) -> None:
        assert job.restore_from is not None
        # Include posts committed by an already-running P1 after the suspension snapshot.
        post_ids = set(job.post_ids) | set(await self._store.post_ids(job.user_id))
        for post_id in post_ids:
            snapshot = await self._store.post_snapshot(job.restore_from, post_id)
            if snapshot is None:
                snapshot = await self._views.snapshot(post_id)
                snapshot.feeds = {**await self._store.fallback_feeds(post_id), **snapshot.feeds}
            await self._views.restore_post(post_id, snapshot)

    async def _commit(self, job: AccountJob) -> None:
        try:
            await self._retry(job, "audit", lambda: self._store.finalize(job))
            job.status = "completed"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "committing", exc)

    async def _compensate(self, job: AccountJob) -> None:
        try:
            if job.previous_status is not None:
                if job.action == "suspend":
                    for post_id in job.post_ids:
                        snapshot = await self._store.post_snapshot(job.operation_id, post_id)
                        if snapshot:
                            await self._retry(
                                job,
                                "restore_post",
                                partial(self._views.restore_post, post_id, snapshot),
                            )
                    if job.graph_snapshot is not None:
                        graph_snapshot = job.graph_snapshot
                        await self._retry(
                            job,
                            "restore_graph",
                            lambda: self._graph.restore_account(job.user_id, graph_snapshot),
                        )
                    await self._retry(
                        job,
                        "restore_views",
                        lambda: self._views.unblock(job.user_id, job.operation_id, True),
                    )
                    await self._retry(
                        job, "restore_account", lambda: self._store.transition(job, "active")
                    )
                else:
                    await self._retry(
                        job, "resuspend", lambda: self._store.transition(job, "suspended")
                    )
                    await self._retry(
                        job,
                        "reclose_presence",
                        lambda: self._views.block(job.user_id, job.operation_id),
                    )
                    await self._retry(
                        job,
                        "resuspend_graph",
                        lambda: self._graph.set_account_status(job.user_id, "suspended"),
                    )
                    await self._retry(job, "rehide_posts", lambda: self._hide_posts(job))
            job.status = "compensated"
            await self._store.save(job)
        except Exception as exc:
            await self._failed(job, "compensating", exc)

    async def _failed(self, job: AccountJob, phase: str, exc: Exception) -> None:
        job.status, job.resume_phase, job.error = "failed", phase, str(exc)
        logger.exception("Account recovery %s requires retry", job.operation_id)
        await self._store.save(job)
