from datetime import datetime
from typing import cast
from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Conversation, Message


class MongoConversationRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def get(self, conversation_id: UUID) -> Conversation | None:
        doc = await self._database["conversations"].find_one({"_id": str(conversation_id)})
        return None if doc is None else self._conversation(doc)

    @staticmethod
    def _conversation(doc: dict[str, object]) -> Conversation:
        return Conversation(
            id=UUID(str(doc["_id"])),
            participant_ids=tuple(
                UUID(identifier) for identifier in cast(list[str], doc["participant_ids"])
            ),
            created_at=cast(datetime, doc["created_at"]),
        )

    async def list_active_for_user(self, user_id: UUID) -> tuple[Conversation, ...]:
        docs = (
            await self._database["conversations"]
            .find({"participant_ids": str(user_id), "archived": {"$ne": True}})
            .sort("created_at", -1)
            .limit(100)
            .to_list()
        )
        return tuple(self._conversation(doc) for doc in docs)


class MongoMessageRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def create(self, message: Message) -> Message:
        # TODO(TP): Persistir mensaje antes de entrega y definir idempotencia.
        raise FeatureNotImplementedError("MongoMessageRepository.create")

    async def delete(self, message_id: UUID) -> None:
        # TODO(TP): Implementar compensación según la política elegida.
        raise FeatureNotImplementedError("MongoMessageRepository.delete")

    async def mark_read(self, message_id: UUID, participant_id: UUID) -> None:
        # TODO(TP): Actualizar read_by por participante de forma concurrentemente segura.
        raise FeatureNotImplementedError("MongoMessageRepository.mark_read")
