from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Participant(BaseModel):
    id: UUID
    username: str
    full_name: str


class Group(BaseModel):
    id: UUID
    name: str
    participant_ids: list[UUID]
    created_at: datetime
    sequence: int = 0
    read_through: dict[str, int] = Field(default_factory=dict)
    participants: list[Participant] = Field(default_factory=list)
    unread: int = 0


class GroupMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    text: str
    sequence: int
    created_at: datetime
    delivery_status: Literal["pending", "completed"] = "pending"
    error: str | None = None
    author_name: str = ""
    completed_steps: list[str] = Field(default_factory=lambda: ["mongo_persist"])


class MessagePage(BaseModel):
    items: list[GroupMessage]
    next_before: int | None = None


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    participant_ids: list[UUID] = Field(min_length=1, max_length=19)


class MessageText(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=4000)


class ReadThrough(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID


class MessagingLock(Protocol):
    def hold(self, conversation_id: UUID) -> AbstractAsyncContextManager[None]: ...


class MessagingStore(Protocol):
    async def ensure_indexes(self) -> None: ...
    async def participants(self, ids: list[UUID]) -> list[Participant]: ...
    async def search(self, actor: UUID, query: str) -> list[Participant]: ...
    async def create_group(self, actor: UUID, payload: GroupCreate, key: str) -> Group: ...
    async def group(self, group_id: UUID) -> Group | None: ...
    async def groups(self, actor: UUID, before: UUID | None, limit: int) -> list[Group]: ...
    async def send(self, group: Group, actor: UUID, text: str, key: str) -> GroupMessage: ...
    async def message(self, message_id: UUID) -> GroupMessage | None: ...
    async def history(self, group_id: UUID, before: int | None, limit: int) -> MessagePage: ...
    async def read(self, group_id: UUID, actor: UUID, sequence: int) -> None: ...
    async def unread(self, group: Group, actor: UUID) -> int: ...
    async def pending_messages(self, group_id: UUID) -> list[GroupMessage]: ...
    async def complete(self, message_id: UUID) -> None: ...
    async def checkpoint(self, message_id: UUID, step: str) -> None: ...
    async def failed(self, message_id: UUID, error: str) -> None: ...
    async def dirty(self, group_id: UUID, value: bool) -> None: ...
    async def pending_groups(self) -> list[UUID]: ...


class MessagingViews(Protocol):
    async def set_unread(self, group_id: UUID, actor: UUID, count: int) -> None: ...
    async def unread(self, group_id: UUID, actor: UUID) -> int: ...
    async def notify(self, message: GroupMessage, recipient: UUID) -> None: ...
