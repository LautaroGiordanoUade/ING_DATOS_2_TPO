import base64
import hashlib
import hmac
from uuid import UUID

from pydantic import ValidationError

from app.application.services.comment_queries import CommentPosition
from app.core.config import get_settings
from app.core.exceptions import InvalidOperationError


class CommentCursorCodec:
    """Signed keyset bound to a post; independent from authentication and feed cursors."""

    @staticmethod
    def _signature(body: str) -> str:
        return hmac.new(
            get_settings().auth_secret.get_secret_value().encode(),
            ("comments-v1:" + body).encode(),
            hashlib.sha256,
        ).hexdigest()

    def encode(self, position: CommentPosition) -> str:
        body = base64.urlsafe_b64encode(position.model_dump_json().encode()).decode().rstrip("=")
        return body + "." + self._signature(body)

    def decode(self, token: str, post_id: UUID) -> CommentPosition:
        try:
            if len(token) > 2048:
                raise ValueError("Too long")
            body, signature = token.split(".")
            if not hmac.compare_digest(signature, self._signature(body)):
                raise ValueError("Signature")
            position = CommentPosition.model_validate_json(
                base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
            )
            if position.post_id != post_id:
                raise ValueError("Post")
            return position
        except (ValueError, TypeError, ValidationError) as exc:
            raise InvalidOperationError(
                "Cursor de comentarios inválido para esta publicación"
            ) from exc
