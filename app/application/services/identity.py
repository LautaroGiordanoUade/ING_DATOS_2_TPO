import asyncio

from app.core.exceptions import AuthenticationError
from app.domain.entities import User
from app.domain.entities.models import AccountType
from app.domain.repositories import UserRepository
from app.infrastructure.security.password import PasswordHasher
from app.infrastructure.security.tokens import TokenService


class IdentityService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(
        self,
        username: str,
        full_name: str,
        email: str,
        password: str,
        account_type: AccountType = AccountType.PUBLIC,
        interests: tuple[str, ...] = (),
    ) -> User:
        digest = await asyncio.to_thread(PasswordHasher().hash, password)
        return await self._users.create(
            User(
                username=username,
                full_name=full_name,
                email=email,
                password_hash=digest,
                account_type=account_type,
                interests=interests,
            )
        )

    async def login(self, username: str, password: str) -> str:
        user = await self._users.by_username(username)
        # A dummy hash keeps missing-user verification on the same expensive path.
        digest = (
            user.password_hash if user else ("pbkdf2_sha256$600000$" + "00" * 16 + "$" + "00" * 32)
        )
        valid = await asyncio.to_thread(PasswordHasher().verify, password, digest)
        if not valid or user is None or user.account_status != "active":
            raise AuthenticationError("Invalid credentials")
        return TokenService().create_access_token(user.id, user.auth_version)
