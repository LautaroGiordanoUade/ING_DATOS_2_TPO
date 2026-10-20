from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ModerationSnapshot(BaseModel):
    moderation_status: str
    owner: str | None = None
    feeds: dict[str, float] = Field(default_factory=dict)
    counters: dict[str, int] = Field(default_factory=dict)


class ModerationJob(BaseModel):
    operation_id: UUID
    report_id: UUID
    post_id: UUID
    moderator_id: UUID
    action: Literal["hide", "reject", "revert"]
    reason: str
    status: str = "pending"
    active: bool = True
    snapshot: ModerationSnapshot | None = None
    restore: ModerationSnapshot | None = None
    completed_steps: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    error: str | None = None
    resume_phase: str = "pending"
    fail_at: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
