
from app.application.services import (
    CompensationService,
    OperationContext,
    OperationStep,
)
from app.core.exceptions import (
    ConflictError,
    ResourceNotFoundError,
)
from app.domain.counter_names import CONVERSATION_UNREAD
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

    async def execute(
        self,
        message: Message,
    ) -> OperationContext:

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

        message_saved = False
        unread_updated = False
        message_delivered = False

        async def save_message() -> None:
            nonlocal message_saved

            message_saved = True
            await self._messages.create(message)

        async def delete_message() -> None:
            if message_saved:
                await self._messages.delete(message.id)

        async def increment_unread() -> None:
            nonlocal unread_updated

            unread_updated = True

            for participant_id in conversation.participant_ids:
                if participant_id != message.sender_id:
                    await self._counters.increment(
                        CONVERSATION_UNREAD,
                        participant_id,
                        1,
                    )

        async def rollback_unread() -> None:
            if not unread_updated:
                return

            for participant_id in conversation.participant_ids:
                if participant_id != message.sender_id:
                    await self._counters.increment(
                        CONVERSATION_UNREAD,
                        participant_id,
                        -1,
                    )

        async def deliver_message() -> None:
            nonlocal message_delivered

            message_delivered = True

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

        async def revoke_delivery() -> None:
            if not message_delivered:
                return

            for participant_id in conversation.participant_ids:
                if participant_id != message.sender_id:
                    await self._delivery.revoke(
                        participant_id,
                        message.id,
                    )

        operation = OperationContext(
            operation_type="problem_06_send_group_message"
        )

        return await self._compensation.execute(
            operation,
            [
                OperationStep(
                    "mongo_create_message",
                    save_message,
                    delete_message,
                    compensate_on_failure=True,
                ),
                OperationStep(
                    "redis_increment_unread",
                    increment_unread,
                    rollback_unread,
                    compensate_on_failure=True,
                ),
                OperationStep(
                    "redis_publish_message",
                    deliver_message,
                    revoke_delivery,
                    compensate_on_failure=True,
                ),
            ],
        )