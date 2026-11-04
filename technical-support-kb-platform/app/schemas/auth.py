"""Public request and response schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.common import NonEmptyText
from app.models.user import User, normalize_email_address


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    name: NonEmptyText
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email_address(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(character.isalpha() for character in value) or not any(
            character.isdigit() for character in value
        ):
            raise ValueError("Password must contain a letter and a digit")
        return value


class PublicUser(BaseModel):
    id: str
    email: str
    name: str
    role: str
    preferred_products: list[str]
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "PublicUser":
        return cls(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            preferred_products=user.preferred_products,
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyText | None = None
    preferred_products: list[NonEmptyText] | None = None

    @model_validator(mode="after")
    def require_valid_change(self) -> "ProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Profile fields cannot be null")
        return self
