from uuid import UUID

from pydantic import BaseModel, Field


class FeedPosition(BaseModel):
    session_id: UUID
    user_id: UUID
    expires: int
    window: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0, le=200)


class FeedSession(BaseModel):
    id: UUID
    user_id: UUID
    expires: int
    anchor: float


class FeedWindow(BaseModel):
    ids: list[UUID]
    boundary_score: float
    boundary_id: str
    more: bool


class FeedCandidates(BaseModel):
    rows: list[tuple[UUID, float]]
    more: bool


class FeedExpiredError(Exception):
    """The short-lived navigation has expired; start a new feed request."""
