from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.use_cases import get_feed_use_case
from app.application.services.feed_page import FeedExpiredError
from app.application.use_cases import GetFeedUseCase
from app.schemas.models import FeedResponse

router = APIRouter(
    responses={
        401: {"description": "Login requerido"},
        403: {"description": "Feed de otro usuario"},
        410: {"description": "Cursor vencido; refresque el feed"},
        422: {"description": "Cursor invalido"},
        503: {"description": "Motor no disponible"},
    }
)


@router.get("/{user_id}", response_model=FeedResponse)
async def get_user_feed(
    user_id: UUID,
    service: Annotated[GetFeedUseCase, Depends(get_feed_use_case)],
    actor: CurrentUserDep,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> object:
    """20 posts, recency/relevance in 200-candidate windows; navigation expires in 15 min."""
    if actor.id != user_id:
        raise HTTPException(status_code=403, detail="Solo puede consultar su propio feed")
    try:
        return await service.execute(user_id, cursor)
    except FeedExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
