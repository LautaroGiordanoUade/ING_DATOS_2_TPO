import json

from app.application.ports.idempotency import IdempotencyRepository


class IdempotencyConflictError(RuntimeError):
    pass


class IdempotencyService:
    def __init__(
        self, repository: IdempotencyRepository, ttl_seconds: int = 86_400
    ) -> None:
        self._repository = repository
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _encode_envelope(result: bytes, fingerprint: str | None) -> bytes:
        if fingerprint is None:
            return result
        payload = {
            "fingerprint": fingerprint,
            "result": result.decode(),
        }
        return json.dumps(payload).encode()

    @staticmethod
    def _decode_envelope(raw: bytes, expected_fingerprint: str | None) -> bytes:
        if expected_fingerprint is None:
            return raw
        try:
            data = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw
        if not isinstance(data, dict) or "fingerprint" not in data:
            return raw
        if data["fingerprint"] != expected_fingerprint:
            raise IdempotencyConflictError(
                "La clave de idempotencia ya fue utilizada con un contenido distinto"
            )
        return str(data["result"]).encode()

    async def begin(
        self,
        key: str,
        operation_name: str,
        fingerprint: str | None = None,
    ) -> bytes | None:
        reservation_token = (
            f"{operation_name}:{fingerprint}" if fingerprint else operation_name
        )
        previous = await self._repository.get_result(key)
        if previous is not None:
            return self._decode_envelope(previous, fingerprint)

        reserved = await self._repository.reserve(
            key, reservation_token, self._ttl_seconds
        )
        if not reserved:
            getter = getattr(self._repository, "get_reservation", None)
            if callable(getter) and fingerprint is not None:
                current_token = await getter(key)
                if current_token is not None and current_token != reservation_token:
                    raise IdempotencyConflictError(
                        "La clave de idempotencia está en uso con un contenido distinto"
                    )
            previous = await self._repository.get_result(key)
            if previous is not None:
                return self._decode_envelope(previous, fingerprint)
            raise IdempotencyConflictError("La operación con esta clave ya está en curso")
        return None

    async def complete(
        self, key: str, result: bytes, fingerprint: str | None = None
    ) -> None:
        encoded = self._encode_envelope(result, fingerprint)
        await self._repository.store_result(key, encoded, self._ttl_seconds)

    async def release(self, key: str) -> None:
        await self._repository.release(key)