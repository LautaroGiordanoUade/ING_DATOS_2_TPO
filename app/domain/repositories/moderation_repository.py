from typing import Protocol
from uuid import UUID

from app.domain.entities import ModerationReport


class ModerationRepository(Protocol):
    async def create_report(self, report: ModerationReport) -> ModerationReport: ...
    async def resolve_report(self, report_id: UUID, moderator_id: UUID, status: str) -> None: ...
    async def reverse_resolution(self, report_id: UUID) -> None: ...

