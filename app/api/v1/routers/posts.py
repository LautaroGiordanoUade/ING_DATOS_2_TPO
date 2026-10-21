from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.use_cases import RepositoriesDep, get_publish_use_case
from app.application.services.content_queries import ContentQueries
from app.application.use_cases import PublishContentUseCase
from app.domain.entities import Post
from app.schemas.models import PostCreate, PostResponse, PublicationResponse

router = APIRouter()


@router.post(
    "",
    response_model=PublicationResponse,
    status_code=202,
    responses={
        401: {"description": "Login required"},
        403: {"description": "Author must match bearer"},
    },
)
async def create_post(
    payload: PostCreate,
    actor: CurrentUserDep,
    service: Annotated[PublishContentUseCase, Depends(get_publish_use_case)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PublicationResponse:
    if payload.user_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo puede publicar desde su propia cuenta")
    job = await service.execute(
        Post(
            user_id=payload.user_id,
            text=payload.text,
            media=tuple(payload.media),
            interests=tuple(payload.interests),
            visibility=payload.visibility,
        ),
        idempotency_key,
    )
    return PublicationResponse(
        operation_id=job.operation.operation_id,
        post_id=job.post.id,
        status=job.operation.status.value,
    )


@router.get("/by-user/{user_id}", response_model=list[PostResponse])
async def by_author(user_id: UUID, repositories: RepositoriesDep) -> object:
    return await ContentQueries(repositories.posts, repositories.counters).by_author(user_id)


@router.get("/{post_id}", response_model=PostResponse)
async def detail(post_id: UUID, repositories: RepositoriesDep) -> object:
    return await ContentQueries(repositories.posts, repositories.counters).detail(post_id)
