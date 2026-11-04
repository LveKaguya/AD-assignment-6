"""Exercise the complete API workflow in a dedicated MongoDB test database."""

from collections.abc import Iterator
from dataclasses import dataclass, field
import secrets
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.database import Database
import pytest

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.db.dependencies import database_dependency
from app.db.initialize import initialize_database
from app.main import app
from scripts.grant_catalog_admin import grant_catalog_admin


@dataclass
class WorkflowContext:
    client: TestClient
    database: Database
    user_ids: list[ObjectId] = field(default_factory=list)
    item_ids: list[ObjectId] = field(default_factory=list)
    interaction_ids: list[ObjectId] = field(default_factory=list)


@pytest.fixture
def workflow(monkeypatch: pytest.MonkeyPatch) -> Iterator[WorkflowContext]:
    development = MongoSettings.from_env()
    isolated = MongoSettings(development.uri, f"{development.database}_e2e_test")
    assert isolated.database != development.database
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))

    mongo_client = create_client(isolated)
    database = get_database(mongo_client, isolated)
    initialize_database(database)

    def test_database() -> Iterator[Database]:
        yield database

    app.dependency_overrides[database_dependency] = test_database
    context: WorkflowContext | None = None
    try:
        with TestClient(app) as client:
            context = WorkflowContext(client=client, database=database)
            yield context
    finally:
        app.dependency_overrides.pop(database_dependency, None)
        if context is not None:
            if context.interaction_ids:
                database.interactions.delete_many(
                    {"_id": {"$in": context.interaction_ids}}
                )
            if context.item_ids:
                database.kb_items.delete_many({"_id": {"$in": context.item_ids}})
            if context.user_ids:
                database.users.delete_many({"_id": {"$in": context.user_ids}})
        mongo_client.close()


def test_complete_support_workflow(workflow: WorkflowContext) -> None:
    api = workflow.client
    suffix = uuid4().hex
    engineer_email = f"workflow-engineer-{suffix}@example.invalid"
    admin_email = f"workflow-admin-{suffix}@example.invalid"
    password = "WorkflowPass1234!"

    engineer = api.post("/auth/register", json={
        "email": engineer_email, "name": "Workflow Engineer", "password": password,
    })
    assert engineer.status_code == 201
    workflow.user_ids.append(ObjectId(engineer.json()["id"]))
    assert engineer.json()["role"] == "support_engineer"

    login = api.post("/auth/login", data={
        "username": engineer_email, "password": password,
    })
    assert login.status_code == 200
    engineer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = api.get("/users/me", headers=engineer_headers)
    assert profile.status_code == 200
    assert profile.json()["id"] == engineer.json()["id"]
    assert api.get("/health").status_code == 200

    administrator = api.post("/auth/register", json={
        "email": admin_email, "name": "Workflow Administrator", "password": password,
    })
    assert administrator.status_code == 201
    workflow.user_ids.append(ObjectId(administrator.json()["id"]))
    assert grant_catalog_admin(workflow.database, admin_email, admin_email).role == "catalog_admin"
    admin_login = api.post("/auth/login", data={
        "username": admin_email, "password": password,
    })
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    item_payload = {
        "title": f"PostgreSQL SCRAM authentication failure {suffix[:8]}",
        "description": "A PostgreSQL client receives a SCRAM authentication error.",
        "content": "Check pg_hba.conf for the selected authentication method, inspect "
                   "the stored password verifier, then retry the connection with psql.",
        "category": "Database Systems",
        "document_type": "troubleshooting guide",
        "product": "PostgreSQL",
        "version": "16",
        "tags": ["SCRAM", "authentication"],
        "source": {
            "source_type": "synthetic integration test",
            "source_uri": "https://docs.example.invalid/workflow/scram",
        },
    }
    denied = api.post("/items", headers=engineer_headers, json=item_payload)
    assert denied.status_code == 403
    created = api.post("/items", headers=admin_headers, json=item_payload)
    assert created.status_code == 201
    item_id = created.json()["id"]
    workflow.item_ids.append(ObjectId(item_id))

    browse = api.get("/items", headers=engineer_headers,
                     params={"category": "Database Systems", "product": "PostgreSQL"})
    assert browse.status_code == 200
    assert item_id in [item["id"] for item in browse.json()["items"]]
    search = api.get("/items/search", headers=engineer_headers,
                     params={"q": "SCRAM authentication"})
    assert search.status_code == 200
    assert item_id in [item["id"] for item in search.json()["items"]]
    assert api.get(f"/items/{item_id}", headers=engineer_headers).status_code == 200

    viewed = api.post("/interactions", headers=engineer_headers, json={
        "item_id": item_id, "event_type": "view",
    })
    assert viewed.status_code == 201
    interaction_id = viewed.json()["id"]
    workflow.interaction_ids.append(ObjectId(interaction_id))
    assert viewed.json()["user_id"] == engineer.json()["id"]

    own_history = api.get("/users/me/history", headers=engineer_headers)
    other_history = api.get("/users/me/history", headers=admin_headers)
    assert own_history.status_code == other_history.status_code == 200
    assert [event["id"] for event in own_history.json()["interactions"]] == [interaction_id]
    assert other_history.json()["total"] == 0
    assert other_history.json()["interactions"] == []

    denied_update = api.patch(f"/items/{item_id}", headers=engineer_headers,
                              json={"version": "16.1"})
    assert denied_update.status_code == 403
    updated = api.patch(f"/items/{item_id}", headers=admin_headers,
                        json={"version": "16.1"})
    assert updated.status_code == 200
    assert updated.json()["version"] == "16.1"
    assert api.delete(f"/items/{item_id}", headers=engineer_headers).status_code == 403
    assert api.delete(f"/items/{item_id}", headers=admin_headers).status_code == 204
    assert api.get(f"/items/{item_id}", headers=engineer_headers).status_code == 404

    after_deletion = api.get("/items/search", headers=engineer_headers,
                             params={"q": "SCRAM authentication"})
    assert after_deletion.status_code == 200
    assert item_id not in [item["id"] for item in after_deletion.json()["items"]]
    history_after_deletion = api.get("/users/me/history", headers=engineer_headers)
    assert history_after_deletion.json()["interactions"][0]["item_id"] == item_id
    assert workflow.database.kb_items.find_one({"_id": ObjectId(item_id)})["deleted_at"]
    assert workflow.database.interactions.find_one({"_id": ObjectId(interaction_id)})
