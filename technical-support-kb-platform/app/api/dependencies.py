"""Authentication dependencies shared by protected API routes."""

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pymongo.database import Database

from app.core.config import SecuritySettings
from app.db.dependencies import database_dependency
from app.models.user import User
from app.services.auth import ALGORITHM
from app.services.users import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def security_settings_dependency() -> SecuritySettings:
    return SecuritySettings.from_env()


def invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user_dependency(
    token: str = Depends(oauth2_scheme),
    database: Database = Depends(database_dependency),
    settings: SecuritySettings = Depends(security_settings_dependency),
) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError as exc:
        raise invalid_credentials() from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not ObjectId.is_valid(subject):
        raise invalid_credentials()
    user = get_user_by_id(database, ObjectId(subject))
    if user is None:
        raise invalid_credentials()
    return user


def catalog_admin_dependency(
    current_user: User = Depends(current_user_dependency),
) -> User:
    """Allow catalog writes only for an explicitly provisioned administrator."""
    if current_user.role != "catalog_admin":
        raise HTTPException(status_code=403, detail="Catalog administrator required")
    return current_user
