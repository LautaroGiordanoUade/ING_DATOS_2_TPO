from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class VisibleComment:
    id: UUID
    post_id: UUID
    user_id: UUID
    text: str
    created_at: datetime
    author_name: str
    author_username: str | None
