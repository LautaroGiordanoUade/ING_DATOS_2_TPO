import os
from uuid import uuid4

import pytest

from app.application.services.moderation_job import ModerationJob
from app.core.config import get_settings
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Redis"
)


async def test_moderator_content_stays_available_after_hide_and_revert(harness: Harness) -> None:
    h = harness
    path = f"/api/v1/moderation/posts/{h.post.id}/content"
    assert (await h.client.get(path)).status_code == 401
    assert (await h.client.get(path, headers=h.headers())).status_code == 403
    report = await h.report()
    associated = await h.report(h.admin)
    hide = await h.decision(report)
    pending = await h.client.get(path, headers=h.headers(h.moderator))
    assert pending.status_code == 200
    assert pending.json()["active_operation_id"] == str(hide.operation_id)
    assert (await h.run(hide)).status == "completed"
    for actor in (h.moderator, h.admin):
        response = await h.client.get(
            path, headers=h.headers(actor), params={"report_id": str(associated)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == h.post.text
        assert data["moderation_status"] == "hidden"
        assert data["moderation_owner"] == str(report)
        assert data["active_operation_id"] is None
        assert data["report_operation_id"] == str(hide.operation_id)
        assert set(data) == {
            "id",
            "user_id",
            "text",
            "media",
            "interests",
            "published_at",
            "visibility",
            "moderation_status",
            "moderation_owner",
            "active_operation_id",
            "report_operation_id",
        }
    assert (await h.client.get(f"/api/v1/posts/{h.post.id}")).status_code == 404
    # A role downgrade takes effect on the same bearer, regardless of frontend cache.
    db = h.resources.mongo_client[get_settings().mongodb_database]
    await db.users.update_one({"_id": str(h.moderator.id)}, {"$set": {"role": "user"}})
    assert (await h.client.get(path, headers=h.headers(h.moderator))).status_code == 403
    response = await h.client.post(
        f"/api/v1/moderation/reports/{associated}/revert",
        headers=h.headers(h.admin),
        json={"reason": "Revision"},
    )
    reverted = await h.run(ModerationJob.model_validate(response.json()))
    assert reverted.status == "completed"
    content = (
        await h.client.get(path, headers=h.headers(h.admin), params={"report_id": str(associated)})
    ).json()
    assert content["moderation_status"] == "approved"
    assert content["report_operation_id"] == str(reverted.operation_id)
    assert (await h.client.get(f"/api/v1/posts/{h.post.id}")).status_code == 200


async def test_moderation_content_does_not_expose_pending_or_missing_posts(
    harness: Harness,
) -> None:
    h = harness
    db = h.resources.mongo_client[get_settings().mongodb_database]
    await db.posts.update_one({"_id": str(h.post.id)}, {"$set": {"publication_state": "pending"}})
    for post_id in (h.post.id, uuid4()):
        response = await h.client.get(
            f"/api/v1/moderation/posts/{post_id}/content", headers=h.headers(h.admin)
        )
        assert response.status_code == 404


async def test_content_recovers_compensated_decision_without_frontend_storage(
    harness: Harness,
) -> None:
    h = harness
    report = await h.report()
    job = await h.run(await h.decision(report, **{"X-Fail-At-Step": "redis_feed"}))
    assert job.status == "compensated"
    response = await h.client.get(
        f"/api/v1/moderation/posts/{h.post.id}/content",
        headers=h.headers(h.admin),
        params={"report_id": str(report)},
    )
    assert response.status_code == 200
    assert response.json()["active_operation_id"] is None
    assert response.json()["report_operation_id"] == str(job.operation_id)
