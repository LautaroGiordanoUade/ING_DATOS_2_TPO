from app.application.ports.idempotency import IdempotencyRepository


class IdempotencyConflictError(RuntimeError):
    pass


class IdempotencyService:
    def __init__(self, repository: IdempotencyRepository, ttl_seconds: int = 86_400) -> None:
        self._repository = repository
        self._ttl_seconds = ttl_seconds

    async def begin(self, key: str, operation_name: str) -> bytes | None:
        previous = await self._repository.get_result(key)
        if previous is not None:
            return previous
        reserved = await self._repository.reserve(key, operation_name, self._ttl_seconds)
        if not reserved:
            # Puede que la otra operación haya terminado justo ahora.
            previous = await self._repository.get_result(key)
            if previous is not None:
                return previous
            raise IdempotencyConflictError("La operación con esta clave ya está en curso")
        return None

    async def complete(self, key: str, result: bytes) -> None:
        await self._repository.store_result(key, result, self._ttl_seconds)

    async def release(self, key: str) -> None:
        await self._repository.release(key)