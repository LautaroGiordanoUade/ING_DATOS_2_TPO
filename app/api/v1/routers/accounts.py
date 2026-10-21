from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies.auth import CurrentUserDep, ModeratorDep
from app.api.dependencies.use_cases import FailureInjectorDep, get_suspend_trace_use_case
from app.application.services.account_job import AccountJob
from app.application.use_cases import SuspendAndTraceUserUseCase
from app.schemas.accounts import AccountDecision
from app.schemas.models import UserTraceResponse

router = APIRouter(
    responses={
        401: {"description": "Invalid, expired or revoked bearer"},
        403: {"description": "Moderator/admin required or private trace"},
        404: {"description": "Account/operation not found"},
        409: {"description": "Concurrent or invalid account transition"},
        422: {"description": "Invalid payload or key"},
        503: {"description": "A required storage is temporarily unavailable"},
    }
)
AccountDep = Annotated[SuspendAndTraceUserUseCase, Depends(get_suspend_trace_use_case)]


@router.post("/{user_id}/suspend", response_model=AccountJob, status_code=202)
async def suspend(
    user_id: UUID,
    payload: AccountDecision,
    actor: ModeratorDep,
    service: AccountDep,
    injector: FailureInjectorDep,
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AccountJob:
    """Durable suspension. Poll the operation until completed, compensated or failed."""
    return await service.suspend_user(
        user_id, payload.reason, actor.id, key, getattr(injector, "fail_at", None)
    )


@router.post("/{user_id}/reactivate", response_model=AccountJob, status_code=202)
async def reactivate(
    user_id: UUID,
    payload: AccountDecision,
    actor: ModeratorDep,
    service: AccountDep,
    injector: FailureInjectorDep,
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AccountJob:
    """Restore suspension effects; preserve P7 moderation and require a fresh login/heartbeat."""
    return await service.suspend_user(
        user_id,
        payload.reason,
        actor.id,
        key,
        getattr(injector, "fail_at", None),
        action="reactivate",
    )


@router.get("/operations/{operation_id}", response_model=AccountJob)
async def operation(operation_id: UUID, actor: ModeratorDep, service: AccountDep) -> AccountJob:
    return await service.job(operation_id)


@router.post("/operations/{operation_id}/retry", response_model=AccountJob, status_code=202)
async def retry(operation_id: UUID, actor: ModeratorDep, service: AccountDep) -> AccountJob:
    """Resume failed compensation/commit. A compensated command needs a fresh request key."""
    return await service.retry(operation_id)


@router.get("/{user_id}/history")
async def history(
    user_id: UUID, actor: ModeratorDep, service: AccountDep
) -> list[dict[str, object]]:
    return await service.history(user_id)


@router.get("/{user_id}/trace", response_model=UserTraceResponse)
async def trace(user_id: UUID, actor: CurrentUserDep, service: AccountDep) -> object:
    if actor.id != user_id and actor.role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Only the account owner or moderator may trace")
    return await service.trace_user(user_id)


@router.put("/me/presence", status_code=204)
async def heartbeat(actor: CurrentUserDep, service: AccountDep) -> None:
    """Renew real Redis presence for 120 seconds. Suspension atomically prevents late heartbeats."""
    await service.heartbeat(actor.id)


@router.get("/{user_id}/presence")
async def presence(user_id: UUID, actor: CurrentUserDep, service: AccountDep) -> dict[str, bool]:
    return {"online": await service.presence(user_id)}
