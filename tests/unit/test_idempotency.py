import pytest

from app.application.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyService,
)


class FakeIdempotencyRepository:
    def __init__(self) -> None:
        self.reserved: set[str] = set()
        self.results: dict[str, bytes] = {}

    async def reserve(self, key: str, operation_name: str, ttl_seconds: int) -> bool:
        del operation_name, ttl_seconds
        if key in self.reserved:
            return False
        self.reserved.add(key)
        return True

    async def get_result(self, key: str) -> bytes | None:
        return self.results.get(key)

    async def store_result(self, key: str, result: bytes, ttl_seconds: int) -> None:
        del ttl_seconds
        self.results[key] = result


@pytest.mark.asyncio
async def test_idempotency_returns_completed_result() -> None:
    repository = FakeIdempotencyRepository()
    service = IdempotencyService(repository)
    assert await service.begin("key", "publish") is None
    await service.complete("key", b"result")
    assert await service.begin("key", "publish") == b"result"


@pytest.mark.asyncio
async def test_idempotency_rejects_duplicate_in_flight_operation() -> None:
    repository = FakeIdempotencyRepository()
    service = IdempotencyService(repository)
    await service.begin("key", "publish")
    with pytest.raises(IdempotencyConflictError):
        await service.begin("key", "publish")

