from fastapi import APIRouter

from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import CommentCreate, ReactionCreate

router = APIRouter()


@router.post("/reactions", status_code=204)
async def create_reaction(payload: ReactionCreate, demo_mode: DemoModeDep) -> None:
    if demo_mode:
        return
    del payload
    raise FeatureNotImplementedError("Crear o cambiar reacción")


@router.post("/comments", status_code=204)
async def create_comment(payload: CommentCreate, demo_mode: DemoModeDep) -> None:
    if demo_mode:
        return
    del payload
    raise FeatureNotImplementedError("Crear comentario")

