"""PyMongo client creation. The API does not connect until a caller uses this."""

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import MongoSettings


def create_client(settings: MongoSettings) -> MongoClient:
    return MongoClient(settings.uri, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_database(client: MongoClient, settings: MongoSettings) -> Database:
    return client[settings.database]
