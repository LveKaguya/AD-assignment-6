"""Authenticated catalog reads and administrator-only writes."""

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.database import Database

from app.api.dependencies import catalog_admin_dependency, current_user_dependency
from app.db.dependencies import database_dependency
from app.models.user import User
from app.schemas.items import (
    Category, DocumentType, ItemCreate, ItemPage, ItemResponse, ItemUpdate,
    SearchHit, SearchPage,
)
from app.services.items import (
    create_item, get_item, list_items, search_items, soft_delete_item, update_item,
)

router = APIRouter(prefix="/items", tags=["items"])


def item_object_id(item_id: str) -> ObjectId:
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Malformed item identifier")
    return ObjectId(item_id)


def missing_item() -> HTTPException:
    return HTTPException(status_code=404, detail="Knowledge item not found")


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def post_item(
    request: ItemCreate,
    _admin: User = Depends(catalog_admin_dependency),
    database: Database = Depends(database_dependency),
) -> ItemResponse:
    return ItemResponse.from_item(create_item(database, request))


@router.get("", response_model=ItemPage)
def get_items(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    category: Category | None = None,
    product: str | None = None,
    document_type: DocumentType | None = None,
    _user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> ItemPage:
    items, total = list_items(
        database,
        skip=skip,
        limit=limit,
        category=category,
        product=product,
        document_type=document_type,
    )
    return ItemPage(
        items=[ItemResponse.from_item(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/search", response_model=SearchPage)
def get_search_results(
    q: str | None = Query(default=None, max_length=200),
    category: Category | None = None,
    product: str | None = Query(default=None, max_length=100),
    document_type: DocumentType | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> SearchPage:
    """Search active catalog items with text relevance and metadata filters."""
    query_text = q.strip() if q is not None else None
    if q is not None and (not query_text or not any(char.isalnum() for char in query_text)):
        raise HTTPException(status_code=422, detail="q must contain a search term")
    filtered_product = product.strip() if product is not None else None
    if product is not None and not filtered_product:
        raise HTTPException(status_code=422, detail="product must not be blank")
    matches, total = search_items(
        database,
        query_text=query_text,
        skip=skip,
        limit=limit,
        category=category,
        product=filtered_product,
        document_type=document_type,
    )
    return SearchPage(
        items=[SearchHit.from_item_and_score(item, score) for item, score in matches],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{item_id}", response_model=ItemResponse)
def get_item_by_id(
    item_id: str,
    _user: User = Depends(current_user_dependency),
    database: Database = Depends(database_dependency),
) -> ItemResponse:
    item = get_item(database, item_object_id(item_id))
    if item is None:
        raise missing_item()
    return ItemResponse.from_item(item)


@router.patch("/{item_id}", response_model=ItemResponse)
def patch_item(
    item_id: str,
    request: ItemUpdate,
    _admin: User = Depends(catalog_admin_dependency),
    database: Database = Depends(database_dependency),
) -> ItemResponse:
    item = update_item(database, item_object_id(item_id), request)
    if item is None:
        raise missing_item()
    return ItemResponse.from_item(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    _admin: User = Depends(catalog_admin_dependency),
    database: Database = Depends(database_dependency),
) -> Response:
    if not soft_delete_item(database, item_object_id(item_id)):
        raise missing_item()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
