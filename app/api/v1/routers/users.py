from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.use_cases import RepositoriesDep
from app.application.services.identity import IdentityService
from app.core.exceptions import ResourceNotFoundError
from app.domain.entities.models import AccountType
from app.schemas.models import UserCreate, UserInterestsUpdate, UserResponse
from app.schemas.moderation import LoginRequest, TokenResponse

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(payload: UserCreate, repositories: RepositoriesDep) -> object:
    return await IdentityService(repositories.users).register(
        payload.username,
        payload.full_name,
        payload.email,
        payload.password,
        AccountType(payload.account_type),
        tuple(payload.interests),
    )


@router.post(
    "/login", response_model=TokenResponse, responses={401: {"description": "Invalid credentials"}}
)
async def login(payload: LoginRequest, repositories: RepositoriesDep) -> TokenResponse:
    token = await IdentityService(repositories.users).login(payload.username, payload.password)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_current_user(actor: CurrentUserDep) -> object:
    """Validate the bearer against current account state and return its public profile."""
    return actor


@router.put("/me/interests", response_model=UserResponse)
async def update_interests(
    payload: UserInterestsUpdate, actor: CurrentUserDep, repositories: RepositoriesDep
) -> object:
    """Atomically replace only the authenticated active user's declared interests."""
    return await repositories.users.update_interests(actor.id, tuple(payload.interests))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, repositories: RepositoriesDep) -> object:
    user = await repositories.users.get(user_id)
    if user is None or user.account_status != "active":
        raise ResourceNotFoundError("User not found")
    return user
