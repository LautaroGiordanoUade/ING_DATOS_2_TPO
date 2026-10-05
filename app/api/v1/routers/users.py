from uuid import UUID

from fastapi import APIRouter

from app.api.demo_data import demo_user
from app.api.dependencies.demo import DemoModeDep
from app.core.exceptions import FeatureNotImplementedError
from app.schemas.models import UserCreate, UserResponse

router = APIRouter()


@router.post("", response_model=UserResponse)
async def create_user(payload: UserCreate, demo_mode: DemoModeDep) -> UserResponse:
    if demo_mode:
        return demo_user()
    del payload
    # TODO(TP): Implementar caso de uso de alta, hash y reglas de unicidad.
    raise FeatureNotImplementedError("Crear usuario")


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, demo_mode: DemoModeDep) -> UserResponse:
    if demo_mode:
        return demo_user(user_id)
    del user_id
    # TODO(TP): Implementar consulta de perfil y reglas de exposición.
    raise FeatureNotImplementedError("Obtener usuario")

