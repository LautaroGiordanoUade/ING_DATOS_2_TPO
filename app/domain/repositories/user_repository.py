from typing import Protocol
from uuid import UUID

from app.domain.entities import User


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None: ...

    async def create(self, user: User) -> User: ...

    async def update_account_status(self, user_id: UUID, status: str) -> None: ...

