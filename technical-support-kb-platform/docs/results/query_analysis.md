# MongoDB query execution analysis

Generated: 2026-11-03T20:44:24.609771+00:00  
Database: `tech_support_recommender`  
MongoDB: `8.3.9`

All metrics come from MongoDB `explain` with `executionStats` verbosity.
`executionTimeMillis` measures the explained database operation, not API latency.
A null metric means it was absent from the server output.

| Query | Collection (size) | Returned | Keys | Docs | Time (ms) | Winning index(es) | Scan |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Q1 | users (12) | 1 | 1 | 1 | 0 | email_unique | index traversal |
| Q2 | kb_items (41) | 2 | 2 | 2 | 0 | category_product | index traversal |
| Q3 | kb_items (41) | 5 | 7 | 10 | 0 | catalog_text | index traversal |
| Q4 | interactions (161) | 16 | 16 | 16 | 0 | user_history | index traversal |
| Q5 | interactions (161) | 8 | 8 | 8 | 0 | item_usage | index traversal |

## Q1: User lookup by normalized email

Filter: `{"email": "engineer01-e33d8cca4b@example.invalid"}`  
Sort: `null`  
Winning plan stages: `EXPRESS_IXSCAN`


## Q2: Active catalog category and product filter

Filter: `{"deleted_at": null, "category": "Networking", "product": "RouterOS"}`  
Sort: `{"created_at": -1, "_id": -1}`  
Winning plan stages: `FETCH, IXSCAN, SORT`


## Q3: Active catalog full-text search

Filter: `{"deleted_at": null, "$text": {"$search": "PostgreSQL authentication"}}`  
Sort: `{"relevance_score": {"$meta": "textScore"}, "created_at": -1, "_id": -1}`  
Winning plan stages: `FETCH, IXSCAN, PROJECTION_DEFAULT, SORT, TEXT_MATCH, TEXT_OR`


## Q4: Personal interaction history, newest first

Filter: `{"user_id": {"$oid": "b5150c0ea1ff9052a6ae5350"}}`  
Sort: `{"timestamp": -1, "_id": -1}`  
Winning plan stages: `FETCH, IXSCAN, SORT`


## Q5: Item usage events, newest first

Filter: `{"item_id": {"$oid": "4d45f60331a7457479ecc22d"}}`  
Sort: `{"timestamp": -1}`  
Winning plan stages: `FETCH, IXSCAN, LIMIT`


## Interpretation limits

These are individual query executions on a small synthetic dataset. A selected index
shows the observed plan for these values and this dataset; it does not prove faster
execution at other sizes or under load. A small collection can lead the planner to
choose a collection scan. Sort stages may remain even when an index supplies filtering.
The JSON file contains the exact returned metrics and query specifications.
