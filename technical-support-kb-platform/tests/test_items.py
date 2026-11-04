"""Catalog CRUD and role checks using an isolated MongoDB test database."""

from collections.abc import Iterator
from dataclasses import dataclass, field
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
from scripts.grant_catalog_admin import grant_catalog_admin


@dataclass
class CatalogContext:
    client: TestClient
    database: Database
    engineer: User
    admin: User
    engineer_token: str
    admin_token: str
    product: str
    user_ids: list[ObjectId] = field(default_factory=list)
    item_ids: list[ObjectId] = field(default_factory=list)
    interaction_ids: list[ObjectId] = field(default_factory=list)

    def headers(self, *, admin: bool = False) -> dict[str, str]:
        token = self.admin_token if admin else self.engineer_token
        return {"Authorization": f"Bearer {token}"}

    def payload(self, **changes: object) -> dict[str, object]:
        document: dict[str, object] = {
            "title": "Resolve database connection timeout",
            "description": "A client times out while opening a database connection.",
            "content": "Inspect network reachability, connection pool usage, and server logs. "
            "Correct the failing route or pool setting, then retry the request.",
            "category": "Database Systems",
            "document_type": "troubleshooting guide",
            "product": self.product,
            "version": "2.0",
            "tags": ["database", "timeout"],
            "source": {
                "source_type": "internal guide",
                "source_uri": "https://docs.example.invalid/catalog/connection-timeout",
                "section": "Connections",
            },
        }
        document.update(changes)
        return document

    def create(self, **changes: object):
        response = self.client.post(
            "/items", headers=self.headers(admin=True), json=self.payload(**changes)
        )
        if response.status_code == 201:
            self.item_ids.append(ObjectId(response.json()["id"]))
        return response


@pytest.fixture
def catalog_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[CatalogContext]:
    production = MongoSettings.from_env()
    settings = MongoSettings(production.uri, f"{production.database}_catalog_test")
    assert settings.database != production.database
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "30")

    mongo_client = create_client(settings)
    database = get_database(mongo_client, settings)
    initialize_database(database)
    suffix = uuid4().hex
    engineer = User(
        email=f"engineer-{suffix}@example.invalid",
        name="Test Engineer",
        password_hash=hash_password("EngineerPass1234"),
        role="support_engineer",
    )
    admin = User(
        email=f"admin-{suffix}@example.invalid",
        name="Test Catalog Administrator",
        password_hash=hash_password("AdminPass1234"),
        role="catalog_admin",
    )
    database.users.insert_many([engineer.to_bson(), admin.to_bson()])

    def isolated_database() -> Iterator[Database]:
        yield database

    app.dependency_overrides[database_dependency] = isolated_database
    context: CatalogContext | None = None
    try:
        with TestClient(app) as client:
            security = SecuritySettings.from_env()
            context = CatalogContext(
                client=client,
                database=database,
                engineer=engineer,
                admin=admin,
                engineer_token=create_access_token(engineer, security),
                admin_token=create_access_token(admin, security),
                product=f"TestProduct-{suffix}",
                user_ids=[engineer.id, admin.id],
            )
            yield context
    finally:
        app.dependency_overrides.pop(database_dependency, None)
        if context is not None:
            database.interactions.delete_many({"_id": {"$in": context.interaction_ids}})
            database.kb_items.delete_many({"_id": {"$in": context.item_ids}})
            database.users.delete_many({"_id": {"$in": context.user_ids}})
        mongo_client.close()


def test_administrator_can_create_item(catalog_context: CatalogContext) -> None:
    response = catalog_context.create()
    assert response.status_code == 201
    body = response.json()
    assert ObjectId.is_valid(body["id"])
    assert body["title"] == "Resolve database connection timeout"
    assert body["source"]["section"] == "Connections"
    assert body["deleted_at"] is None
    assert catalog_context.database.kb_items.count_documents({"_id": ObjectId(body["id"])}) == 1


def test_support_engineer_cannot_create_item(catalog_context: CatalogContext) -> None:
    response = catalog_context.client.post(
        "/items", headers=catalog_context.headers(), json=catalog_context.payload()
    )
    assert response.status_code == 403
    assert catalog_context.database.kb_items.count_documents({"product": catalog_context.product}) == 0


@pytest.mark.parametrize("changes", [
    {"title": "x"},
    {"description": "too short"},
    {"category": "Unknown Category"},
    {"document_type": "memo"},
    {"source": {
        "source_type": "manual",
        "source_uri": "https://docs.example.invalid/example",
        "unexpected": "forbidden",
    }},
])
def test_create_rejects_invalid_metadata(
    catalog_context: CatalogContext, changes: dict[str, object]
) -> None:
    response = catalog_context.client.post(
        "/items", headers=catalog_context.headers(admin=True),
        json=catalog_context.payload(**changes),
    )
    assert response.status_code == 422
    assert catalog_context.database.kb_items.count_documents({"product": catalog_context.product}) == 0


def test_create_rejects_lifecycle_and_unknown_fields(catalog_context: CatalogContext) -> None:
    for protected in ("_id", "id", "created_at", "updated_at", "deleted_at", "role"):
        response = catalog_context.client.post(
            "/items", headers=catalog_context.headers(admin=True),
            json=catalog_context.payload(**{protected: "forbidden"}),
        )
        assert response.status_code == 422
    assert catalog_context.database.kb_items.count_documents({"product": catalog_context.product}) == 0


def test_list_and_read_existing_item(catalog_context: CatalogContext) -> None:
    created = catalog_context.create()
    item_id = created.json()["id"]
    listing = catalog_context.client.get(
        "/items", headers=catalog_context.headers(), params={"product": catalog_context.product}
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == item_id
    retrieved = catalog_context.client.get(f"/items/{item_id}", headers=catalog_context.headers())
    assert retrieved.status_code == 200
    assert retrieved.json() == created.json()


def test_pagination_filtering_and_stable_order(catalog_context: CatalogContext) -> None:
    for index in range(3):
        assert catalog_context.create(title=f"Connection guide number {index}").status_code == 201
    params = {
        "product": catalog_context.product,
        "category": "Database Systems",
        "document_type": "troubleshooting guide",
        "limit": 2,
    }
    first = catalog_context.client.get("/items", headers=catalog_context.headers(), params=params)
    second = catalog_context.client.get(
        "/items", headers=catalog_context.headers(), params={**params, "skip": 2}
    )
    repeat = catalog_context.client.get("/items", headers=catalog_context.headers(), params=params)
    assert first.status_code == second.status_code == 200
    assert first.json() == repeat.json()
    assert first.json()["total"] == 3
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 1
    assert {item["id"] for item in first.json()["items"]}.isdisjoint(
        {item["id"] for item in second.json()["items"]}
    )
    assert catalog_context.client.get(
        "/items", headers=catalog_context.headers(), params={"limit": 101}
    ).status_code == 422
    assert catalog_context.client.get(
        "/items", headers=catalog_context.headers(), params={"skip": -1}
    ).status_code == 422


def test_invalid_and_missing_item_ids(catalog_context: CatalogContext) -> None:
    assert catalog_context.client.get(
        "/items/not-an-object-id", headers=catalog_context.headers()
    ).status_code == 400
    assert catalog_context.client.get(
        f"/items/{ObjectId()}", headers=catalog_context.headers()
    ).status_code == 404


def test_admin_can_partially_update_item(catalog_context: CatalogContext) -> None:
    created = catalog_context.create()
    item_id = created.json()["id"]
    response = catalog_context.client.patch(
        f"/items/{item_id}",
        headers=catalog_context.headers(admin=True),
        json={"title": "Updated database connection guide", "version": None},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated database connection guide"
    assert response.json()["version"] is None
    assert response.json()["created_at"] == created.json()["created_at"]
    assert response.json()["updated_at"] >= created.json()["updated_at"]


def test_support_engineer_cannot_update_or_delete(catalog_context: CatalogContext) -> None:
    item_id = catalog_context.create().json()["id"]
    assert catalog_context.client.patch(
        f"/items/{item_id}", headers=catalog_context.headers(), json={"title": "Changed title"}
    ).status_code == 403
    assert catalog_context.client.delete(
        f"/items/{item_id}", headers=catalog_context.headers()
    ).status_code == 403
    assert catalog_context.database.kb_items.find_one({"_id": ObjectId(item_id)})["deleted_at"] is None


@pytest.mark.parametrize("protected", ["_id", "id", "created_at", "updated_at", "deleted_at"])
def test_patch_rejects_protected_fields(
    catalog_context: CatalogContext, protected: str
) -> None:
    item_id = catalog_context.create().json()["id"]
    before = catalog_context.database.kb_items.find_one({"_id": ObjectId(item_id)})
    response = catalog_context.client.patch(
        f"/items/{item_id}",
        headers=catalog_context.headers(admin=True),
        json={"title": "Changed title", protected: "forbidden"},
    )
    assert response.status_code == 422
    assert catalog_context.database.kb_items.find_one({"_id": ObjectId(item_id)}) == before


def test_soft_delete_hides_item_and_preserves_interaction(catalog_context: CatalogContext) -> None:
    item_id = ObjectId(catalog_context.create().json()["id"])
    interaction = Interaction(
        user_id=catalog_context.engineer.id,
        item_id=item_id,
        event_type="view",
    )
    catalog_context.database.interactions.insert_one(interaction.to_bson())
    catalog_context.interaction_ids.append(interaction.id)

    response = catalog_context.client.delete(
        f"/items/{item_id}", headers=catalog_context.headers(admin=True)
    )
    assert response.status_code == 204
    saved = catalog_context.database.kb_items.find_one({"_id": item_id})
    assert saved is not None and saved["deleted_at"] is not None
    assert catalog_context.database.interactions.find_one({"_id": interaction.id})["item_id"] == item_id
    assert catalog_context.client.get(
        f"/items/{item_id}", headers=catalog_context.headers()
    ).status_code == 404
    listing = catalog_context.client.get(
        "/items", headers=catalog_context.headers(), params={"product": catalog_context.product}
    )
    assert listing.json()["total"] == 0
    assert catalog_context.client.delete(
        f"/items/{item_id}", headers=catalog_context.headers(admin=True)
    ).status_code == 404


def test_existing_item_without_deleted_at_remains_visible(catalog_context: CatalogContext) -> None:
    item = KnowledgeBaseItem(
        title="Legacy item remains available",
        description="An existing resource written before soft deletion was added.",
        content="Check the legacy configuration and compare it with the current server state.",
        category="Networking",
        document_type="FAQ",
        product=catalog_context.product,
        source=SourceMetadata(source_type="manual", source_uri="https://docs.example.invalid/legacy"),
    )
    document = item.to_bson()
    document.pop("deleted_at")
    catalog_context.database.kb_items.insert_one(document)
    catalog_context.item_ids.append(item.id)
    response = catalog_context.client.get(f"/items/{item.id}", headers=catalog_context.headers())
    assert response.status_code == 200
    assert response.json()["deleted_at"] is None


def test_unauthenticated_item_requests_are_rejected(catalog_context: CatalogContext) -> None:
    item_id = str(ObjectId())
    requests = [
        catalog_context.client.post("/items", json=catalog_context.payload()),
        catalog_context.client.get("/items"),
        catalog_context.client.get(f"/items/{item_id}"),
        catalog_context.client.patch(f"/items/{item_id}", json={"title": "Changed title"}),
        catalog_context.client.delete(f"/items/{item_id}"),
    ]
    assert all(response.status_code == 401 for response in requests)


def test_explicit_grant_requires_matching_confirmation(catalog_context: CatalogContext) -> None:
    with pytest.raises(ValueError, match="Confirmation must exactly match"):
        grant_catalog_admin(catalog_context.database, catalog_context.engineer.email, "wrong")
    assert catalog_context.database.users.find_one({"_id": catalog_context.engineer.id})["role"] == "support_engineer"

    promoted = grant_catalog_admin(
        catalog_context.database,
        catalog_context.engineer.email,
        catalog_context.engineer.email,
    )
    assert promoted.role == "catalog_admin"
    # JWT identifies the user; authorization reads the current stored role.
    response = catalog_context.client.post(
        "/items", headers=catalog_context.headers(), json=catalog_context.payload()
    )
    assert response.status_code == 201
    catalog_context.item_ids.append(ObjectId(response.json()["id"]))
