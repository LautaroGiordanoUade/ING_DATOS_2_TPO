from typing import Protocol
from uuid import UUID

from app.domain.entities import Reaction


class ReactionRepository(Protocol):
    async def upsert(self, reaction: Reaction) -> Reaction: ...
    async def delete_for_user(self, post_id: UUID, user_id: UUID) -> None: ...

