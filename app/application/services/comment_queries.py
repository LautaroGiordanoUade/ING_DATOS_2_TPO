from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel

from app.core.exceptions import ResourceNotFoundError
from app.domain.comments import VisibleComment
from app.domain.repositories import CommentRepository, PostRepository


class CommentPosition(BaseModel):
    post_id: UUID
    comment_id: UUID
    created_at: AwareDatetime


class CommentCursor(Protocol):
    def encode(self, position: CommentPosition) -> str: ...
    def decode(self, token: str, post_id: UUID) -> CommentPosition: ...


@dataclass(frozen=True)
class CommentPage:
    items: tuple[VisibleComment, ...]
    next_cursor: str | None


class CommentQueries:
    def __init__(
        self, posts: PostRepository, comments: CommentRepository, cursor: CommentCursor
    ) -> None:
        self._posts, self._comments, self._cursor = posts, comments, cursor

    async def _available(self, post_id: UUID) -> None:
        post = await self._posts.get(post_id)
        if post is None or post.visibility != "public":
            raise ResourceNotFoundError("Public post not found")

    async def page(self, post_id: UUID, cursor: str | None, limit: int) -> CommentPage:
        await self._available(post_id)
        position = None if cursor is None else self._cursor.decode(cursor, post_id)
        before = None if position is None else (position.created_at, position.comment_id)
        rows = await self._comments.visible_page(post_id, before, limit + 1)
        await self._available(post_id)
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = self._cursor.encode(
                CommentPosition(
                    post_id=post_id,
                    comment_id=last.id,
                    created_at=last.created_at,
                )
            )
        return CommentPage(items=items, next_cursor=next_cursor)
