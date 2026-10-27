from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


class AccountType(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ModerationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class Interest:
    name: str
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class User:
    username: str
    full_name: str
    email: str
    password_hash: str
    id: UUID = field(default_factory=uuid4)
    biography: str | None = None
    account_type: AccountType = AccountType.PUBLIC
    account_status: AccountStatus = AccountStatus.ACTIVE
    registered_at: datetime = field(default_factory=utc_now)
    role: str = "user"
    auth_version: int = 0
    interests: tuple[str, ...] = ()


@dataclass(slots=True)
class Post:
    user_id: UUID
    text: str
    id: UUID = field(default_factory=uuid4)
    media: tuple[str, ...] = ()
    content_type: str = "text"
    visibility: str = "public"
    interests: tuple[str, ...] = ()
    moderation_status: ModerationStatus = ModerationStatus.PENDING
    published_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Comment:
    post_id: UUID
    user_id: UUID
    text: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Reaction:
    post_id: UUID
    user_id: UUID
    kind: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Conversation:
    participant_ids: tuple[UUID, ...]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Message:
    conversation_id: UUID
    sender_id: UUID
    text: str
    id: UUID = field(default_factory=uuid4)
    read_by: frozenset[UUID] = field(default_factory=frozenset)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class ModerationReport:
    post_id: UUID
    reporter_id: UUID
    reason: str
    id: UUID = field(default_factory=uuid4)
    moderator_id: UUID | None = None
    resolution_status: str = "pending"
    reported_at: datetime = field(default_factory=utc_now)
    resolved_at: datetime | None = None
    description: str | None = None
