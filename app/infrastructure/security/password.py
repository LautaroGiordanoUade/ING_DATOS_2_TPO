import hashlib
import hmac
import secrets


class PasswordHasher:
    def hash(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
        return f"pbkdf2_sha256$600000${salt}${digest.hex()}"

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            algorithm, iterations, salt, digest = password_hash.split("$")
            if algorithm != "pbkdf2_sha256" or int(iterations) != 600_000:
                return False
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
            )
            return hmac.compare_digest(candidate.hex(), digest)
        except (ValueError, TypeError):
            return False
