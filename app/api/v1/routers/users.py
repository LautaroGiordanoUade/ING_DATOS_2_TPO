from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies.use_cases import RepositoriesDep
from app.application.services.identity import IdentityService
from app.core.exceptions import ResourceNotFoundError
from app.schemas.models import UserCreate, UserResponse
from app.schemas.moderation import LoginRequest, TokenResponse

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(payload: UserCreate, repositories: RepositoriesDep) -> object:
    return await IdentityService(repositories.users).register(
        payload.username, payload.full_name, payload.email, payload.password
    )


@router.post(
    "/login", response_model=TokenResponse, responses={401: {"description": "Invalid credentials"}}
)
async def login(payload: LoginRequest, repositories: RepositoriesDep) -> TokenResponse:
    token = await IdentityService(repositories.users).login(payload.username, payload.password)
    return TokenResponse(access_token=token)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, repositories: RepositoriesDep) -> object:
    user = await repositories.users.get(user_id)
    if user is None or user.account_status != "active":
        raise ResourceNotFoundError("User not found")
    return user
