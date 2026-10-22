from uuid import UUID

from app.domain.counter_names import CONVERSATION_UNREAD
from app.domain.repositories import (
    CounterRepository,
    MessageRepository,
)


class MarkMessageReadUseCase:
    def __init__(
        self,
        messages: MessageRepository,
        counters: CounterRepository,
    ) -> None:
        self._messages = messages
        self._counters = counters

    async def execute(
        self,
        message_id: UUID,
        participant_id: UUID,
    ) -> None:

        await self._messages.mark_read(
            message_id,
            participant_id,
        )

        await self._counters.increment(
            CONVERSATION_UNREAD,
            participant_id,
            -1,
        )