from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FeedCursor:
    score: float
    item_id: UUID


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    next_cursor: FeedCursor | None = None

