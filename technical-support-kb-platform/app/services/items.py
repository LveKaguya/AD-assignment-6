"""MongoDB operations for active knowledge resources."""

from bson import ObjectId
from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database

from app.models.common import utc_now
from app.models.kb_item import KnowledgeBaseItem
from app.schemas.items import ItemCreate, ItemUpdate


def active_filter(**fields: object) -> dict[str, object]:
    """Missing deleted_at in older documents also means active."""
    return {"deleted_at": None, **fields}


def create_item(database: Database, request: ItemCreate) -> KnowledgeBaseItem:
    item = KnowledgeBaseItem(**request.model_dump())
    database.kb_items.insert_one(item.to_bson())
    saved_item = get_item(database, item.id)
    if saved_item is None:
        raise RuntimeError("Newly created knowledge item could not be read")
    return saved_item


def list_items(
    database: Database,
    *,
    skip: int,
    limit: int,
    category: str | None,
    product: str | None,
    document_type: str | None,
) -> tuple[list[KnowledgeBaseItem], int]:
    filters = {
        key: value
        for key, value in {
            "category": category,
            "product": product,
            "document_type": document_type,
        }.items()
        if value is not None
    }
    query = active_filter(**filters)
    total = database.kb_items.count_documents(query)
    documents = database.kb_items.find(query).sort(
        [("created_at", DESCENDING), ("_id", DESCENDING)]
    ).skip(skip).limit(limit)
    return [KnowledgeBaseItem.model_validate(document) for document in documents], total


def search_items(
    database: Database,
    *,
    query_text: str | None,
    skip: int,
    limit: int,
    category: str | None,
    product: str | None,
    document_type: str | None,
) -> tuple[list[tuple[KnowledgeBaseItem, float | None]], int]:
    """Search the existing text index, or filter and sort without text scoring."""
    filters = {
        key: value
        for key, value in {
            "category": category,
            "product": product,
            "document_type": document_type,
        }.items()
        if value is not None
    }
    query = active_filter(**filters)
    if query_text is not None:
        query["$text"] = {"$search": query_text}
    total = database.kb_items.count_documents(query)

    if query_text is None:
        documents = database.kb_items.find(query).sort(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
    else:
        documents = database.kb_items.find(
            query, {"relevance_score": {"$meta": "textScore"}}
        ).sort([
            ("relevance_score", {"$meta": "textScore"}),
            ("created_at", DESCENDING),
            ("_id", DESCENDING),
        ])
    results = []
    for document in documents.skip(skip).limit(limit):
        score = float(document["relevance_score"]) if query_text is not None else None
        results.append((KnowledgeBaseItem.model_validate(document), score))
    return results, total


def get_item(database: Database, item_id: ObjectId) -> KnowledgeBaseItem | None:
    document = database.kb_items.find_one(active_filter(_id=item_id))
    return KnowledgeBaseItem.model_validate(document) if document is not None else None


def update_item(
    database: Database, item_id: ObjectId, request: ItemUpdate
) -> KnowledgeBaseItem | None:
    changes = request.model_dump(exclude_unset=True)
    changes["updated_at"] = utc_now()
    document = database.kb_items.find_one_and_update(
        active_filter(_id=item_id),
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    return KnowledgeBaseItem.model_validate(document) if document is not None else None


def soft_delete_item(database: Database, item_id: ObjectId) -> bool:
    now = utc_now()
    result = database.kb_items.update_one(
        active_filter(_id=item_id),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    return result.matched_count == 1
