from fastapi import APIRouter

from app.api.demo_data import demo_message
from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import MessageCreate, MessageResponse

router = APIRouter()


@router.post("", response_model=MessageResponse)
async def create_message(payload: MessageCreate, demo_mode: DemoModeDep) -> MessageResponse:
    if demo_mode:
        return demo_message(payload.sender_id)
    del payload
    raise FeatureNotImplementedError("Enviar mensaje")

