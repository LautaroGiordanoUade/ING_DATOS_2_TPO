from dataclasses import dataclass

from app.application.services.operation import OperationContext
from app.domain.entities import Post


@dataclass(slots=True)
class PublicationJob:
    post: Post
    operation: OperationContext
    fingerprint: str
    followers: list[str] | None = None
    offset: int = 0
    rollback: bool = False
    fail_at: str | None = None
