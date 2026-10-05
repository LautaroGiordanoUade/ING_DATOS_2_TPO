from app.application.services import CompensationService
from app.core.exceptions import FeatureNotImplementedError
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
        # TODO(TP): Persistir antes de entregar; definir compensación e idempotencia.
        # TODO(TP): Actualizar unread por participante y presencia/entrega Redis.
        raise FeatureNotImplementedError("Problema 6: mensaje grupal")
