from fastapi import APIRouter

from app.api.demo_data import demo_post
from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import PostCreate, PostResponse

router = APIRouter()


@router.post("", response_model=PostResponse)
async def create_post(payload: PostCreate, demo_mode: DemoModeDep) -> PostResponse:
    if demo_mode:
        return demo_post(payload.user_id)
    del payload
    # TODO(TP): Reutilizar caso de publicación e idempotencia.
    raise FeatureNotImplementedError("Crear publicación")

