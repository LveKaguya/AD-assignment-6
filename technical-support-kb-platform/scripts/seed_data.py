"""Deterministic, insert-only synthetic seed: python -m scripts.seed_data."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from random import Random

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.models.common import MongoModel
from app.models.interaction import Interaction
from app.models.kb_item import KnowledgeBaseItem, SourceMetadata
from app.models.user import User
from scripts.seed_catalog import RESOURCES

SEED_NAMESPACE = "assignment6-synthetic-v1"
SEED_FIELD = "seed_namespace"
BASE_TIME = datetime(2025, 1, 1, tzinfo=timezone.utc)

# Fictional names and role interests; no passwords are generated.
ENGINEERS: tuple[tuple[str, tuple[str, str]], ...] = (
    ("Mira Quill", ("PostgreSQL", "Kubernetes")),
    ("Tarin Vale", ("Ubuntu", "RouterOS")),
    ("Nela Rowan", ("MongoDB", "Docker")),
    ("Soren Lark", ("OpenSSH", "Vault")),
    ("Ivo Mercer", ("Nginx", "OpenVPN")),
    ("Lumi Venn", ("Windows Server", "OIDC")),
    ("Kian Moss", ("Redis", "Terraform")),
    ("Rhea Solin", ("WireGuard", "macOS")),
    ("Aven Reed", ("MySQL", "GitHub Actions")),
    ("Dara Fen", ("systemd", "OpenSSL")),
)


@dataclass(frozen=True)
class SeedDataset:
    users: tuple[User, ...]
    kb_items: tuple[KnowledgeBaseItem, ...]
    interactions: tuple[Interaction, ...]


def stable_id(namespace: str, collection: str, key: str) -> ObjectId:
    """Derive a stable 12-byte ObjectId from the seed namespace and key."""
    digest = sha256(f"{namespace}:{collection}:{key}".encode("utf-8")).digest()
    return ObjectId(digest[:12])


def generate_dataset(namespace: str = SEED_NAMESPACE) -> SeedDataset:
    """Generate identical validated documents for the same namespace."""
    if not namespace.strip():
        raise ValueError("Seed namespace must not be empty")
    if len(RESOURCES) != 40 or len(ENGINEERS) != 10:
        raise ValueError("Seed catalog must contain 40 resources and 10 engineers")

    namespace_tag = sha256(namespace.encode("utf-8")).hexdigest()[:10]
    users = tuple(
        User(
            id=stable_id(namespace, "users", f"engineer-{index:02d}"),
            email=f"engineer{index:02d}-{namespace_tag}@example.invalid",
            name=name,
            password_hash="disabled:sha256:" + sha256(
                f"non-login-account:{namespace}:{index}".encode("utf-8")
            ).hexdigest(),
            role="support_engineer",
            preferred_products=list(products),
            created_at=BASE_TIME + timedelta(days=index),
        )
        for index, (name, products) in enumerate(ENGINEERS, start=1)
    )

    items = tuple(
        KnowledgeBaseItem(
            id=stable_id(namespace, "kb_items", spec.slug),
            title=spec.title,
            description=spec.description,
            content=spec.content,
            category=spec.category,
            document_type=spec.document_type,
            product=spec.product,
            version=spec.version,
            tags=list(spec.tags),
            source=SourceMetadata(
                source_type="fictional support document",
                source_uri=f"https://docs.example.invalid/support/{spec.slug}",
                section=spec.category,
            ),
            created_at=BASE_TIME + timedelta(days=20 + index),
            updated_at=BASE_TIME + timedelta(days=60 + index),
        )
        for index, spec in enumerate(RESOURCES)
    )

    rng = Random(603)
    interactions: list[Interaction] = []
    for user_index, user in enumerate(users):
        follow_ups = ["selection"] * 3 + ["helpful"] * 2 + ["unhelpful"] + ["rating"] * 2
        rng.shuffle(follow_ups)
        for session_index, follow_up in enumerate(follow_ups):
            session_number = user_index * 8 + session_index
            if session_number < 40:
                item = items[session_number]  # Every resource gets at least one view.
            else:
                weights = []
                for item_index, candidate in enumerate(items):
                    popularity = 8 if item_index < 5 else 3 if item_index < 15 else 1
                    affinity = 4 if candidate.product in user.preferred_products else 1
                    quality = 2 if item_index % 7 == 0 else 4
                    feedback = (5 - quality) if follow_up == "unhelpful" else quality
                    weights.append(popularity * affinity * feedback)
                item = rng.choices(items, weights=weights, k=1)[0]

            started = BASE_TIME + timedelta(days=150, hours=session_number * 3)
            interactions.append(
                Interaction(
                    id=stable_id(namespace, "interactions", f"{session_number:03d}-view"),
                    user_id=user.id,
                    item_id=item.id,
                    event_type="view",
                    timestamp=started,
                )
            )
            item_index = items.index(item)
            quality = 2 if item_index % 7 == 0 else 4
            rating = min(5, max(1, quality + rng.choice((-1, 0, 1)))) if follow_up == "rating" else None
            interactions.append(
                Interaction(
                    id=stable_id(namespace, "interactions", f"{session_number:03d}-follow-up"),
                    user_id=user.id,
                    item_id=item.id,
                    event_type=follow_up,
                    rating=rating,
                    timestamp=started + timedelta(minutes=5),
                )
            )

    return SeedDataset(users=users, kb_items=items, interactions=tuple(interactions))


def dataset_collections(dataset: SeedDataset) -> dict[str, tuple[MongoModel, ...]]:
    return {
        "users": dataset.users,
        "kb_items": dataset.kb_items,
        "interactions": dataset.interactions,
    }


def seed_database(database: Database, dataset: SeedDataset, namespace: str) -> dict[str, int]:
    """Insert missing seed documents; never update or remove existing documents."""
    collections = dataset_collections(dataset)
    missing = set(collections) - set(database.list_collection_names())
    if missing:
        raise ValueError(f"Initialize the database first; missing collections: {sorted(missing)}")

    # Check ownership before writing anything. An unlikely ID collision must not
    # make a user-created document part of this synthetic dataset.
    for name, models in collections.items():
        ids = [model.id for model in models]
        existing = database[name].find({"_id": {"$in": ids}}, {SEED_FIELD: 1})
        for document in existing:
            if document.get(SEED_FIELD) != namespace:
                raise ValueError(f"Seed ID collision with unrelated {name} document: {document['_id']}")

    inserted: dict[str, int] = {}
    for name, models in collections.items():
        inserted[name] = 0
        for model in models:
            document = model.to_bson()
            document[SEED_FIELD] = namespace
            result = database[name].update_one(
                {"_id": model.id}, {"$setOnInsert": document}, upsert=True
            )
            inserted[name] += int(result.upserted_id is not None)
    return inserted


def count_documents(database: Database) -> dict[str, int]:
    return {name: database[name].count_documents({}) for name in ("users", "kb_items", "interactions")}


def count_valid_references(database: Database, dataset: SeedDataset) -> int:
    """Count generated interactions whose user and item both exist in MongoDB."""
    user_ids = {doc["_id"] for doc in database.users.find(
        {"_id": {"$in": [user.id for user in dataset.users]}}, {"_id": 1}
    )}
    item_ids = {doc["_id"] for doc in database.kb_items.find(
        {"_id": {"$in": [item.id for item in dataset.kb_items]}}, {"_id": 1}
    )}
    interactions = database.interactions.find(
        {"_id": {"$in": [event.id for event in dataset.interactions]}},
        {"user_id": 1, "item_id": 1},
    )
    return sum(
        event["user_id"] in user_ids and event["item_id"] in item_ids
        for event in interactions
    )


def main() -> None:
    settings = MongoSettings.from_env()
    if settings.database.endswith("_test"):
        raise ValueError("The seed command refuses a test database")
    dataset = generate_dataset()
    client = create_client(settings)
    try:
        client.admin.command("ping")
        database = get_database(client, settings)
        inserted = seed_database(database, dataset, SEED_NAMESPACE)
        counts = count_documents(database)
        valid_references = count_valid_references(database, dataset)
        if valid_references != len(dataset.interactions):
            raise ValueError("Some seeded interaction references are missing")
        print(f"Database: {settings.database}")
        for name in ("users", "kb_items", "interactions"):
            print(f"{name}: {counts[name]} total, {inserted[name]} inserted")
        print(f"Seed interaction references: {valid_references}/{len(dataset.interactions)} valid")
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except (PyMongoError, ValueError) as exc:
        raise SystemExit(f"Seeding failed: {exc}") from exc
