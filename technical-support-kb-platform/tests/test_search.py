"""Indexed catalog search tests in a dedicated MongoDB test database."""

from collections.abc import Iterator
from dataclasses import dataclass
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
from app.models.kb_item import KnowledgeBaseItem, SourceMetadata
from app.models.user import User
from app.services.auth import create_access_token, hash_password


@dataclass
class SearchContext:
    client: TestClient
    database: Database
    headers: dict[str, str]
    ids: dict[str, ObjectId]


@pytest.fixture
def search_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[SearchContext]:
    production = MongoSettings.from_env()
    settings = MongoSettings(production.uri, f"{production.database}_search_test")
    assert settings.database != production.database
    monkeypatch.setenv("JWT_SECRET_KEY", secrets.token_urlsafe(48))
    mongo_client = create_client(settings)
    database = get_database(mongo_client, settings)
    initialize_database(database)

    user = User(
        email=f"search-{uuid4().hex}@example.invalid",
        name="Search Test Engineer",
        password_hash=hash_password("SearchTestPass123"),
        role="support_engineer",
    )
    source = SourceMetadata(
        source_type="test guide",
        source_uri="https://docs.example.invalid/search-test",
    )
    baseline = datetime(2025, 1, 1, tzinfo=timezone.utc)
    specs = (
        (
            "auth_high", "PostgreSQL SCRAM authentication failure",
            "SCRAM authentication fails for a database role.",
            "Authentication fails with SCRAM-SHA-256. Check the authentication rule in "
            "pg_hba.conf, reset the password verifier, and retry authentication with psql.",
            "Database Systems", "PostgreSQL", "troubleshooting guide",
            ["authentication", "SCRAM"], None,
        ),
        (
            "auth_low", "PostgreSQL connection pool guide",
            "A database pool becomes exhausted during traffic spikes.",
            "Inspect maxPoolSize and active sessions. One authentication check may also "
            "fail when a stale connection is reused; verify the pool after recovery.",
            "Database Systems", "PostgreSQL", "FAQ", ["pool"], None,
        ),
        (
            "vpn", "WireGuard VPN handshake troubleshooting",
            "A VPN peer never completes its UDP handshake.",
            "Inspect WireGuard peer keys, UDP firewall counters, and AllowedIPs. "
            "Correct the VPN endpoint route and check the latest handshake timestamp.",
            "Networking", "WireGuard", "troubleshooting guide", ["vpn", "handshake"], None,
        ),
        (
            "linux", "Linux file permissions with systemd",
            "A Linux service cannot read a mounted configuration file.",
            "Inspect file permissions, owner, and systemd sandbox options. Use namei "
            "to inspect parent directory permissions before changing the service account.",
            "Operating Systems", "Ubuntu", "configuration manual",
            ["linux", "permissions"], None,
        ),
        (
            "deleted", "Archived PostgreSQL authentication note",
            "An old authentication note has been withdrawn.",
            "This archived SCRAM authentication note is retained only to check "
            "that soft-deleted documents never appear in search results.",
            "Database Systems", "PostgreSQL", "FAQ", ["authentication"], baseline,
        ),
    )
    items = [
        KnowledgeBaseItem(
            title=title,
            description=description,
            content=content,
            category=category,
            document_type=document_type,
            product=product,
            tags=tags,
            source=source,
            created_at=baseline + timedelta(days=index),
            updated_at=baseline + timedelta(days=index),
            deleted_at=deleted_at,
        )
        for index, (_, title, description, content, category, product,
                    document_type, tags, deleted_at) in enumerate(specs)
    ]
    ids = {spec[0]: item.id for spec, item in zip(specs, items)}
    try:
        database.users.insert_one(user.to_bson())
        database.kb_items.insert_many([item.to_bson() for item in items])

        def isolated_database() -> Iterator[Database]:
            yield database

        app.dependency_overrides[database_dependency] = isolated_database
        with TestClient(app) as client:
            token = create_access_token(user, SecuritySettings.from_env())
            yield SearchContext(
                client=client,
                database=database,
                headers={"Authorization": f"Bearer {token}"},
                ids=ids,
            )
    finally:
        app.dependency_overrides.pop(database_dependency, None)
        database.kb_items.delete_many({"_id": {"$in": list(ids.values())}})
        database.users.delete_one({"_id": user.id})
        mongo_client.close()


def test_keyword_search_uses_relevance_ranking(search_context: SearchContext) -> None:
    response = search_context.client.get(
        "/items/search", headers=search_context.headers, params={"q": "authentication"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == str(search_context.ids["auth_high"])
    scores = [item["relevance_score"] for item in body["items"]]
    assert all(isinstance(score, float) and score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)
    assert body == search_context.client.get(
        "/items/search", headers=search_context.headers, params={"q": "authentication"}
    ).json()


def test_technical_term_search(search_context: SearchContext) -> None:
    response = search_context.client.get(
        "/items/search", headers=search_context.headers, params={"q": "SCRAM"}
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        str(search_context.ids["auth_high"])
    ]


def test_category_and_product_filter_only_search(search_context: SearchContext) -> None:
    category = search_context.client.get(
        "/items/search", headers=search_context.headers,
        params={"category": "Operating Systems"},
    )
    assert category.status_code == 200
    assert [item["id"] for item in category.json()["items"]] == [
        str(search_context.ids["linux"])
    ]
    assert category.json()["items"][0]["relevance_score"] is None

    product = search_context.client.get(
        "/items/search", headers=search_context.headers,
        params={"product": "WireGuard"},
    )
    assert product.status_code == 200
    assert [item["id"] for item in product.json()["items"]] == [
        str(search_context.ids["vpn"])
    ]


def test_combined_keyword_and_metadata_filters(search_context: SearchContext) -> None:
    response = search_context.client.get(
        "/items/search", headers=search_context.headers,
        params={
            "q": "authentication",
            "category": "Database Systems",
            "product": "PostgreSQL",
            "document_type": "troubleshooting guide",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(search_context.ids["auth_high"])
    assert response.json()["items"][0]["relevance_score"] > 0


def test_search_pagination_and_filter_only_order(search_context: SearchContext) -> None:
    params = {"category": "Database Systems", "limit": 1}
    first = search_context.client.get(
        "/items/search", headers=search_context.headers, params=params
    )
    second = search_context.client.get(
        "/items/search", headers=search_context.headers, params={**params, "skip": 1}
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 2
    assert first.json()["items"][0]["id"] == str(search_context.ids["auth_low"])
    assert second.json()["items"][0]["id"] == str(search_context.ids["auth_high"])
    assert first.json()["items"][0]["relevance_score"] is None


def test_search_empty_results_and_deleted_exclusion(search_context: SearchContext) -> None:
    empty = search_context.client.get(
        "/items/search", headers=search_context.headers, params={"q": "unobtainiumtoken"}
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["items"] == []
    matches = search_context.client.get(
        "/items/search", headers=search_context.headers, params={"q": "authentication"}
    ).json()["items"]
    assert str(search_context.ids["deleted"]) not in {item["id"] for item in matches}


@pytest.mark.parametrize("params", [
    {"q": "   "}, {"q": "---"}, {"limit": 101}, {"skip": -1},
    {"category": "Unknown"}, {"document_type": "memo"}, {"product": "   "},
])
def test_search_rejects_invalid_parameters(
    search_context: SearchContext, params: dict[str, object]
) -> None:
    response = search_context.client.get(
        "/items/search", headers=search_context.headers, params=params
    )
    assert response.status_code == 422


def test_search_requires_authentication(search_context: SearchContext) -> None:
    assert search_context.client.get("/items/search", params={"q": "SCRAM"}).status_code == 401


def test_existing_catalog_routes_still_work(search_context: SearchContext) -> None:
    listing = search_context.client.get("/items", headers=search_context.headers)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 4
    detail = search_context.client.get(
        f"/items/{search_context.ids['vpn']}", headers=search_context.headers
    )
    assert detail.status_code == 200
    assert detail.json()["title"] == "WireGuard VPN handshake troubleshooting"
