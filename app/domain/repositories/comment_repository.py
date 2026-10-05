from typing import Protocol
from uuid import UUID

from app.domain.entities import Comment


class CommentRepository(Protocol):
    async def create(self, comment: Comment) -> Comment: ...
    async def delete(self, comment_id: UUID) -> None: ...

