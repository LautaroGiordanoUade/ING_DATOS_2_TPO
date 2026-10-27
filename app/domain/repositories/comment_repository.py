# Guardar un comentario, y borrarlo
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.comments import VisibleComment
from app.domain.entities import Comment


class CommentRepository(Protocol):
    async def create(self, comment: Comment) -> Comment: ...
    async def get(self, comment_id: UUID) -> Comment | None: ...
    async def delete(self, comment_id: UUID) -> None: ...
    async def count_for_post(self, post_id: UUID) -> int: ...

    async def visible_page(
        self, post_id: UUID, before: tuple[datetime, UUID] | None, limit: int
    ) -> tuple[VisibleComment, ...]: ...
