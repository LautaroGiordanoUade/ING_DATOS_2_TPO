from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.api.dependencies.use_cases import get_interaction_use_case
from app.application.use_cases import InteractWithPostUseCase
from app.domain.entities import Comment, Reaction
from app.schemas.models import CommentCreate, ReactionCreate, ReactionRemove

router = APIRouter()
InteractionDep = Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)]


@router.post("/reactions", status_code=204)
async def create_reaction(payload: ReactionCreate, service: InteractionDep) -> None:
    await service.react(
        Reaction(post_id=payload.post_id, user_id=payload.user_id, kind=payload.kind)
    )


@router.delete("/reactions", status_code=204)
async def delete_reaction(payload: ReactionRemove, service: InteractionDep) -> None:
    await service.remove_reaction(payload.post_id, payload.user_id)


@router.post("/comments", status_code=204)
async def create_comment(
    payload: CommentCreate,
    service: InteractionDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> None:
    await service.comment(
        Comment(post_id=payload.post_id, user_id=payload.user_id, text=payload.text),
        idempotency_key,
    )
