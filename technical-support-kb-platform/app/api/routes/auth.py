"""Registration and OAuth2 password-form login."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.api.dependencies import invalid_credentials, security_settings_dependency
from app.core.config import SecuritySettings
from app.db.dependencies import database_dependency
from app.models.user import normalize_email_address
from app.schemas.auth import PublicUser, RegisterRequest, TokenResponse
from app.services.auth import create_access_token, verify_password
from app.services.users import create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    database: Database = Depends(database_dependency),
    _settings: SecuritySettings = Depends(security_settings_dependency),
) -> PublicUser:
    """Create a support engineer account with a hashed password."""
    try:
        user = create_user(database, request)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    return PublicUser.from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    database: Database = Depends(database_dependency),
    settings: SecuritySettings = Depends(security_settings_dependency),
) -> TokenResponse:
    """Accept email in the OAuth2 username field and return a Bearer token."""
    try:
        email = normalize_email_address(form.username)
    except ValueError as exc:
        raise invalid_credentials() from exc
    user = get_user_by_email(database, email)
    if user is None or not verify_password(form.password, user.password_hash):
        raise invalid_credentials()
    return TokenResponse(access_token=create_access_token(user, settings))
