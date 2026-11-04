"""Append interaction events and read a user's history."""

from bson import ObjectId
from pymongo import DESCENDING
from pymongo.database import Database

from app.models.common import utc_now
from app.models.interaction import EventType, Interaction


def create_interaction(
    database: Database,
    *,
    user_id: ObjectId,
    item_id: ObjectId,
    event_type: EventType,
    rating: int | None,
) -> Interaction:
    """Insert one new event without changing any existing event."""
    interaction = Interaction(
        user_id=user_id,
        item_id=item_id,
        event_type=event_type,
        rating=rating,
        timestamp=utc_now(),
    )
    database.interactions.insert_one(interaction.to_bson())
    saved = database.interactions.find_one({"_id": interaction.id})
    if saved is None:
        raise RuntimeError("Newly created interaction could not be read")
    return Interaction.model_validate(saved)


def get_user_history(
    database: Database,
    *,
    user_id: ObjectId,
    skip: int,
    limit: int,
    event_type: EventType | None,
) -> tuple[list[Interaction], int]:
    query: dict[str, object] = {"user_id": user_id}
    if event_type is not None:
        query["event_type"] = event_type
    total = database.interactions.count_documents(query)
    documents = database.interactions.find(query).sort(
        [("timestamp", DESCENDING), ("_id", DESCENDING)]
    ).skip(skip).limit(limit)
    return [Interaction.model_validate(document) for document in documents], total
