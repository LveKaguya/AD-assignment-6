"""Authenticated user profile routes."""

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.api.dependencies import current_user_dependency, invalid_credentials
from app.db.dependencies import database_dependency
from app.models.user import User
from app.schemas.auth import ProfileUpdate, PublicUser
from app.models.interaction import EventType
from app.schemas.interactions import HistoryPage, InteractionResponse
from app.services.interactions import get_user_history
from app.services.users import update_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=PublicUser)
def get_me(current_user: User = Depends(current_user_dependency)) -> PublicUser:
    return PublicUser.from_user(current_user)


@router.patch("/me", response_model=PublicUser)
def patch_me(
    request: ProfileUpdate,
    current_user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> PublicUser:
    updated_user = update_user_profile(database, current_user, request)
    if updated_user is None:
        raise invalid_credentials()
    return PublicUser.from_user(updated_user)


@router.get("/me/history", response_model=HistoryPage)
def get_my_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    event_type: EventType | None = None,
    current_user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> HistoryPage:
    interactions, total = get_user_history(
        database,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        event_type=event_type,
    )
    return HistoryPage(
        interactions=[InteractionResponse.from_interaction(event) for event in interactions],
        total=total,
        skip=skip,
        limit=limit,
    )
