import hashlib
from uuid import UUID
from app.application.ports.conversation_lock import ConversationLock
from app.application.services import (
    CompensationService,
    IdempotencyService,
    OperationContext,
    OperationStep,
    OperationStatus,
)
from app.application.services.idempotency_service import (
    IdempotencyConflictError,
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
        conversation_lock: ConversationLock | None = None,
        idempotency: IdempotencyService | None= None,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._counters = counters
        self._delivery = delivery
        self._compensation = compensation
        self._conversation_lock = conversation_lock
        self._idempotency= idempotency

    @staticmethod
    def _message_fingerprint(
        message: Message,
    ) -> str:
        raw = (
            f"{message.conversation_id}:"
            f"{message.sender_id}:"
            f"{message.text}"
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    async def execute(
        self,
        message: Message,
        idempotency_key: str | None = None,
    ) -> OperationContext:

        if self._conversation_lock is None:
            return await self._execute(
                message,
                idempotency_key,
            )

        async with self._conversation_lock.hold(
            message.conversation_id
        ):
            return await self._execute(
                message,
                idempotency_key,
            )

    async def _execute(
        self,
        message: Message,
        idempotency_key: str | None=None,
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
        
        scoped_key: str | None = None

        fingerprint = self._message_fingerprint(
            message
        )

        if (
            idempotency_key is not None
            and self._idempotency is not None
        ):
            scoped_key = (
                f"message:{message.sender_id}:"
                f"{idempotency_key}"
            )

            try:
                previous = await self._idempotency.begin(
                    scoped_key,
                    "problem_06_send_group_message",
                    fingerprint=fingerprint,
                )
            except IdempotencyConflictError as exc:
                raise ConflictError(str(exc)) from exc

            if previous is not None:
                return OperationContext(
                    operation_type="problem_06_send_group_message",
                    operation_id=UUID(previous.decode()),
                    status=OperationStatus.COMPLETED,
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
        
        try:
            operation = await self._compensation.execute(
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
        except Exception:
            if (
                scoped_key is not None
                and self._idempotency is not None
            ):
                await self._idempotency.release(
                    scoped_key
                )
            raise

        if (
            scoped_key is not None
            and self._idempotency is not None
        ):
            await self._idempotency.complete(
                scoped_key,
                str(operation.operation_id).encode(),
                fingerprint=fingerprint,
            )
        return operation

    