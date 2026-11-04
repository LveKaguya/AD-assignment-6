"""Synthetic dataset checks and isolated MongoDB seeding integration test."""

from collections import Counter
from uuid import uuid4

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.db.initialize import initialize_database
from app.models.interaction import Interaction
from app.models.kb_item import KnowledgeBaseItem
from app.models.user import User
from scripts.seed_data import (
    SEED_FIELD,
    count_documents,
    count_valid_references,
    dataset_collections,
    generate_dataset,
    seed_database,
)


def test_generated_dataset_is_valid_and_deterministic() -> None:
    first = generate_dataset()
    second = generate_dataset()

    assert (len(first.users), len(first.kb_items), len(first.interactions)) == (10, 40, 160)
    assert {
        name: [model.to_bson() for model in models]
        for name, models in dataset_collections(first).items()
    } == {
        name: [model.to_bson() for model in models]
        for name, models in dataset_collections(second).items()
    }

    assert all(User.model_validate(user.to_bson()) for user in first.users)
    assert all(KnowledgeBaseItem.model_validate(item.to_bson()) for item in first.kb_items)
    assert all(Interaction.model_validate(event.to_bson()) for event in first.interactions)
    assert {item.category for item in first.kb_items} == {
        "Networking", "Operating Systems", "Database Systems", "Deployment and DevOps", "Security"
    }
    assert len({item.id for item in first.kb_items}) == 40
    assert all(item.source.source_uri.startswith("https://docs.example.invalid/") for item in first.kb_items)

    user_ids = {user.id for user in first.users}
    item_ids = {item.id for item in first.kb_items}
    assert all(event.user_id in user_ids and event.item_id in item_ids for event in first.interactions)
    assert Counter(event.event_type for event in first.interactions) == {
        "view": 80, "selection": 30, "helpful": 20, "unhelpful": 10, "rating": 20
    }
    assert all(
        (event.rating is not None and 1 <= event.rating <= 5)
        if event.event_type == "rating" else event.rating is None
        for event in first.interactions
    )


def test_seed_is_idempotent_and_metadata_is_queryable_in_test_database() -> None:
    production_settings = MongoSettings.from_env()
    test_settings = MongoSettings(
        uri=production_settings.uri,
        database=f"{production_settings.database}_seed_test",
    )
    assert test_settings.database != production_settings.database
    namespace = f"assignment6-test-{uuid4().hex}"
    dataset = generate_dataset(namespace)
    client = create_client(test_settings)
    try:
        database = get_database(client, test_settings)
        initialize_database(database)
        before = count_documents(database)

        first = seed_database(database, dataset, namespace)
        after_first = count_documents(database)
        second = seed_database(database, dataset, namespace)
        after_second = count_documents(database)

        assert first == {"users": 10, "kb_items": 40, "interactions": 160}
        assert second == {"users": 0, "kb_items": 0, "interactions": 0}
        assert after_first == after_second
        assert after_first == {
            "users": before["users"] + 10,
            "kb_items": before["kb_items"] + 40,
            "interactions": before["interactions"] + 160,
        }
        assert count_valid_references(database, dataset) == 160

        matches = list(database.kb_items.find({
            SEED_FIELD: namespace,
            "category": "Database Systems",
            "product": "PostgreSQL",
            "version": "16",
        }))
        assert len(matches) >= 2
        assert any("SCRAM" in item["title"] for item in matches)

        # A rerun must not overwrite an existing document, even one from this seed.
        database.kb_items.update_one(
            {"_id": dataset.kb_items[0].id, SEED_FIELD: namespace},
            {"$set": {"description": "Locally edited test description"}},
        )
        assert seed_database(database, dataset, namespace) == {
            "users": 0, "kb_items": 0, "interactions": 0
        }
        assert database.kb_items.find_one({"_id": dataset.kb_items[0].id})["description"] == (
            "Locally edited test description"
        )
    finally:
        # The random namespace identifies only records created by this test.
        for name, models in dataset_collections(dataset).items():
            client[test_settings.database][name].delete_many({
                "_id": {"$in": [model.id for model in models]},
                SEED_FIELD: namespace,
            })
        client.close()
