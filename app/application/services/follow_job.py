from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FollowSnapshot(BaseModel):
    gate: str | None = None
    feeds: dict[str, float] = Field(default_factory=dict)


class FollowJob(BaseModel):
    operation_id: UUID
    follower_id: UUID
    followed_id: UUID
    actor_id: UUID
    action: Literal["follow", "unfollow", "approve"]
    participant_ids: list[str] = Field(default_factory=list)
    status: str = "pending"
    active: bool = True
    desired: str | None = None
    graph_snapshot: dict[str, Any] | None = None
    snapshot: FollowSnapshot | None = None
    catalog: list[UUID] = Field(default_factory=list)
    candidates: dict[str, float] | None = None
    completed_steps: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    error: str | None = None
    resume_phase: str = "pending"
    fail_at: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
