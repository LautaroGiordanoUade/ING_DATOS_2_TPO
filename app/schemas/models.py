from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.interests import normalize_interests


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnReactionResponse(ApiModel):
    kind: str | None


class UserCreate(ApiModel):
    interests: list[str] = Field(default_factory=list, max_length=20)
    account_type: Literal["public", "private"] = "public"
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=150)
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        return list(normalize_interests(values))


class UserInterestsUpdate(ApiModel):
    model_config = ConfigDict(extra="forbid")
    interests: list[str] = Field(max_length=20)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        return list(normalize_interests(values))


class UserUpdate(ApiModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    biography: str | None = Field(default=None, max_length=500)


class UserResponse(ApiModel):
    interests: list[str] = Field(default_factory=list)
    id: UUID
    username: str
    full_name: str
    biography: str | None
    account_type: str
    account_status: str
    registered_at: datetime
    role: str = "user"


class PostCreate(ApiModel):
    user_id: UUID
    text: str = Field(min_length=1, max_length=10_000)
    media: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    visibility: str = "public"


class PostResponse(ApiModel):
    id: UUID
    user_id: UUID
    text: str
    media: list[str]
    interests: list[str]
    published_at: datetime
    reaction_count: int = 0
    comment_count: int = 0


class FollowRequest(ApiModel):
    user_id: UUID
    followed_user_id: UUID


class FeedCursorSchema(ApiModel):
    score: float
    item_id: UUID


class FeedResponse(ApiModel):
    items: list[PostResponse]
    next_cursor: str | None = None


class MutualFriendsRequest(ApiModel):
    user_id: UUID
    other_user_id: UUID


class ReactionCreate(ApiModel):
    post_id: UUID
    user_id: UUID
    kind: str = Field(min_length=1, max_length=30)


class ReactionRemove(ApiModel):
    post_id: UUID
    user_id: UUID


class CommentCreate(ApiModel):
    post_id: UUID
    user_id: UUID
    text: str = Field(min_length=1, max_length=2_000)


class MessageCreate(ApiModel):
    conversation_id: UUID
    sender_id: UUID
    text: str = Field(min_length=1, max_length=10_000)


class MessageResponse(ApiModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    text: str
    read_by: set[UUID]
    created_at: datetime


class ModerationRequest(ApiModel):
    report_id: UUID
    post_id: UUID
    moderator_id: UUID
    decision: str


class SuspensionRequest(ApiModel):
    user_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class UserTraceResponse(ApiModel):
    user_id: UUID
    profile: UserResponse | None
    relationships: dict[str, object]
    recent_posts: list[PostResponse]
    active_conversations: list[dict[str, object]]
    post_states: list[dict[str, object]] = Field(default_factory=list)
    presence: bool = False
    account_history: list[dict[str, object]] = Field(default_factory=list)


class OperationResponse(ApiModel):
    operation_id: UUID
    status: str


class PublicationResponse(OperationResponse):
    post_id: UUID


class OperationDetailResponse(OperationResponse):
    post_id: UUID | None = None
    operation_type: str
    current_step: str | None
    completed_steps: list[str]
    error: str | None
    created_at: datetime
    updated_at: datetime


class HealthResponse(ApiModel):
    status: str


class ReadinessResponse(ApiModel):
    status: str
    services: dict[str, str]
