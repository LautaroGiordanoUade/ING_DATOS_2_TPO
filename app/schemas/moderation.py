from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "post_id": "71000000-0000-0000-0000-000000000001",
                    "reason": "spam",
                    "description": "Contenido de prueba para problema 7",
                }
            ]
        },
    )
    post_id: UUID
    reason: Literal["spam", "abuse", "hate", "violence", "other"]
    description: str | None = Field(default=None, max_length=2000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={"examples": [{"decision": "hide", "reason": "Spam confirmado"}]},
    )
    decision: Literal["hide", "reject"]
    reason: str = Field(min_length=1, max_length=1000)


class RevertRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={"examples": [{"reason": "Revision: contenido permitido"}]},
    )
    reason: str = Field(min_length=1, max_length=1000)


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    post_id: UUID
    reporter_id: UUID
    reason: str
    description: str | None = None
    resolution_status: str
    target_type: Literal["post"] = "post"
    reported_at: datetime
    moderator_id: UUID | None = None
    resolved_at: datetime | None = None
    decision: str | None = None
    decision_reason: str | None = None
    operation_id: UUID | None = None
    resolution_operation_id: UUID | None = None
    resolution_report_id: UUID | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class ModerationContentResponse(BaseModel):
    id: UUID
    user_id: UUID
    text: str
    media: list[str]
    interests: list[str]
    published_at: datetime
    visibility: str
    moderation_status: str
    moderation_owner: UUID | None
    active_operation_id: UUID | None
    report_operation_id: UUID | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
