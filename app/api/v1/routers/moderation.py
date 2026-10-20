from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.auth import CurrentUserDep, ModeratorDep
from app.api.dependencies.use_cases import FailureInjectorDep, get_moderation_use_case
from app.application.services.moderation_job import ModerationJob
from app.application.use_cases import ModeratePostUseCase
from app.schemas.models import ModerationRequest
from app.schemas.moderation import DecisionRequest, ReportCreate, ReportResponse, RevertRequest

router = APIRouter(
    responses={
        401: {"description": "Missing, invalid or expired bearer"},
        403: {"description": "Moderator/admin role required"},
        404: {"description": "Not found"},
        409: {"description": "Closed report, conflicting decision or concurrent operation"},
        422: {"description": "Invalid request"},
    }
)
ModerationDep = Annotated[ModeratePostUseCase, Depends(get_moderation_use_case)]


def failure_name(injector: FailureInjectorDep) -> str | None:
    # Validation of development-only injection happens in the shared dependency.
    return getattr(injector, "fail_at", None)


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def create_report(
    payload: ReportCreate, actor: CurrentUserDep, service: ModerationDep
) -> object:
    """Report a published post. One report per user/post; identity comes from the bearer."""
    return await service.report(payload.post_id, actor.id, payload.reason, payload.description)


@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    actor: ModeratorDep,
    service: ModerationDep,
    status: Annotated[str | None, Query(pattern="^(pending|approved|rejected|reverted)$")] = None,
) -> object:
    """Moderator queue, newest first, up to 100 reports."""
    return await service.list_reports(status)


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: UUID, actor: CurrentUserDep, service: ModerationDep) -> object:
    report = await service.get_report(report_id)
    if actor.role not in ("moderator", "admin") and str(report["reporter_id"]) != str(actor.id):
        raise HTTPException(
            status_code=403, detail="Only reporter or moderator may read this report"
        )
    return report


@router.post("/reports/{report_id}/decision", response_model=ModerationJob, status_code=202)
async def decide(
    report_id: UUID,
    payload: DecisionRequest,
    actor: ModeratorDep,
    service: ModerationDep,
    injector: FailureInjectorDep,
) -> ModerationJob:
    """Enqueue durable hide/reject; poll the operation until a terminal status."""
    report = await service.get_report(report_id)
    return await service.moderate_post(
        report_id,
        UUID(str(report["post_id"])),
        actor.id,
        payload.decision,
        payload.reason,
        failure_name(injector),
    )


@router.post("/reports/{report_id}/revert", response_model=ModerationJob, status_code=202)
async def revert(
    report_id: UUID,
    payload: RevertRequest,
    actor: ModeratorDep,
    service: ModerationDep,
    injector: FailureInjectorDep,
) -> ModerationJob:
    """Restore the exact previous moderation status and feed scores, plus current saved counts."""
    report = await service.get_report(report_id)
    return await service.reverse_moderation(
        report_id, UUID(str(report["post_id"])), actor.id, payload.reason, failure_name(injector)
    )


@router.get("/operations/{operation_id}", response_model=ModerationJob)
async def operation(
    operation_id: UUID, actor: ModeratorDep, service: ModerationDep
) -> ModerationJob:
    job = await service.job(operation_id)
    if job is None:
        from app.core.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("Moderation operation not found")
    return job


@router.post("/operations/{operation_id}/retry", response_model=ModerationJob, status_code=202)
async def retry(operation_id: UUID, actor: ModeratorDep, service: ModerationDep) -> ModerationJob:
    """Resume bounded recovery after a dependency outage; competing requests get 409."""
    return await service.retry(operation_id)


@router.get("/history/{post_id}")
async def history(
    post_id: UUID, actor: ModeratorDep, service: ModerationDep
) -> list[dict[str, object]]:
    return await service.history(post_id)


@router.post("/decisions", status_code=204)
async def create_moderation_decision(
    payload: ModerationRequest, actor: ModeratorDep, service: ModerationDep
) -> None:
    """Compatibility route. Enqueues work; inspect report/operations to verify completion."""
    if payload.moderator_id != actor.id:
        raise HTTPException(status_code=403, detail="moderator_id must match bearer identity")
    await service.moderate_post(payload.report_id, payload.post_id, actor.id, payload.decision)


@router.get("/posts/{post_id}/state")
async def inspect(post_id: UUID, actor: ModeratorDep, service: ModerationDep) -> dict[str, object]:
    """Inspect persisted visibility, real feed membership and the two existing P5 counters."""
    return await service.inspect(post_id)
