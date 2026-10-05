from typing import Protocol
from uuid import UUID

from app.domain.value_objects import FeedCursor, Page


class FeedRepository(Protocol):
    async def add_to_feeds(
        self, user_ids: tuple[UUID, ...], post_id: UUID, score: float
    ) -> None: ...

    async def remove_from_feeds(self, post_id: UUID) -> None: ...

    async def get_feed(
        self, user_id: UUID, cursor: FeedCursor | None, limit: int
    ) -> Page[UUID]: ...

    async def clear_user_feed(self, user_id: UUID) -> None: ...

