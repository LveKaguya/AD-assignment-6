"""Interaction request, response, and history page schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.models.interaction import EventType, Interaction


class InteractionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    event_type: EventType
    rating: StrictInt | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_rating_for_event(self) -> "InteractionCreate":
        if self.event_type == "rating" and self.rating is None:
            raise ValueError("rating is required for a rating event")
        if self.event_type != "rating" and self.rating is not None:
            raise ValueError("rating is allowed only for a rating event")
        return self


class InteractionResponse(BaseModel):
    id: str
    user_id: str
    item_id: str
    event_type: EventType
    rating: int | None
    timestamp: datetime

    @classmethod
    def from_interaction(cls, interaction: Interaction) -> "InteractionResponse":
        return cls(
            id=str(interaction.id),
            user_id=str(interaction.user_id),
            item_id=str(interaction.item_id),
            event_type=interaction.event_type,
            rating=interaction.rating,
            timestamp=interaction.timestamp,
        )


class HistoryPage(BaseModel):
    interactions: list[InteractionResponse]
    total: int
    skip: int
    limit: int
