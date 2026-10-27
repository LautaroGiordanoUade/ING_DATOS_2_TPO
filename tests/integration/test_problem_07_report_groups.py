import asyncio
import os
from typing import Any
from uuid import UUID, uuid5

import pytest

from app.application.services.moderation_job import ModerationJob
from app.application.services.moderation_processor import ModerationProcessor
from app.application.use_cases.problem_07_moderate_post import ModeratePostUseCase
from app.core.config import get_settings
from app.core.exceptions import ConflictError
from app.domain.entities import ModerationReport, Post
from app.domain.entities.models import ModerationStatus
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Redis"
)


class ProcessCrash(BaseException):
    """Termination without normal compensation or acknowledgement."""


async def reverse(h: Harness, report_id: UUID, **headers: str) -> ModerationJob:
    response = await h.client.post(
        f"/api/v1/moderation/reports/{report_id}/revert",
        headers={**h.headers(h.admin), **headers},
        json={"reason": "Revision del grupo"},
    )
    assert response.status_code == 202, response.text
    return ModerationJob.model_validate(response.json())


async def test_hide_resolves_all_pending_and_any_report_reverses_one_shared_decision(
    harness: Harness,
) -> None:
    h = harness
    first, second, third = await h.report(), await h.report(h.admin), await h.report(h.moderator)
    hide = await h.run(await h.decision(first))
    for report_id in (first, second, third):
        report = await h.store.report(report_id)
        assert report["resolution_status"] == "approved"
        assert report["moderator_id"] == str(h.moderator.id)
        assert report["decision_reason"] == hide.reason
        assert report["operation_id"] == str(hide.operation_id)
        assert report["resolution_operation_id"] == str(hide.operation_id)
        assert report["resolution_report_id"] == str(first)
    assert not await h.store.reports("pending")
    history = await h.store.history(h.post.id)
    assert len(history) == 1 and history[0]["affected_report_count"] == 3
    responses = await asyncio.gather(reverse(h, first), reverse(h, second), reverse(h, third))
    assert len({j.operation_id for j in responses}) == 1
    assert responses[0].operation_id == uuid5(first, "revert")
    revert = await h.run(responses[0])
    assert revert.status == "completed" and await h.posts.get(h.post.id) is not None
    for report_id in (first, second, third):
        report = await h.store.report(report_id)
        assert report["resolution_status"] == "reverted"
        assert report["operation_id"] == str(revert.operation_id)
        assert report["resolution_operation_id"] == str(hide.operation_id)
    history = await h.store.history(h.post.id)
    assert [event["affected_report_count"] for event in history] == [3, 3]
    assert (await reverse(h, second)).operation_id == revert.operation_id


async def test_reject_is_individual_and_hide_preserves_previously_rejected_and_other_posts(
    harness: Harness,
) -> None:
    h = harness
    rejected_id, first, second = (
        await h.report(),
        await h.report(h.admin),
        await h.report(h.moderator),
    )
    reject = await h.run(await h.decision(rejected_id, "reject"))
    assert reject.status == "completed"
    rejected = await h.store.report(rejected_id)
    assert (await h.store.report(first))["resolution_status"] == "pending"
    other = Post(
        user_id=h.admin.id, text="Otra publicación", moderation_status=ModerationStatus.APPROVED
    )
    await h.posts.create(other)
    unrelated = await h.store.create_report(
        ModerationReport(post_id=other.id, reporter_id=h.user.id, reason="spam")
    )
    hide = await h.run(await h.decision(first))
    assert hide.status == "completed"
    assert await h.store.report(rejected_id) == rejected
    assert (await h.store.report(unrelated.id))["resolution_status"] == "pending"
    assert (await h.store.report(second))["resolution_status"] == "approved"
    assert (await h.run(await reverse(h, second))).status == "completed"
    assert await h.store.report(rejected_id) == rejected
    assert (await h.store.report(unrelated.id))["resolution_status"] == "pending"
    assert [event["affected_report_count"] for event in await h.store.history(h.post.id)] == [
        1,
        2,
        2,
    ]


@pytest.mark.parametrize("action", ["hide", "revert"])
async def test_partial_report_update_crash_resumes_same_cohort_and_audit_count(
    harness: Harness,
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    first, second = await h.report(), await h.report(h.admin)
    if action == "hide":
        job = await h.decision(first)
    else:
        await h.run(await h.decision(first))
        job = await reverse(h, second)
    reports = h.resources.mongo_client[get_settings().mongodb_database]["moderation_reports"]

    # Interrupt a real multi-document update after its first write, before audit.
    async def partial(query: dict[str, Any], update: dict[str, Any]) -> None:
        result = await reports.update_one({"$and": [query, {"_id": str(first)}]}, update)
        assert result.modified_count == 1
        raise ProcessCrash()

    monkeypatch.setattr(h.store._reports, "update_many", partial)
    with pytest.raises(ProcessCrash):
        await ModerationProcessor(h.store, h.views).process(job)
    persisted = await h.store.get_job(job.operation_id)
    assert persisted is not None and persisted.status == "committing" and persisted.active
    assert (await h.store.report(first))["resolution_status"] == (
        "approved" if action == "hide" else "reverted"
    )
    assert (await h.store.report(second))["resolution_status"] == (
        "pending" if action == "hide" else "approved"
    )
    late = None
    if action == "revert":
        # Mongo is visible before the audit finishes. A new report belongs to a future decision.
        late = await h.report(h.moderator)
    assert (await h.run(job)).status == "completed"
    expected = "approved" if action == "hide" else "reverted"
    for report_id in (first, second):
        assert (await h.store.report(report_id))["resolution_status"] == expected
    assert (await h.store.report(first))["resolved_at"] == (await h.store.report(second))[
        "resolved_at"
    ]
    events = await h.store.history(h.post.id)
    assert events[-1]["affected_report_count"] == 2
    assert sum(event["operation_id"] == str(job.operation_id) for event in events) == 1
    if late:
        assert (await h.store.report(late))["resolution_status"] == "pending"
    assert (await h.posts.get(h.post.id) is not None) == (action == "revert")


@pytest.mark.parametrize("action,step", [("hide", "redis_feed"), ("revert", "mongo_restore")])
async def test_compensation_preserves_report_group_until_retry_commits(
    harness: Harness,
    action: str,
    step: str,
) -> None:
    h = harness
    first, second = await h.report(), await h.report(h.admin)
    if action == "hide":
        job = await h.decision(first, **{"X-Fail-At-Step": step})
        previous = "pending"
    else:
        await h.run(await h.decision(first))
        job = await reverse(h, second, **{"X-Fail-At-Step": step})
        previous = "approved"
    assert (await h.run(job)).status == "compensated"
    for report_id in (first, second):
        assert (await h.store.report(report_id))["resolution_status"] == previous
    retried = await h.store.retry(job.operation_id)
    assert (await h.run(retried)).status == "completed"
    for report_id in (first, second):
        assert (await h.store.report(report_id))["resolution_status"] == (
            "approved" if action == "hide" else "reverted"
        )


async def test_report_validation_cannot_insert_after_concurrent_hide(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    first = await h.report()
    insert = h.store.create_report

    async def hide_between_validation_and_insert(report: ModerationReport) -> ModerationReport:
        assert (await h.run(await h.decision(first))).status == "completed"
        return await insert(report)

    monkeypatch.setattr(h.store, "create_report", hide_between_validation_and_insert)
    with pytest.raises(ConflictError):
        await ModeratePostUseCase(h.store, h.views).report(h.post.id, h.admin.id, "spam")
    assert not await h.store.reports("pending")
    assert len(await h.store.reports()) == 1


async def test_inflight_report_insert_is_included_before_worker_hides(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    first = await h.report()
    job = await h.decision(first)
    inserting, hiding, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    insert, set_post = h.store._reports.insert_one, h.store.set_post

    async def pause_insert(*args: Any, **kwargs: Any) -> Any:
        inserting.set()
        await release.wait()
        return await insert(*args, **kwargs)

    async def watch_hide(post_id: UUID, status: str, owner: str | None) -> None:
        hiding.set()
        await set_post(post_id, status, owner)

    monkeypatch.setattr(h.store._reports, "insert_one", pause_insert)
    monkeypatch.setattr(h.store, "set_post", watch_hide)
    reporter = asyncio.create_task(
        ModeratePostUseCase(h.store, h.views).report(h.post.id, h.admin.id, "abuse")
    )
    processor = None
    try:
        await asyncio.wait_for(inserting.wait(), 2)
        processor = asyncio.create_task(ModerationProcessor(h.store, h.views).process(job))
        await asyncio.wait_for(hiding.wait(), 2)
        assert not processor.done()
        release.set()
        report = await reporter
        await processor
        assert job.status == "completed"
        assert (await h.store.report(report.id))["resolution_status"] == "approved"
        assert (await h.store.history(h.post.id))[0]["affected_report_count"] == 2
    finally:
        release.set()
        await asyncio.gather(reporter, *([processor] if processor else []), return_exceptions=True)


async def test_stale_decision_cannot_queue_after_another_report_closed_the_group(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    first, second = await h.report(), await h.report(h.admin)
    enqueue = h.store.enqueue

    async def concurrent_decision(job: ModerationJob) -> ModerationJob:
        assert (await h.run(await h.decision(second))).status == "completed"
        return await enqueue(job)

    monkeypatch.setattr(h.store, "enqueue", concurrent_decision)
    with pytest.raises(ConflictError):
        await ModeratePostUseCase(h.store, h.views).moderate_post(
            first, h.post.id, h.moderator.id, "reject"
        )
    assert await h.store.get_job(uuid5(first, "decision")) is None
    assert not await h.store.reports("pending")


async def test_revert_of_legacy_hide_without_group_metadata(harness: Harness) -> None:
    h = harness
    first = await h.report()
    hide = await h.run(await h.decision(first))
    reports = h.resources.mongo_client[get_settings().mongodb_database]["moderation_reports"]
    await reports.update_one(
        {"_id": str(first)}, {"$unset": {"resolution_operation_id": "", "resolution_report_id": ""}}
    )
    revert = await h.run(await reverse(h, first))
    assert revert.status == "completed"
    report = await h.store.report(first)
    assert report["resolution_status"] == "reverted"
    assert report["resolution_operation_id"] == str(hide.operation_id)
    assert (await h.store.history(h.post.id))[-1]["affected_report_count"] == 1
