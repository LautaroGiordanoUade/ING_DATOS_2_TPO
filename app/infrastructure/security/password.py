from app.core.exceptions import FeatureNotImplementedError


class PasswordHasher:
    def hash(self, password: str) -> str:
        # TODO(TP): Elegir biblioteca/parámetros de hash y política de contraseñas.
        raise FeatureNotImplementedError("PasswordHasher.hash")

    def verify(self, password: str, password_hash: str) -> bool:
        # TODO(TP): Verificar hash sin filtrar información sensible.
        raise FeatureNotImplementedError("PasswordHasher.verify")

