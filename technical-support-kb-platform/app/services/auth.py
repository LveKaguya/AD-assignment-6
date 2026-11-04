"""Password verification and signed access tokens."""

from datetime import datetime, timedelta, timezone

import jwt
from argon2.exceptions import InvalidHashError, VerificationError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import SecuritySettings
from app.models.user import User

ALGORITHM = "HS256"
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a validated password with pwdlib's Argon2id hasher."""
    return _password_hash.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Treat disabled or malformed hashes as invalid credentials."""
    if not isinstance(stored_hash, str) or not stored_hash.startswith("$argon2id$"):
        return False
    try:
        return _password_hash.verify(password, stored_hash)
    except (UnknownHashError, InvalidHashError, VerificationError, ValueError, TypeError):
        return False


def create_access_token(user: User, settings: SecuritySettings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
