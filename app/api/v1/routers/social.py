from fastapi import APIRouter

from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import FollowRequest

router = APIRouter()


@router.post("/follows", status_code=204)
async def create_follow(payload: FollowRequest, demo_mode: DemoModeDep) -> None:
    if demo_mode:
        return
    del payload
    # TODO(TP): Reutilizar Problema 2.
    raise FeatureNotImplementedError("Seguir usuario")


@router.delete("/follows", status_code=204)
async def delete_follow(payload: FollowRequest, demo_mode: DemoModeDep) -> None:
    if demo_mode:
        return
    del payload
    # TODO(TP): Reutilizar Problema 2 con semántica idempotente.
    raise FeatureNotImplementedError("Dejar de seguir usuario")

