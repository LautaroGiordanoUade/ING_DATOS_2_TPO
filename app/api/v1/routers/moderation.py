from fastapi import APIRouter

from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import ModerationRequest

router = APIRouter()


@router.post("/decisions", status_code=204)
async def create_moderation_decision(
    payload: ModerationRequest, demo_mode: DemoModeDep
) -> None:
    if demo_mode:
        return
    del payload
    raise FeatureNotImplementedError("Decisión de moderación")

