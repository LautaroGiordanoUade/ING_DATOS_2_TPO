from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies.use_cases import get_feed_use_case
from app.application.use_cases import GetFeedUseCase
from app.schemas.models import FeedResponse

router = APIRouter()


@router.get("/{user_id}", response_model=FeedResponse)
async def get_user_feed(
    user_id: UUID, service: Annotated[GetFeedUseCase, Depends(get_feed_use_case)]
) -> object:
    """Chronological visible feed. Personalized ranking/cursors remain P3."""
    return await service.execute(user_id)
