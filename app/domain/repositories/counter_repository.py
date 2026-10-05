from typing import Protocol
from uuid import UUID


class CounterRepository(Protocol):
    async def increment(self, namespace: str, entity_id: UUID, amount: int = 1) -> int: ...
    async def get_many(self, namespace: str, entity_ids: tuple[UUID, ...]) -> dict[UUID, int]: ...

