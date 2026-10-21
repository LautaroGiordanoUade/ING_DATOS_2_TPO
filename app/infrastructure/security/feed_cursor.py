import base64
import hashlib
import hmac
import time
from uuid import UUID

from pydantic import ValidationError

from app.application.services.feed_page import FeedExpiredError, FeedPosition
from app.core.config import get_settings
from app.core.exceptions import InvalidOperationError


class FeedCursorCodec:
    """Domain-separated HMAC cursor; never accepted as a login credential."""

    def encode(self, position: FeedPosition) -> str:
        body = base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        return f"{body}.{self._signature(body)}"

    @staticmethod
    def _signature(body: str) -> str:
        return hmac.new(
            get_settings().auth_secret.get_secret_value().encode(),
            ("feed-v1:" + body).encode(),
            hashlib.sha256,
        ).hexdigest()

    def decode(self, token: str, user_id: UUID) -> FeedPosition:
        try:
            if len(token) > 2048:
                raise ValueError("Too long")
            body, signature = token.split(".")
            if not hmac.compare_digest(signature, self._signature(body)):
                raise ValueError("Signature")
            position = FeedPosition.model_validate_json(
                base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
            )
            if position.user_id != user_id:
                raise ValueError("Owner")
        except (ValueError, TypeError, ValidationError) as exc:
            raise InvalidOperationError("Cursor de feed invalido para este usuario") from exc
        if position.expires <= time.time():
            raise FeedExpiredError("El cursor vencio; refresque el feed")
        return position
