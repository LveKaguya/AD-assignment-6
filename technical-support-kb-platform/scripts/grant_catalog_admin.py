"""Explicitly promote one registered user: python -m scripts.grant_catalog_admin."""

import argparse

from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.models.user import User, normalize_email_address
from app.services.users import get_user_by_email, get_user_by_id


def grant_catalog_admin(database: Database, email: str, confirmation: str) -> User:
    """Change only the confirmed, active account's role."""
    target_email = normalize_email_address(email)
    if confirmation != target_email:
        raise ValueError("Confirmation must exactly match the normalized target email")
    user = get_user_by_email(database, target_email)
    if user is None:
        raise ValueError("Target user does not exist")
    if user.password_hash.startswith("disabled:"):
        raise ValueError("Disabled synthetic accounts cannot be catalog administrators")
    if user.role == "catalog_admin":
        return user
    if user.role != "support_engineer":
        raise ValueError("Only support_engineer accounts can be promoted")
    result = database.users.update_one(
        {"_id": user.id, "role": "support_engineer"},
        {"$set": {"role": "catalog_admin"}},
    )
    if result.matched_count != 1:
        raise ValueError("Target role changed before promotion; retry after checking the user")
    updated = get_user_by_id(database, user.id)
    if updated is None:
        raise RuntimeError("Promoted user could not be read")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant catalog administrator permissions")
    parser.add_argument("--email", required=True, help="Email of an existing registered user")
    args = parser.parse_args()
    target_email = normalize_email_address(args.email)
    settings = MongoSettings.from_env()
    print(f"Database: {settings.database}")
    print(f"Target user: {target_email}")
    confirmation = input(f"Type {target_email} to confirm promotion: ")

    client = create_client(settings)
    try:
        client.admin.command("ping")
        updated = grant_catalog_admin(get_database(client, settings), target_email, confirmation)
        print(f"Catalog administrator: {updated.email}")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except (PyMongoError, ValueError, EOFError, KeyboardInterrupt) as exc:
        raise SystemExit(f"Administrator grant cancelled: {exc}") from exc
