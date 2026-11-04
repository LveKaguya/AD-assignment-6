"""Read-only executionStats analysis of five application query patterns."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo.database import Database
from pymongo.errors import OperationFailure

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from scripts.seed_data import generate_dataset

RESULTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "results"


def as_json(value: Any) -> Any:
    """Preserve ObjectId and other BSON types in Extended JSON."""
    return json.loads(json_util.dumps(value))


def plan_details(winning_plan: Any) -> tuple[list[str], list[str]]:
    """Walk nested classic and SBE query plans, including shard subplans."""
    stages: set[str] = set()
    indexes: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("stage"), str):
                stages.add(node["stage"])
            if isinstance(node.get("indexName"), str):
                indexes.add(node["indexName"])
            for child in node.values():
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(winning_plan)
    return sorted(stages), sorted(indexes)


def explain_query(
    database: Database, *, label: str, description: str, collection: str,
    filter_spec: dict[str, Any], sort_spec: dict[str, Any] | None = None,
    projection: dict[str, Any] | None = None, limit: int = 20,
) -> dict[str, Any]:
    command: dict[str, Any] = {
        "find": collection, "filter": filter_spec, "limit": limit,
    }
    if sort_spec is not None:
        command["sort"] = sort_spec
    if projection is not None:
        command["projection"] = projection

    error: str | None = None
    try:
        explain = database.command({"explain": command, "verbosity": "executionStats"})
    except OperationFailure as exc:
        # An unsupported explain shape must remain visibly unmeasured.
        explain = {}
        error = f"{type(exc).__name__}: {exc}"
    planner = explain.get("queryPlanner")
    stats = explain.get("executionStats")
    planner = planner if isinstance(planner, dict) else {}
    stats = stats if isinstance(stats, dict) else {}
    winning_plan = planner.get("winningPlan")
    stages, indexes = plan_details(winning_plan)
    plan_available = isinstance(winning_plan, (dict, list))
    traversal_stages = {"IXSCAN", "IXSEEK", "DISTINCT_SCAN", "COUNT_SCAN", "TEXT_MATCH"}
    traversed_index = any(
        stage in traversal_stages or stage.endswith("IXSCAN") for stage in stages
    )
    return {
        "id": label,
        "description": description,
        "database": database.name,
        "collection": collection,
        "collection_size": database[collection].count_documents({}),
        "filter": as_json(filter_spec),
        "sort": as_json(sort_spec) if sort_spec is not None else None,
        "projection": as_json(projection) if projection is not None else None,
        "limit": limit,
        "nReturned": stats.get("nReturned"),
        "totalKeysExamined": stats.get("totalKeysExamined"),
        "totalDocsExamined": stats.get("totalDocsExamined"),
        "executionTimeMillis": stats.get("executionTimeMillis"),
        "winning_plan_stages": stages,
        "winning_plan_indexes": indexes,
        "index_traversal_observed": traversed_index if plan_available else None,
        "collection_scan_observed": ("COLLSCAN" in stages) if plan_available else None,
        "explain_error": error,
    }


def analyze(database: Database) -> list[dict[str, Any]]:
    seed = generate_dataset()
    user = seed.users[0]
    item = seed.kb_items[0]
    if database.users.find_one({"_id": user.id}) is None:
        raise ValueError("Seeded user is absent; initialize and seed this database first")
    if database.kb_items.find_one({"_id": item.id}) is None:
        raise ValueError("Seeded item is absent; initialize and seed this database first")
    if database.interactions.find_one({"user_id": user.id, "item_id": item.id}) is None:
        raise ValueError("Expected seeded interaction is absent")
    if database.kb_items.count_documents({"deleted_at": None, "$text": {"$search": "PostgreSQL authentication"}}) == 0:
        raise ValueError("No active documents match the predefined text query")

    active = {"deleted_at": None}
    return [
        explain_query(
            database, label="Q1", description="User lookup by normalized email",
            collection="users", filter_spec={"email": user.email}, limit=1,
        ),
        explain_query(
            database, label="Q2", description="Active catalog category and product filter",
            collection="kb_items",
            filter_spec={**active, "category": item.category, "product": item.product},
            sort_spec={"created_at": -1, "_id": -1},
        ),
        explain_query(
            database, label="Q3", description="Active catalog full-text search",
            collection="kb_items",
            filter_spec={**active, "$text": {"$search": "PostgreSQL authentication"}},
            sort_spec={"relevance_score": {"$meta": "textScore"},
                       "created_at": -1, "_id": -1},
            projection={"relevance_score": {"$meta": "textScore"}},
        ),
        explain_query(
            database, label="Q4", description="Personal interaction history, newest first",
            collection="interactions", filter_spec={"user_id": user.id},
            sort_spec={"timestamp": -1, "_id": -1},
        ),
        explain_query(
            database, label="Q5", description="Item usage events, newest first",
            collection="interactions", filter_spec={"item_id": item.id},
            sort_spec={"timestamp": -1},
        ),
    ]


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# MongoDB query execution analysis",
        "",
        f"Generated: {result['generated_at']}  ",
        f"Database: `{result['database']}`  ",
        f"MongoDB: `{result['mongodb_version']}`",
        "",
        "All metrics come from MongoDB `explain` with `executionStats` verbosity.",
        "`executionTimeMillis` measures the explained database operation, not API latency.",
        "A null metric means it was absent from the server output.",
        "",
        "| Query | Collection (size) | Returned | Keys | Docs | Time (ms) | Winning index(es) | Scan |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for query in result["queries"]:
        if query["collection_scan_observed"] is None:
            scan = "plan unavailable"
        elif query["collection_scan_observed"]:
            scan = "COLLSCAN"
        elif query["index_traversal_observed"]:
            scan = "index traversal"
        else:
            scan = "neither established"
        metrics = [query[key] for key in (
            "nReturned", "totalKeysExamined", "totalDocsExamined", "executionTimeMillis"
        )]
        lines.append(
            f"| {query['id']} | {query['collection']} ({query['collection_size']}) | "
            + " | ".join(str(value) if value is not None else "unknown" for value in metrics)
            + f" | {', '.join(query['winning_plan_indexes']) or 'not established'} | {scan} |"
        )
    lines.extend([""])
    for query in result["queries"]:
        lines.extend([
            f"## {query['id']}: {query['description']}",
            "",
            f"Filter: `{json.dumps(query['filter'], ensure_ascii=False)}`  ",
            f"Sort: `{json.dumps(query['sort'], ensure_ascii=False)}`  ",
            f"Winning plan stages: `{', '.join(query['winning_plan_stages']) or 'not available'}`",
            f"Explain error: `{query['explain_error']}`" if query["explain_error"] else "",
            "",
        ])
    lines.extend([
        "## Interpretation limits", "",
        "These are individual query executions on a small synthetic dataset. A selected index",
        "shows the observed plan for these values and this dataset; it does not prove faster",
        "execution at other sizes or under load. A small collection can lead the planner to",
        "choose a collection scan. Sort stages may remain even when an index supplies filtering.",
        "The JSON file contains the exact returned metrics and query specifications.", "",
    ])
    return "\n".join(lines)


def main() -> None:
    settings = MongoSettings.from_env()
    client = create_client(settings)
    try:
        client.admin.command("ping")
        database = get_database(client, settings)
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": database.name,
            "mongodb_version": client.server_info()["version"],
            "queries": analyze(database),
        }
    finally:
        client.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "query_analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESULTS_DIR / "query_analysis.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    for query in result["queries"]:
        print(query["id"], query["description"],
              "returned", query["nReturned"],
              "keys", query["totalKeysExamined"],
              "docs", query["totalDocsExamined"],
              "ms", query["executionTimeMillis"],
              "indexes", query["winning_plan_indexes"],
              "collection_scan", query["collection_scan_observed"])
    print("Results:", RESULTS_DIR / "query_analysis.json", RESULTS_DIR / "query_analysis.md")


if __name__ == "__main__":
    main()
