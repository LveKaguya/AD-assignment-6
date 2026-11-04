"""Shared MongoDB identifier and model behavior."""

from datetime import datetime, timezone
from typing import Annotated

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, StringConstraints, WithJsonSchema


def parse_object_id(value: ObjectId | str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    raise ValueError("Expected a valid MongoDB ObjectId")


MongoObjectId = Annotated[
    ObjectId,
    BeforeValidator(parse_object_id),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string"}),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MongoModel(BaseModel):
    """Base model with BSON `_id` and JSON ObjectId serialization."""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    id: MongoObjectId = Field(default_factory=ObjectId, alias="_id")

    def to_bson(self) -> dict[str, object]:
        """Return a document suitable for PyMongo, retaining ObjectIds and dates."""
        return self.model_dump(mode="python", by_alias=True)
