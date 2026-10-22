from app.application.services import CompensationService
from app.core.exceptions import (ConflictError, ResourceNotFoundError,)
from app.domain.entities import Message
from app.domain.repositories import (
    ConversationRepository,
    CounterRepository,
    MessageRepository,
    NotificationRepository,
)
from app.domain.counter_names import CONVERSATION_UNREAD


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
        for participant_id in conversation.participant_ids: 
            if participant_id != message.sender_id: 
                await self._counters.increment( 
                    CONVERSATION_UNREAD, 
                    participant_id, 
                    1, 
                )     
        for participant_id in conversation.participant_ids:
            if participant_id != message.sender_id:
                await self._delivery.publish(
                    participant_id,
                    {
                        "event_id": str(message.id),
                        "type": "group_message",
                        "conversation_id": str(
                            message.conversation_id
                        ),
                        "message_id": str(message.id),
                        "sender_id": str(message.sender_id),
                    },
                )

