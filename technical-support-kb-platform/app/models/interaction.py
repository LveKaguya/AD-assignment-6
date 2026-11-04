"""Validated user interaction document."""

from datetime import datetime
from typing import Literal

from pydantic import Field, StrictInt, model_validator

from app.models.common import MongoModel, MongoObjectId, utc_now

EventType = Literal["view", "selection", "helpful", "unhelpful", "rating"]


class Interaction(MongoModel):
    user_id: MongoObjectId
    item_id: MongoObjectId
    event_type: EventType
    rating: StrictInt | None = Field(default=None, ge=1, le=5)
    timestamp: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_rating_for_event(self) -> "Interaction":
        if self.event_type == "rating" and self.rating is None:
            raise ValueError("rating is required for a rating event")
        if self.event_type != "rating" and self.rating is not None:
            raise ValueError("rating is allowed only for a rating event")
        return self
