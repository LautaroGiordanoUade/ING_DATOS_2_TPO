from uuid import UUID

from fastapi import APIRouter

from app.api.demo_data import demo_feed
from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import FeedResponse

router = APIRouter()


@router.get("/{user_id}", response_model=FeedResponse)
async def get_user_feed(user_id: UUID, demo_mode: DemoModeDep) -> FeedResponse:
    if demo_mode:
        return demo_feed(user_id)
    del user_id
    # TODO(TP): Reutilizar Problema 3 con cursor opaco.
    raise FeatureNotImplementedError("Feed de usuario")

