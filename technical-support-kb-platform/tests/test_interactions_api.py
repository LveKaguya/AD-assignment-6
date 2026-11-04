"""Interaction creation and personal history in an isolated database."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.database import Database
import pytest

from app.core.config import MongoSettings, SecuritySettings
from app.db.connection import create_client, get_database
from app.db.dependencies import database_dependency
from app.db.initialize import initialize_database
from app.main import app
from app.models.interaction import Interaction
from app.models.kb_item import KnowledgeBaseItem, SourceMetadata
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@dataclass
class InteractionContext:
    client: TestClient
    database: Database
    user: User
    other_user: User
    active_item: KnowledgeBaseItem
    deleted_item: KnowledgeBaseItem
    user_token: str
    other_token: str
    event_ids: list[ObjectId] = field(default_factory=list)

    def headers(self, *, other: bool = False) -> dict[str, str]:
        token = self.other_token if other else self.user_token
        return {"Authorization": f"Bearer {token}"}

    def post(self, event_type: str, *, item_id: ObjectId | None = None,
             rating: object = None, other: bool = False):
        body: dict[str, object] = {
            "item_id": str(item_id or self.active_item.id),
            "event_type": event_type,
        }
        if rating is not None:
            body["rating"] = rating
        response = self.client.post(
            "/interactions", headers=self.headers(other=other), json=body
        )
        if response.status_code == 201:
            self.event_ids.append(ObjectId(response.json()["id"]))
        return response


@pytest.fixture
def interaction_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[InteractionContext]:
    production = MongoSettings.from_env()
    settings = MongoSettings(production.uri, f"{production.database}_interactions_test")
    assert settings.database != production.database
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    mongo_client = create_client(settings)
    database = get_database(mongo_client, settings)
    suffix = uuid4().hex
    users = [
        User(
            email=f"history-{number}-{suffix}@example.invalid",
            name=f"History Test User {number}",
            password_hash=hash_password("HistoryTestPass123"),
            role="support_engineer",
        )
        for number in (1, 2)
    ]
    source = SourceMetadata(
        source_type="test guide",
        source_uri="https://docs.example.invalid/interaction-test",
    )
    active_item = KnowledgeBaseItem(
        title="Check database connection pool",
        description="A connection pool becomes exhausted under load.",
        content="Inspect active clients and timeout logs, then adjust the pool after measuring usage.",
        category="Database Systems",
        document_type="troubleshooting guide",
        product="TestDB",
        source=source,
    )
    deleted_item = KnowledgeBaseItem(
        title="Withdrawn connection pool note",
        description="An older guide is no longer available in the catalog.",
        content="This withdrawn resource remains in MongoDB to preserve historical references.",
        category="Database Systems",
        document_type="FAQ",
        product="TestDB",
        source=source,
        deleted_at=datetime.now(timezone.utc),
    )
    context: InteractionContext | None = None
    try:
        initialize_database(database)
        database.users.insert_many([user.to_bson() for user in users])
        database.kb_items.insert_many([active_item.to_bson(), deleted_item.to_bson()])

        def isolated_database() -> Iterator[Database]:
            yield database

        app.dependency_overrides[database_dependency] = isolated_database
        with TestClient(app) as client:
            security = SecuritySettings.from_env()
            context = InteractionContext(
                client=client,
                database=database,
                user=users[0],
                other_user=users[1],
                active_item=active_item,
                deleted_item=deleted_item,
                user_token=create_access_token(users[0], security),
                other_token=create_access_token(users[1], security),
            )
            yield context
    finally:
        app.dependency_overrides.pop(database_dependency, None)
        if context is not None:
            database.interactions.delete_many({"_id": {"$in": context.event_ids}})
        database.kb_items.delete_many({"_id": {"$in": [active_item.id, deleted_item.id]}})
        database.users.delete_many({"_id": {"$in": [user.id for user in users]}})
        mongo_client.close()


@pytest.mark.parametrize("event_type", ["view", "selection", "helpful", "unhelpful"])
def test_create_non_rating_events(interaction_context: InteractionContext, event_type: str) -> None:
    response = interaction_context.post(event_type)
    assert response.status_code == 201
    body = response.json()
    assert ObjectId.is_valid(body["id"])
    assert body["user_id"] == str(interaction_context.user.id)
    assert body["item_id"] == str(interaction_context.active_item.id)
    assert body["event_type"] == event_type
    assert body["rating"] is None
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None
    assert interaction_context.database.interactions.count_documents({"_id": ObjectId(body["id"])}) == 1


def test_create_rating_event(interaction_context: InteractionContext) -> None:
    response = interaction_context.post("rating", rating=5)
    assert response.status_code == 201
    assert response.json()["rating"] == 5
    assert response.json()["user_id"] == str(interaction_context.user.id)


@pytest.mark.parametrize("rating", [0, 6, 2.5, True])
def test_invalid_rating_values(interaction_context: InteractionContext, rating: object) -> None:
    assert interaction_context.post("rating", rating=rating).status_code == 422
    assert interaction_context.database.interactions.count_documents({}) == 0


def test_rating_required_only_for_rating_event(interaction_context: InteractionContext) -> None:
    assert interaction_context.post("rating").status_code == 422
    assert interaction_context.post("view", rating=3).status_code == 422
    assert interaction_context.database.interactions.count_documents({}) == 0


def test_unsupported_event_type(interaction_context: InteractionContext) -> None:
    assert interaction_context.post("download").status_code == 422


def test_invalid_missing_and_deleted_item_ids(interaction_context: InteractionContext) -> None:
    invalid = interaction_context.client.post(
        "/interactions", headers=interaction_context.headers(),
        json={"item_id": "not-an-object-id", "event_type": "view"},
    )
    assert invalid.status_code == 400
    assert interaction_context.post("view", item_id=ObjectId()).status_code == 404
    assert interaction_context.post("view", item_id=interaction_context.deleted_item.id).status_code == 404
    assert interaction_context.database.interactions.count_documents({}) == 0


@pytest.mark.parametrize("protected,value", [
    ("user_id", "000000000000000000000001"),
    ("id", "000000000000000000000001"),
    ("_id", "000000000000000000000001"),
    ("timestamp", "2020-01-01T00:00:00Z"),
])
def test_protected_request_fields_are_rejected(
    interaction_context: InteractionContext, protected: str, value: str
) -> None:
    response = interaction_context.client.post(
        "/interactions", headers=interaction_context.headers(),
        json={
            "item_id": str(interaction_context.active_item.id),
            "event_type": "view",
            protected: value,
        },
    )
    assert response.status_code == 422
    assert interaction_context.database.interactions.count_documents({}) == 0


def test_unauthenticated_requests_return_401(interaction_context: InteractionContext) -> None:
    assert interaction_context.client.post(
        "/interactions", json={
            "item_id": str(interaction_context.active_item.id), "event_type": "view"
        },
    ).status_code == 401
    assert interaction_context.client.get("/users/me/history").status_code == 401


def test_history_is_personal_and_empty_for_new_user(interaction_context: InteractionContext) -> None:
    first = interaction_context.post("view")
    second = interaction_context.post("helpful", other=True)
    assert first.status_code == second.status_code == 201
    own = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers()
    )
    other = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers(other=True)
    )
    assert own.status_code == other.status_code == 200
    assert own.json()["total"] == other.json()["total"] == 1
    assert own.json()["interactions"][0]["user_id"] == str(interaction_context.user.id)
    assert other.json()["interactions"][0]["user_id"] == str(interaction_context.other_user.id)
    assert own.json()["interactions"][0]["id"] != other.json()["interactions"][0]["id"]


def test_empty_history_and_event_filter(interaction_context: InteractionContext) -> None:
    empty = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers()
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["interactions"] == []
    interaction_context.post("view")
    interaction_context.post("helpful")
    filtered = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers(),
        params={"event_type": "helpful"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["interactions"][0]["event_type"] == "helpful"
    assert interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers(),
        params={"event_type": "unsupported"},
    ).status_code == 422


def test_history_pagination_and_stable_secondary_order(
    interaction_context: InteractionContext,
) -> None:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = [
        Interaction(user_id=interaction_context.user.id,
                    item_id=interaction_context.active_item.id,
                    event_type="view", timestamp=base),
        Interaction(user_id=interaction_context.user.id,
                    item_id=interaction_context.active_item.id,
                    event_type="selection", timestamp=base + timedelta(minutes=1)),
        Interaction(user_id=interaction_context.user.id,
                    item_id=interaction_context.active_item.id,
                    event_type="helpful", timestamp=base + timedelta(minutes=1)),
    ]
    interaction_context.database.interactions.insert_many([event.to_bson() for event in events])
    interaction_context.event_ids.extend(event.id for event in events)
    expected = [str(event.id) for event in sorted(
        events, key=lambda event: (event.timestamp, event.id), reverse=True
    )]
    first = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers(),
        params={"skip": 0, "limit": 2},
    )
    second = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers(),
        params={"skip": 2, "limit": 2},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 3
    assert [event["id"] for event in first.json()["interactions"]] == expected[:2]
    assert [event["id"] for event in second.json()["interactions"]] == expected[2:]
    for params in ({"skip": -1}, {"limit": 0}, {"limit": 101}):
        assert interaction_context.client.get(
            "/users/me/history", headers=interaction_context.headers(), params=params
        ).status_code == 422


def test_history_preserves_deleted_item_reference(interaction_context: InteractionContext) -> None:
    created = interaction_context.post("view")
    assert created.status_code == 201
    interaction_context.database.kb_items.update_one(
        {"_id": interaction_context.active_item.id},
        {"$set": {"deleted_at": datetime.now(timezone.utc)}},
    )
    assert interaction_context.client.get(
        f"/items/{interaction_context.active_item.id}",
        headers=interaction_context.headers(),
    ).status_code == 404
    history = interaction_context.client.get(
        "/users/me/history", headers=interaction_context.headers()
    )
    assert history.status_code == 200
    assert history.json()["interactions"][0]["item_id"] == str(interaction_context.active_item.id)
    assert interaction_context.database.interactions.count_documents({"_id": ObjectId(created.json()["id"])}) == 1
