import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.application.ports.messaging import (
    Group,
    GroupCreate,
    GroupMessage,
    MessagePage,
    Participant,
)
from app.core.exceptions import ConflictError


class MongoMessagingStore:
    """A message is its own durable outbox: insertion atomically makes it retryable."""

    def __init__(self, database: AsyncDatabase[dict[str, Any]]) -> None:
        self.db = database

    async def ensure_indexes(self) -> None:
        await self.db.conversations.create_index(
            [("creator_id", 1), ("request_key", 1)],
            unique=True,
            partialFilterExpression={"request_key": {"$type": "string"}},
            name="ix_group_request",
        )
        await self.db.conversations.create_index([("participant_ids", 1), ("_id", -1)])
        await self.db.conversations.create_index("redis_pending")
        await self.db.messages.create_index(
            [("sender_id", 1), ("request_key", 1)],
            unique=True,
            partialFilterExpression={"request_key": {"$type": "string"}},
            name="ix_message_request",
        )
        await self.db.messages.create_index(
            [("conversation_id", 1), ("sequence", -1)],
            unique=True,
            partialFilterExpression={"sequence": {"$type": "number"}},
            name="ix_message_sequence",
        )
        await self.db.messages.create_index([("delivery_status", 1), ("conversation_id", 1)])

    @staticmethod
    def _group(doc: dict[str, Any]) -> Group:
        return Group.model_validate(
            {
                **doc,
                "id": doc["_id"],
                "name": doc.get("name", "Grupo"),
                "created_at": doc["created_at"].replace(tzinfo=UTC),
            }
        )

    @staticmethod
    def _message(doc: dict[str, Any]) -> GroupMessage:
        return GroupMessage.model_validate(
            {**doc, "id": doc["_id"], "created_at": doc["created_at"].replace(tzinfo=UTC)}
        )

    async def participants(self, ids: list[UUID]) -> list[Participant]:
        docs = await self.db.users.find(
            {"_id": {"$in": list(map(str, ids))}, "account_status": "active"},
            {"username": 1, "full_name": 1},
        ).to_list()
        return [
            Participant(id=d["_id"], username=d["username"], full_name=d["full_name"]) for d in docs
        ]

    async def search(self, actor: UUID, query: str) -> list[Participant]:
        docs = (
            await self.db.users.find(
                {
                    "_id": {"$ne": str(actor)},
                    "account_status": "active",
                    "username": {"$regex": "^" + re.escape(query.lower())},
                },
                {"username": 1, "full_name": 1},
            )
            .sort("username", 1)
            .limit(20)
            .to_list()
        )
        return [
            Participant(id=d["_id"], username=d["username"], full_name=d["full_name"]) for d in docs
        ]

    async def create_group(self, actor: UUID, payload: GroupCreate, key: str) -> Group:
        ids = sorted({str(actor), *map(str, payload.participant_ids)})
        doc = {
            "_id": str(uuid4()),
            "creator_id": str(actor),
            "name": payload.name,
            "participant_ids": ids,
            "request_key": key,
            "sequence": 0,
            "read_through": {},
            "created_at": datetime.now(UTC),
        }
        try:
            await self.db.conversations.insert_one(doc)
        except DuplicateKeyError:
            saved = await self.db.conversations.find_one(
                {"creator_id": str(actor), "request_key": key}
            )
            if saved is None or saved["name"] != payload.name or saved["participant_ids"] != ids:
                raise ConflictError("La clave ya se usó para otro grupo") from None
            doc = saved
        return self._group(doc)

    async def group(self, group_id: UUID) -> Group | None:
        doc = await self.db.conversations.find_one({"_id": str(group_id)})
        return self._group(doc) if doc else None

    async def groups(self, actor: UUID, before: UUID | None, limit: int) -> list[Group]:
        query: dict[str, Any] = {"participant_ids": str(actor), "archived": {"$ne": True}}
        if before:
            query["_id"] = {"$lt": str(before)}
        docs = await self.db.conversations.find(query).sort("_id", -1).limit(limit).to_list()
        return [self._group(d) for d in docs]

    async def send(self, group: Group, actor: UUID, text: str, key: str) -> GroupMessage:
        query = {"sender_id": str(actor), "request_key": key}
        saved = await self.db.messages.find_one(query)
        if saved is None:
            updated = await self.db.conversations.find_one_and_update(
                {"_id": str(group.id)},
                {"$inc": {"sequence": 1}},
                return_document=ReturnDocument.AFTER,
            )
            assert updated is not None
            saved = {
                "_id": str(uuid4()),
                "conversation_id": str(group.id),
                "sender_id": str(actor),
                "text": text,
                "request_key": key,
                "sequence": updated["sequence"],
                "created_at": datetime.now(UTC),
                "delivery_status": "pending",
                "error": None,
                "completed_steps": ["mongo_persist"],
            }
            try:
                await self.db.messages.insert_one(saved)
            except DuplicateKeyError:
                saved = await self.db.messages.find_one(query)
        if saved is None or saved["conversation_id"] != str(group.id) or saved["text"] != text:
            raise ConflictError("La clave ya se usó para otro mensaje")
        return self._message(saved)

    async def message(self, message_id: UUID) -> GroupMessage | None:
        doc = await self.db.messages.find_one(
            {"_id": str(message_id), "sequence": {"$exists": True}}
        )
        return self._message(doc) if doc else None

    async def history(self, group_id: UUID, before: int | None, limit: int) -> MessagePage:
        query: dict[str, Any] = {"conversation_id": str(group_id), "sequence": {"$exists": True}}
        if before is not None:
            query["sequence"] = {"$lt": before}
        docs = await self.db.messages.find(query).sort("sequence", -1).limit(limit + 1).to_list()
        items = [self._message(d) for d in docs[:limit]]
        authors = await self.db.users.find(
            {"_id": {"$in": [str(m.sender_id) for m in items]}}, {"full_name": 1}
        ).to_list()
        names = {d["_id"]: d["full_name"] for d in authors}
        for item in items:
            item.author_name = names.get(str(item.sender_id), "Usuario no disponible")
        return MessagePage(
            items=items, next_before=items[-1].sequence if len(docs) > limit else None
        )

    async def read(self, group_id: UUID, actor: UUID, sequence: int) -> None:
        await self.db.conversations.update_one(
            {"_id": str(group_id)},
            {"$max": {f"read_through.{actor}": sequence}, "$set": {"redis_pending": True}},
        )

    async def unread(self, group: Group, actor: UUID) -> int:
        return await self.db.messages.count_documents(
            {
                "conversation_id": str(group.id),
                "sender_id": {"$ne": str(actor)},
                "sequence": {"$gt": group.read_through.get(str(actor), 0)},
            }
        )

    async def pending_messages(self, group_id: UUID) -> list[GroupMessage]:
        docs = (
            await self.db.messages.find(
                {"conversation_id": str(group_id), "delivery_status": "pending"}
            )
            .sort("sequence", 1)
            .limit(100)
            .to_list()
        )
        return [self._message(d) for d in docs]

    async def complete(self, message_id: UUID) -> None:
        await self.db.messages.update_one(
            {"_id": str(message_id)},
            {
                "$set": {"delivery_status": "completed", "error": None},
                "$addToSet": {"completed_steps": "redis_distribution"},
            },
        )

    async def checkpoint(self, message_id: UUID, step: str) -> None:
        await self.db.messages.update_one(
            {"_id": str(message_id)}, {"$addToSet": {"completed_steps": step}}
        )

    async def failed(self, message_id: UUID, error: str) -> None:
        await self.db.messages.update_one(
            {"_id": str(message_id)}, {"$set": {"error": error[:500]}}
        )

    async def dirty(self, group_id: UUID, value: bool) -> None:
        await self.db.conversations.update_one(
            {"_id": str(group_id)}, {"$set": {"redis_pending": value}}
        )

    async def pending_groups(self) -> list[UUID]:
        pending = await self.db.messages.aggregate(
            [
                {"$match": {"delivery_status": "pending"}},
                {"$group": {"_id": "$conversation_id"}},
                {"$limit": 100},
            ]
        )
        ids = {UUID(d["_id"]) for d in await pending.to_list()}
        docs = (
            await self.db.conversations.find({"redis_pending": True}, {"_id": 1})
            .limit(100)
            .to_list()
        )
        return list(ids | {UUID(d["_id"]) for d in docs})
