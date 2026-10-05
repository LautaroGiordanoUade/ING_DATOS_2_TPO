import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.postgres.base import Base


class ModerationReportModel(Base):
    __tablename__ = "moderation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    resolution_status: Mapped[str] = mapped_column(String(30), index=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

