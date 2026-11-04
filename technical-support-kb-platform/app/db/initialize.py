"""Create the project collections and their indexes safely on repeat runs."""

from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.database import Database

COLLECTIONS = ("users", "kb_items", "interactions")


def initialize_database(database: Database) -> dict[str, list[str]]:
    """Create missing collections and ensure each declared index exists."""
    existing = set(database.list_collection_names())
    for name in COLLECTIONS:
        if name not in existing:
            database.create_collection(name)

    database.users.create_index([("email", ASCENDING)], unique=True, name="email_unique")
    database.kb_items.create_index(
        [("title", TEXT), ("description", TEXT), ("content", TEXT), ("tags", TEXT)],
        name="catalog_text",
    )
    database.kb_items.create_index(
        [("category", ASCENDING), ("product", ASCENDING)],
        name="category_product",
    )
    database.interactions.create_index(
        [("user_id", ASCENDING), ("timestamp", DESCENDING)],
        name="user_history",
    )
    database.interactions.create_index(
        [("item_id", ASCENDING), ("timestamp", DESCENDING)],
        name="item_usage",
    )

    return {name: list(database[name].index_information()) for name in COLLECTIONS}
