"""FastAPI dependency for the configured MongoDB database."""

from collections.abc import Iterator

from pymongo.database import Database

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database


def database_dependency() -> Iterator[Database]:
    """Give one request a database handle and close its client afterward."""
    settings = MongoSettings.from_env()
    client = create_client(settings)
    try:
        yield get_database(client, settings)
    finally:
        client.close()
