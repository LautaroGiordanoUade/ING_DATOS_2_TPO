from dataclasses import dataclass
from uuid import UUID

from app.domain.entities import Conversation, Post, User


@dataclass(frozen=True, slots=True)
class UserTrace:
    user_id: UUID
    profile: User | None
    relationships: dict[str, object]
    recent_posts: tuple[Post, ...]
    active_conversations: tuple[Conversation, ...]

