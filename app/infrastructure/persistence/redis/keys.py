from uuid import UUID


class RedisKeys:
    """Central naming only; final structures and commands remain TODO(TP)."""

    @staticmethod
    def feed(user_id: UUID) -> str:
        return f"feed:{user_id}"

    @staticmethod
    def counter(namespace: str, entity_id: UUID) -> str:
        return f"{namespace}:{entity_id}:count"

    @staticmethod
    def unread(user_id: UUID) -> str:
        return f"user:{user_id}:unread"

    @staticmethod
    def idempotency(key: str) -> str:
        return f"idempotency:{key}"

    @staticmethod
    def idempotency_result(key: str) -> str:
        return f"idempotency:{key}:result"

    @staticmethod
    def notifications(user_id: UUID) -> str:
        return f"user:{user_id}:notifications"

    @staticmethod
    def notification_channel(user_id: UUID) -> str:
        return f"user:{user_id}:notifications:live"
