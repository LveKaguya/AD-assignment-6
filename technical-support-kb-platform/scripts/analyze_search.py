"""Read-only lexical search observations using the application's search service."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pymongo.database import Database

from app.core.config import MongoSettings
from app.db.connection import create_client, get_database
from app.services.items import search_items

QUERIES = (
    "PostgreSQL authentication",
    "VPN troubleshooting",
    "Linux permissions",
)
RESULTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "results"


def analyze(database: Database) -> list[dict[str, Any]]:
    analyses: list[dict[str, Any]] = []
    for query_text in QUERIES:
        matches, total = search_items(
            database, query_text=query_text, skip=0, limit=100,
            category=None, product=None, document_type=None,
        )
        results = [
            {
                "rank": rank,
                "id": str(item.id),
                "title": item.title,
                "category": item.category,
                "product": item.product,
                "relevance_score": score,
            }
            for rank, (item, score) in enumerate(matches, start=1)
        ]
        analyses.append({
            "query": query_text,
            "total_matches": total,
            "returned_matches": len(results),
            "categories": sorted({entry["category"] for entry in results}),
            "products": sorted({entry["product"] for entry in results}),
            "results": results,
        })
    return analyses


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Lexical search analysis",
        "",
        f"Generated: {result['generated_at']}  ",
        f"Database: `{result['database']}`  ",
        f"Active catalog documents: {result['active_catalog_count']}",
        "",
        "Results use the same `search_items` service as `GET /items/search`, with",
        "MongoDB `catalog_text` scores and the API's deterministic tie-break order.",
        "Scores are MongoDB text scores for each query and are not relevance judgments.",
        "",
    ]
    for analysis in result["queries"]:
        lines.extend([
            f"## {analysis['query']}",
            "",
            f"Matches: {analysis['total_matches']}; returned: {analysis['returned_matches']}.  ",
            f"Categories: {', '.join(analysis['categories']) or 'none'}.  ",
            f"Products: {', '.join(analysis['products']) or 'none'}.",
            "",
            "| Rank | Document ID | Title | Category | Product | Text score |",
            "| ---: | --- | --- | --- | --- | ---: |",
        ])
        for entry in analysis["results"]:
            lines.append(
                f"| {entry['rank']} | `{entry['id']}` | {entry['title']} | "
                f"{entry['category']} | {entry['product']} | {entry['relevance_score']:.6f} |"
            )
        if not analysis["results"]:
            lines.append("| — | — | No matches | — | — | — |")
        lines.append("")
    lines.extend([
        "## Observed limitations", "",
        "The query result lists show which categories and products share the queried",
        "terms. Broad keyword matches can span different technical contexts. In particular,",
        "words such as `authentication`, `troubleshooting`, and `permissions` may",
        "describe different failure modes or products. MongoDB text search matches lexical",
        "terms; it does not establish that a document resolves a user's specific issue.",
        "The synthetic catalog has no independent relevance labels, so this report does",
        "not calculate Recall@k, MRR, or nDCG@k or classify matches as relevant or irrelevant.",
        "Ranking and score comparisons are meaningful only within the same query and",
        "index configuration.", "",
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
            "active_catalog_count": database.kb_items.count_documents({"deleted_at": None}),
            "queries": analyze(database),
        }
    finally:
        client.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "search_analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESULTS_DIR / "search_analysis.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    for analysis in result["queries"]:
        print(analysis["query"], "matches", analysis["total_matches"])
        for entry in analysis["results"]:
            print(" ", entry["rank"], entry["title"],
                  f"[{entry['category']} / {entry['product']}]",
                  "score", entry["relevance_score"])
    print("Results:", RESULTS_DIR / "search_analysis.json", RESULTS_DIR / "search_analysis.md")


if __name__ == "__main__":
    main()
