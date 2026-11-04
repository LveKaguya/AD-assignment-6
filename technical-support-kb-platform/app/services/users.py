"""Database operations for account and profile data."""

from bson import ObjectId
from pydantic import ValidationError
from pymongo.database import Database

from app.models.user import User
from app.schemas.auth import ProfileUpdate, RegisterRequest
from app.services.auth import hash_password


def create_user(database: Database, request: RegisterRequest) -> User:
    user = User(
        email=request.email,
        name=request.name,
        password_hash=hash_password(request.password),
        role="support_engineer",
    )
    database.users.insert_one(user.to_bson())
    saved_user = get_user_by_id(database, user.id)
    if saved_user is None:
        raise RuntimeError("Newly registered user could not be read")
    return saved_user


def get_user_by_email(database: Database, email: str) -> User | None:
    document = database.users.find_one({"email": email})
    if document is None:
        return None
    try:
        return User.model_validate(document)
    except ValidationError:
        return None


def get_user_by_id(database: Database, user_id: ObjectId) -> User | None:
    document = database.users.find_one({"_id": user_id})
    if document is None:
        return None
    try:
        return User.model_validate(document)
    except ValidationError:
        return None


def update_user_profile(database: Database, user: User, request: ProfileUpdate) -> User | None:
    changes = request.model_dump(exclude_unset=True)
    result = database.users.update_one({"_id": user.id}, {"$set": changes})
    if result.matched_count == 0:
        return None
    return get_user_by_id(database, user.id)
