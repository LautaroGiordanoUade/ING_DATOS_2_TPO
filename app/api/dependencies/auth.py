from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies.use_cases import RepositoriesDep
from app.domain.entities import User
from app.infrastructure.security.tokens import TokenService

bearer = HTTPBearer(auto_error=False, description="Obtain a token from POST /api/v1/users/login")


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    repositories: RepositoriesDep,
) -> User:
    try:
        if credentials is None:
            raise ValueError("Missing bearer")
        user_id = TokenService().verify_access_token(credentials.credentials)
        version = TokenService().token_version(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired credential",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = await repositories.users.get(user_id)
    if user is None or user.account_status != "active" or user.auth_version != version:
        raise HTTPException(
            status_code=401, detail="Account unavailable", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]


async def moderator(user: CurrentUserDep) -> User:
    if user.role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Moderator or admin role required")
    return user


ModeratorDep = Annotated[User, Depends(moderator)]
