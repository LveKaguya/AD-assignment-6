"""Settings from the shell, with a project-local .env fallback."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def setting(name: str, default: str) -> str:
    """Give shell variables precedence over the ignored local .env file."""
    shell_value = os.environ.get(name)
    if shell_value is not None:
        return shell_value
    file_value = dotenv_values(_ENV_FILE).get(name)
    return file_value if file_value is not None else default


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    database: str

    @classmethod
    def from_env(cls) -> "MongoSettings":
        uri = setting("MONGODB_URI", "mongodb://localhost:27017").strip()
        database = setting("MONGODB_DATABASE", "tech_support_recommender").strip()
        if not uri or not database:
            raise ValueError("MONGODB_URI and MONGODB_DATABASE must not be empty")
        return cls(uri=uri, database=database)


@dataclass(frozen=True)
class SecuritySettings:
    secret_key: str
    expire_minutes: int

    @classmethod
    def from_env(cls) -> "SecuritySettings":
        secret_key = setting("JWT_SECRET_KEY", "")
        if len(secret_key.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY must be set to at least 32 bytes")
        raw_minutes = setting("JWT_EXPIRE_MINUTES", "30")
        try:
            expire_minutes = int(raw_minutes)
        except ValueError as exc:
            raise ValueError("JWT_EXPIRE_MINUTES must be a positive integer") from exc
        if expire_minutes <= 0:
            raise ValueError("JWT_EXPIRE_MINUTES must be a positive integer")
        return cls(secret_key=secret_key, expire_minutes=expire_minutes)
