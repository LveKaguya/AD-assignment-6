"""Authenticated event creation endpoint."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.api.dependencies import current_user_dependency
from app.db.dependencies import database_dependency
from app.models.user import User
from app.schemas.interactions import InteractionCreate, InteractionResponse
from app.services.interactions import create_interaction
from app.services.items import get_item

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("", response_model=InteractionResponse, status_code=status.HTTP_201_CREATED)
def post_interaction(
    request: InteractionCreate,
    current_user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> InteractionResponse:
    if not ObjectId.is_valid(request.item_id):
        raise HTTPException(status_code=400, detail="Malformed item identifier")
    item_id = ObjectId(request.item_id)
    if get_item(database, item_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    interaction = create_interaction(
        database,
        user_id=current_user.id,
        item_id=item_id,
        event_type=request.event_type,
        rating=request.rating,
    )
    return InteractionResponse.from_interaction(interaction)
