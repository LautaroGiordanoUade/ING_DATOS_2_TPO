from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Conversation, Message


class MongoConversationRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def get(self, conversation_id: UUID) -> Conversation | None:
        # TODO(TP): Consultar conversación y participantes.
        raise FeatureNotImplementedError("MongoConversationRepository.get")

    async def list_active_for_user(self, user_id: UUID) -> tuple[Conversation, ...]:
        # TODO(TP): Definir actividad e implementar consulta para trazabilidad.
        raise FeatureNotImplementedError("MongoConversationRepository.list_active_for_user")


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

