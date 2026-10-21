#Guardar un comentario, y borrarlo
from typing import Protocol
from uuid import UUID

from app.domain.entities import Comment


class CommentRepository(Protocol):
    async def create(self, comment: Comment) -> Comment: ...
    async def delete(self, comment_id: UUID) -> None: ...
    async def count_for_post(self, post_id: UUID) -> int: ...
