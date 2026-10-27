from uuid import UUID, uuid5

from app.application.ports.moderation import ModerationStore, ModerationViews
from app.application.services.moderation_job import ModerationJob
from app.core.exceptions import ConflictError, InvalidOperationError
from app.domain.entities import ModerationReport


class ModeratePostUseCase:
    def __init__(self, moderation: ModerationStore, views: ModerationViews) -> None:
        self._moderation = moderation
        self._views = views

    async def report(
        self, post_id: UUID, reporter_id: UUID, reason: str, description: str | None = None
    ) -> ModerationReport:
        post = await self._moderation.post(post_id)
        if post.moderation_status == "hidden":
            raise ConflictError("Post is already hidden")
        return await self._moderation.create_report(
            ModerationReport(
                post_id=post_id, reporter_id=reporter_id, reason=reason, description=description
            )
        )

    async def moderate_post(
        self,
        report_id: UUID,
        post_id: UUID,
        moderator_id: UUID,
        decision: str,
        reason: str = "Moderation decision",
        fail_at: str | None = None,
    ) -> ModerationJob:
        if decision not in ("hide", "reject", "revert"):
            raise InvalidOperationError("Decision must be hide, reject or revert")
        report = await self._moderation.report(report_id)
        if str(report["post_id"]) != str(post_id):
            raise ConflictError("Report belongs to a different post")
        if decision == "revert" and report.get("resolution_report_id"):
            # Any report resolved by the same hide points to one canonical reversal.
            report_id = UUID(str(report["resolution_report_id"]))
        operation_id = uuid5(report_id, "revert" if decision == "revert" else "decision")
        existing = await self._moderation.get_job(operation_id)
        if existing is not None:
            if (existing.action, existing.reason, existing.fail_at) != (decision, reason, fail_at):
                raise ConflictError("A different decision/request already exists")
            return existing
        post = await self._moderation.post(post_id)
        status = report["resolution_status"]
        if decision == "revert":
            if status != "approved":
                raise ConflictError("Only an approved hide can be reverted")
            hide = await self._moderation.get_job(uuid5(report_id, "decision"))
            if hide is None or hide.status != "completed" or hide.snapshot is None:
                raise ConflictError("Hide has not completed")
            if (
                hide.post_id != post_id
                or post.moderation_status != "hidden"
                or (str(report_id) != (await self._moderation.snapshot(post_id)).owner)
            ):
                raise ConflictError("This report no longer owns the moderation")
            restore = hide.snapshot
        else:
            if status != "pending":
                raise ConflictError("Report is closed")
            if decision == "hide" and post.moderation_status == "hidden":
                raise ConflictError("Post already hidden by another report")
            restore = None
        return await self._moderation.enqueue(
            ModerationJob(
                operation_id=operation_id,
                report_id=report_id,
                post_id=post_id,
                moderator_id=moderator_id,
                action=decision,
                reason=reason,
                fail_at=fail_at,
                restore=restore,
            )
        )

    async def reverse_moderation(
        self,
        report_id: UUID,
        post_id: UUID,
        moderator_id: UUID,
        reason: str = "Revert moderation",
        fail_at: str | None = None,
    ) -> ModerationJob:
        return await self.moderate_post(report_id, post_id, moderator_id, "revert", reason, fail_at)

    async def get_report(self, report_id: UUID) -> dict[str, object]:
        return await self._moderation.report(report_id)

    async def list_reports(self, status: str | None = None) -> list[dict[str, object]]:
        return await self._moderation.reports(status)

    async def history(self, post_id: UUID) -> list[dict[str, object]]:
        return await self._moderation.history(post_id)

    async def job(self, operation_id: UUID) -> ModerationJob | None:
        return await self._moderation.get_job(operation_id)

    async def retry(self, operation_id: UUID) -> ModerationJob:
        return await self._moderation.retry(operation_id)

    async def inspect(self, post_id: UUID) -> dict[str, object]:
        post = await self._moderation.snapshot(post_id)
        views = await self._views.live_snapshot(post_id)
        return {
            "post_id": str(post_id),
            "moderation_status": post.moderation_status,
            "moderation_owner": post.owner,
            "feeds": views.feeds,
            "counters": views.counters,
        }

    async def content(self, post_id: UUID, report_id: UUID | None = None) -> dict[str, object]:
        """Published content for moderator review, independent of public visibility/Redis."""
        post = await self._moderation.post(post_id)
        snapshot = await self._moderation.snapshot(post_id)
        report_operation_id = None
        if report_id is not None:
            report = await self._moderation.report(report_id)
            if str(report["post_id"]) != str(post_id):
                raise ConflictError("Report belongs to a different post")
            canonical = UUID(str(report.get("resolution_report_id") or report_id))
            operation = await self._moderation.get_job(uuid5(canonical, "revert"))
            if operation is None:
                operation = await self._moderation.get_job(uuid5(canonical, "decision"))
            report_operation_id = operation.operation_id if operation else None
        return {
            "id": post.id,
            "user_id": post.user_id,
            "text": post.text,
            "media": post.media,
            "interests": post.interests,
            "published_at": post.published_at,
            "visibility": post.visibility,
            "moderation_status": snapshot.moderation_status,
            "moderation_owner": snapshot.owner,
            "active_operation_id": await self._moderation.active_operation_id(post_id),
            "report_operation_id": report_operation_id,
        }
