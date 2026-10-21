from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AccountJob(BaseModel):
    operation_id: UUID
    user_id: UUID
    actor_id: UUID
    action: Literal["suspend", "reactivate"]
    reason: str
    attempt: int = 1
    status: str = "pending"
    active: bool = True
    previous_status: str | None = None
    restore_from: UUID | None = None
    post_ids: list[UUID] = Field(default_factory=list)
    graph_snapshot: dict[str, object] | None = None
    completed_steps: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    error: str | None = None
    resume_phase: str = "pending"
    fail_at: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
