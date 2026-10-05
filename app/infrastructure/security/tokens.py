from uuid import UUID

from app.core.exceptions import FeatureNotImplementedError


class TokenService:
    def create_access_token(self, user_id: UUID) -> str:
        # TODO(TP): Definir esquema, claims, firma y expiración.
        raise FeatureNotImplementedError("TokenService.create_access_token")

