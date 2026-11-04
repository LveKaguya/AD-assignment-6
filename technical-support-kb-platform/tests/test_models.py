"""Validation and serialization checks for MongoDB documents."""

from bson import ObjectId
from pydantic import ValidationError
import pytest

from app.models.interaction import Interaction
from app.models.kb_item import KnowledgeBaseItem
from app.models.user import User


def test_user_normalizes_email_and_serializes_object_id() -> None:
    user = User(
        email="  ALICE@example.com  ",
        name="Alice",
        password_hash="hashed-value",
        role="user",
    )

    assert user.email == "alice@example.com"
    assert isinstance(user.to_bson()["_id"], ObjectId)
    assert user.model_dump(mode="json", by_alias=True)["_id"] == str(user.id)
    assert User.model_validate(user.to_bson()).id == user.id


@pytest.mark.parametrize("email", ["missing-at-sign", "a@b", " "])
def test_user_rejects_invalid_email(email: str) -> None:
    with pytest.raises(ValidationError):
        User(email=email, name="Alice", password_hash="hash", role="user")


def test_kb_item_validates_embedded_source_metadata() -> None:
    fields = dict(
        title="Guide",
        description="Description",
        content="Content",
        category="Troubleshooting",
        document_type="manual",
        product="Router",
    )
    item = KnowledgeBaseItem(
        **fields,
        source={"source_type": "pdf", "source_uri": "manual.pdf", "page": 2},
    )
    assert item.to_bson()["source"]["page"] == 2

    with pytest.raises(ValidationError):
        KnowledgeBaseItem(
            **fields,
            source={"source_type": "pdf", "source_uri": "manual.pdf", "page": 0},
        )


@pytest.mark.parametrize("rating", [0, 6])
def test_interaction_rejects_out_of_range_rating(rating: int) -> None:
    with pytest.raises(ValidationError):
        Interaction(user_id=ObjectId(), item_id=ObjectId(), event_type="rating", rating=rating)


def test_interaction_validates_references_and_event_type() -> None:
    user_id = ObjectId()
    item_id = ObjectId()
    interaction = Interaction(user_id=str(user_id), item_id=item_id, event_type="view")

    assert interaction.to_bson()["user_id"] == user_id
    assert interaction.model_dump(mode="json")["item_id"] == str(item_id)

    with pytest.raises(ValidationError):
        Interaction(user_id="invalid", item_id=item_id, event_type="view")
    with pytest.raises(ValidationError):
        Interaction(user_id=user_id, item_id=item_id, event_type="unknown")
