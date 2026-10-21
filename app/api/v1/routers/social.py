from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.use_cases import FailureInjectorDep, get_follow_use_case
from app.application.services.follow_job import FollowJob
from app.application.use_cases import FollowUserUseCase
from app.schemas.models import FollowRequest

router = APIRouter(
    responses={
        401: {"description": "Login requerido"},
        403: {"description": "Identidad no autorizada"},
        404: {"description": "Usuario u operacion inexistente"},
        409: {"description": "Conflicto de estado o solicitud concurrente"},
        422: {"description": "Seguimiento invalido"},
    }
)
FollowDep = Annotated[FollowUserUseCase, Depends(get_follow_use_case)]
KeyDep = Annotated[str | None, Header(alias="Idempotency-Key")]


def authorize_operation(job: FollowJob, actor_id: UUID, role: str) -> None:
    if actor_id not in (job.follower_id, job.followed_id) and role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Operacion privada de seguimiento")


@router.post("/follows", response_model=FollowJob, status_code=202)
async def create_follow(
    payload: FollowRequest,
    actor: CurrentUserDep,
    service: FollowDep,
    injector: FailureInjectorDep,
    key: KeyDep = None,
) -> FollowJob:
    if payload.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo puede seguir desde su propia cuenta")
    return await service.follow(
        actor.id, payload.followed_user_id, key, getattr(injector, "fail_at", None)
    )


@router.delete("/follows", response_model=FollowJob, status_code=202)
async def delete_follow(
    payload: FollowRequest,
    actor: CurrentUserDep,
    service: FollowDep,
    injector: FailureInjectorDep,
    key: KeyDep = None,
) -> FollowJob:
    if payload.user_id != actor.id:
        raise HTTPException(
            status_code=403, detail="Solo puede dejar de seguir desde su propia cuenta"
        )
    return await service.unfollow(
        actor.id, payload.followed_user_id, key, getattr(injector, "fail_at", None)
    )


@router.post("/follows/approve", response_model=FollowJob, status_code=202)
async def approve_follow(
    payload: FollowRequest,
    actor: CurrentUserDep,
    service: FollowDep,
    injector: FailureInjectorDep,
    key: KeyDep = None,
) -> FollowJob:
    if payload.followed_user_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo el destinatario aprueba solicitudes")
    return await service.approve(payload.user_id, actor.id, key, getattr(injector, "fail_at", None))


@router.get("/requests")
async def incoming_requests(actor: CurrentUserDep, service: FollowDep) -> tuple[UUID, ...]:
    return await service.requests(actor.id)


@router.get("/operations/{operation_id}", response_model=FollowJob)
async def follow_operation(
    operation_id: UUID, actor: CurrentUserDep, service: FollowDep
) -> FollowJob:
    job = await service.job(operation_id)
    authorize_operation(job, actor.id, actor.role)
    return job


@router.post("/operations/{operation_id}/retry", response_model=FollowJob, status_code=202)
async def retry_follow(operation_id: UUID, actor: CurrentUserDep, service: FollowDep) -> FollowJob:
    authorize_operation(await service.job(operation_id), actor.id, actor.role)
    return await service.retry(operation_id)


@router.get("/relations/{followed_id}")
async def relationship(
    followed_id: UUID, actor: CurrentUserDep, service: FollowDep
) -> dict[str, object]:
    return await service.relationship(actor.id, followed_id)


@router.get("/counts/{user_id}")
async def follow_counts(user_id: UUID, actor: CurrentUserDep, service: FollowDep) -> dict[str, int]:
    return await service.counts(user_id)
