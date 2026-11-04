"""Initialize MongoDB collections and indexes: python -m scripts.init_db."""

from pymongo.errors import PyMongoError

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.db.initialize import initialize_database


def main() -> None:
    settings = MongoSettings.from_env()
    client = create_client(settings)
    try:
        client.admin.command("ping")
        indexes = initialize_database(get_database(client, settings))
        print(f"Database: {settings.database}")
        for collection, names in indexes.items():
            print(f"{collection}: {', '.join(names)}")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except (PyMongoError, ValueError) as exc:
        raise SystemExit(f"MongoDB initialization failed: {exc}") from exc
