"""Integration test: create only schema objects in a separate test database."""

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.db.initialize import initialize_database


def test_initialization_is_repeatable_in_test_database() -> None:
    production_settings = MongoSettings.from_env()
    test_settings = MongoSettings(
        uri=production_settings.uri,
        database=f"{production_settings.database}_test",
    )
    assert test_settings.database != production_settings.database

    client = create_client(test_settings)
    try:
        database = get_database(client, test_settings)
        first = initialize_database(database)
        second = initialize_database(database)

        assert first == second
        assert set(first) == {"users", "kb_items", "interactions"}
        assert database.users.index_information()["email_unique"]["unique"] is True
        assert "catalog_text" in database.kb_items.index_information()
        assert "category_product" in database.kb_items.index_information()
        assert "user_history" in database.interactions.index_information()
        assert "item_usage" in database.interactions.index_information()
    finally:
        client.close()
