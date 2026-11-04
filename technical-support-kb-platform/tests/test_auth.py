"""Authentication and profile tests isolated in a dedicated test database."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
import jwt
from pymongo.database import Database
import pytest

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.db.dependencies import database_dependency
from app.db.initialize import initialize_database
from app.main import app
from app.models.user import User
from app.services.auth import hash_password, verify_password

PASSWORD = "ExamplePass1234"


@dataclass
class AuthTestContext:
    client: TestClient
    database: Database
    email_prefix: str
    secret: str
    created_ids: list[ObjectId] = field(default_factory=list)

    def register(self, suffix: str = "one"):
        response = self.client.post(
            "/auth/register",
            json={
                "email": f"{self.email_prefix}{suffix}@example.invalid",
                "name": "Test Engineer",
                "password": PASSWORD,
            },
        )
        if response.status_code == 201:
            self.created_ids.append(ObjectId(response.json()["id"]))
        return response


@pytest.fixture
def auth_context(monkeypatch: pytest.MonkeyPatch) -> Iterator[AuthTestContext]:
    production = MongoSettings.from_env()
    settings = MongoSettings(
        uri=production.uri,
        database=f"{production.database}_auth_test",
    )
    assert settings.database != production.database
    secret = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET_KEY", secret)
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "30")

    mongo_client = create_client(settings)
    database = get_database(mongo_client, settings)
    initialize_database(database)

    def test_database_dependency() -> Iterator[Database]:
        yield database

    app.dependency_overrides[database_dependency] = test_database_dependency
    context: AuthTestContext | None = None
    try:
        with TestClient(app) as client:
            context = AuthTestContext(
                client=client,
                database=database,
                email_prefix=f"task04-{uuid4().hex}-",
                secret=secret,
            )
            yield context
    finally:
        app.dependency_overrides.pop(database_dependency, None)
        if context is not None and context.created_ids:
            # Only IDs recorded from this fixture are removed.
            database.users.delete_many({"_id": {"$in": context.created_ids}})
        mongo_client.close()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(context: AuthTestContext, email: str, password: str = PASSWORD):
    return context.client.post(
        "/auth/login", data={"username": email, "password": password}
    )


def test_registration_returns_public_user_and_normalized_email(auth_context: AuthTestContext) -> None:
    response = auth_context.client.post(
        "/auth/register",
        json={
            "email": f"  {auth_context.email_prefix.upper()}ONE@EXAMPLE.INVALID  ",
            "name": "  Test Engineer  ",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    auth_context.created_ids.append(ObjectId(response.json()["id"]))
    body = response.json()
    assert body["email"] == f"{auth_context.email_prefix}one@example.invalid"
    assert body["name"] == "Test Engineer"
    assert body["role"] == "support_engineer"
    assert body["preferred_products"] == []
    assert "password_hash" not in body
    assert "password" not in body


def test_duplicate_registration_returns_409(auth_context: AuthTestContext) -> None:
    first = auth_context.register()
    assert first.status_code == 201
    duplicate = auth_context.client.post(
        "/auth/register",
        json={
            "email": f"{auth_context.email_prefix.upper()}ONE@EXAMPLE.INVALID",
            "name": "Other Name",
            "password": PASSWORD,
        },
    )
    assert duplicate.status_code == 409
    assert auth_context.database.users.count_documents({"email": first.json()["email"]}) == 1


def test_password_hashing_verification_and_malformed_hashes() -> None:
    stored = hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert verify_password(PASSWORD, stored)
    assert not verify_password("WrongPass1234", stored)
    assert not verify_password(PASSWORD, "disabled:sha256:synthetic")
    assert not verify_password(PASSWORD, "$argon2id$malformed")
    assert not verify_password(PASSWORD, None)


@pytest.mark.parametrize("password", ["short1", "abcdefghijklmn", "12345678901234"])
def test_registration_rejects_weak_password(auth_context: AuthTestContext, password: str) -> None:
    response = auth_context.client.post(
        "/auth/register",
        json={"email": f"{auth_context.email_prefix}weak@example.invalid", "name": "Test", "password": password},
    )
    assert response.status_code == 422
    assert auth_context.database.users.count_documents({"email": f"{auth_context.email_prefix}weak@example.invalid"}) == 0


def test_login_returns_signed_bearer_token(auth_context: AuthTestContext) -> None:
    registered = auth_context.register()
    response = login(auth_context, registered.json()["email"].upper())
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], auth_context.secret, algorithms=["HS256"])
    assert claims["sub"] == registered.json()["id"]
    assert "exp" in claims


def test_invalid_credentials_share_one_401_response(auth_context: AuthTestContext) -> None:
    registered = auth_context.register()
    email = registered.json()["email"]
    wrong_password = login(auth_context, email, "WrongPass1234")
    unknown_email = login(auth_context, f"{auth_context.email_prefix}missing@example.invalid")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid credentials"}


def test_disabled_seed_style_account_cannot_log_in(auth_context: AuthTestContext) -> None:
    user = User(
        email=f"{auth_context.email_prefix}disabled@example.invalid",
        name="Disabled Synthetic Engineer",
        password_hash="disabled:sha256:synthetic-no-login",
        role="support_engineer",
    )
    auth_context.database.users.insert_one(user.to_bson())
    auth_context.created_ids.append(user.id)
    response = login(auth_context, user.email)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_malformed_stored_hash_returns_401(auth_context: AuthTestContext) -> None:
    user = User(
        email=f"{auth_context.email_prefix}malformed@example.invalid",
        name="Malformed Hash User",
        password_hash="temporary-valid-model-value",
        role="support_engineer",
    )
    auth_context.database.users.insert_one(user.to_bson())
    auth_context.created_ids.append(user.id)
    auth_context.database.users.update_one({"_id": user.id}, {"$set": {"password_hash": None}})
    response = login(auth_context, user.email)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_missing_token_returns_401(auth_context: AuthTestContext) -> None:
    assert auth_context.client.get("/users/me").status_code == 401


def test_invalid_token_returns_401(auth_context: AuthTestContext) -> None:
    response = auth_context.client.get("/users/me", headers=bearer("not-a-jwt"))
    assert response.status_code == 401


def test_expired_token_returns_401(auth_context: AuthTestContext) -> None:
    registered = auth_context.register()
    expired = jwt.encode(
        {"sub": registered.json()["id"], "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        auth_context.secret,
        algorithm="HS256",
    )
    assert auth_context.client.get("/users/me", headers=bearer(expired)).status_code == 401


def test_profile_get_returns_only_public_fields(auth_context: AuthTestContext) -> None:
    registered = auth_context.register()
    token = login(auth_context, registered.json()["email"]).json()["access_token"]
    response = auth_context.client.get("/users/me", headers=bearer(token))
    assert response.status_code == 200
    assert response.json() == registered.json()
    assert "password_hash" not in response.json()


def test_profile_patch_updates_only_allowed_fields(auth_context: AuthTestContext) -> None:
    registered = auth_context.register()
    token = login(auth_context, registered.json()["email"]).json()["access_token"]
    response = auth_context.client.patch(
        "/users/me",
        headers=bearer(token),
        json={"name": "Updated Engineer", "preferred_products": ["MongoDB", "PostgreSQL"]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Engineer"
    assert response.json()["preferred_products"] == ["MongoDB", "PostgreSQL"]
    assert response.json()["email"] == registered.json()["email"]
    saved = auth_context.database.users.find_one({"_id": ObjectId(registered.json()["id"])})
    assert saved["name"] == "Updated Engineer"
    assert saved["preferred_products"] == ["MongoDB", "PostgreSQL"]
    assert saved["role"] == "support_engineer"


@pytest.mark.parametrize("field,value", [
    ("id", "000000000000000000000001"),
    ("email", "changed@example.invalid"),
    ("role", "admin"),
    ("password_hash", "forged"),
    ("created_at", "2020-01-01T00:00:00Z"),
])
def test_profile_patch_rejects_protected_fields(
    auth_context: AuthTestContext, field: str, value: str
) -> None:
    registered = auth_context.register()
    token = login(auth_context, registered.json()["email"]).json()["access_token"]
    before = auth_context.database.users.find_one({"_id": ObjectId(registered.json()["id"])})
    response = auth_context.client.patch(
        "/users/me", headers=bearer(token), json={"name": "Changed", field: value}
    )
    assert response.status_code == 422
    after = auth_context.database.users.find_one({"_id": before["_id"]})
    assert after == before


def test_missing_security_secret_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be set"):
        with TestClient(app):
            pass


def test_swagger_lists_auth_and_profile_routes(auth_context: AuthTestContext) -> None:
    assert auth_context.client.get("/docs").status_code == 200
    schema = auth_context.client.get("/openapi.json").json()
    assert "post" in schema["paths"]["/auth/register"]
    assert "post" in schema["paths"]["/auth/login"]
    assert {"get", "patch"}.issubset(schema["paths"]["/users/me"])
    scheme = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["flows"]["password"]["tokenUrl"] == "/auth/login"
    assert schema["paths"]["/users/me"]["get"]["security"]
