"""Validated user document."""

import re
from datetime import datetime

from pydantic import Field, field_validator

from app.models.common import MongoModel, NonEmptyText, utc_now


def normalize_email_address(value: str) -> str:
    """Use one normalization rule for registration and stored users."""
    email = value.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Invalid email address")
    return email


class User(MongoModel):
    email: NonEmptyText
    name: NonEmptyText
    password_hash: NonEmptyText
    role: NonEmptyText
    preferred_products: list[NonEmptyText] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_address(value)
