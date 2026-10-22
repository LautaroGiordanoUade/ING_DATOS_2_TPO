from app.application.services import CompensationService
from app.core.exceptions import (ConflictError, ResourceNotFoundError,)
from app.domain.entities import Message
from app.domain.repositories import (
    ConversationRepository,
    CounterRepository,
    MessageRepository,
    NotificationRepository,
)


class SendGroupMessageUseCase:
    def __init__(
        self,
        conversations: ConversationRepository,
        messages: MessageRepository,
        counters: CounterRepository,
        delivery: NotificationRepository,
        compensation: CompensationService,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._counters = counters
        self._delivery = delivery
        self._compensation = compensation

    async def execute(self, message: Message) -> None:
        conversation = await self._conversations.get(
            message.conversation_id
        )
        if conversation is None:
            raise ResourceNotFoundError(
                "Conversación no encontrada"
                )
        if message.sender_id not in conversation.participant_ids:
            raise ConflictError(
                "El usuario no pertenece a la conversación"
            )
        await self._messages.create(message)