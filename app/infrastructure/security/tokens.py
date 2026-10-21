import base64
import hashlib
import hmac
import json
import time
from uuid import UUID

from app.core.config import get_settings


class TokenService:
    """Signed expiring bearer credentials; roles are always loaded from MongoDB."""

    def create_access_token(self, user_id: UUID, auth_version: int = 0) -> str:
        settings = get_settings()
        body = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "sub": str(user_id),
                        "ver": auth_version,
                        "exp": int(time.time()) + settings.access_token_seconds,
                    },
                    separators=(",", ":"),
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(
            settings.auth_secret.get_secret_value().encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        return f"{body}.{signature}"

    def verify_access_token(self, token: str) -> UUID:
        try:
            body, signature = token.split(".")
            expected = hmac.new(
                get_settings().auth_secret.get_secret_value().encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Invalid signature")
            claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if int(claims["exp"]) <= time.time():
                raise ValueError("Expired credential")
            return UUID(claims["sub"])
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ValueError("Invalid or expired credential") from exc

    def token_version(self, token: str) -> int:
        self.verify_access_token(token)
        body = token.split(".")[0]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        version = claims.get("ver", 0)
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise ValueError("Invalid credential version")
        return version
