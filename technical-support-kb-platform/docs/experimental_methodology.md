# Task 08: integration and MongoDB query experiment

This is a reproducible local experiment on the development database snapshot of
**2026-11-04 (Asia/Almaty)**. The machine-readable observations are in
[`results/query_analysis.json`](results/query_analysis.json) and
[`results/search_analysis.json`](results/search_analysis.json). Re-run the
commands in the README to refresh all four result files after data changes.

## 6.1 Experimental Objective

Verify that the implemented API supports a complete authenticated support
workflow and inspect how MongoDB executes five representative read queries.
Record the output of lexical catalog searches without assuming that text score
is a human relevance judgment. The experiment evaluates this implementation
and this small database snapshot; it is not a throughput benchmark.

## 6.2 Software and Hardware Environment

Values below were read from the running environment during this experiment:

| Component | Observed value |
| --- | --- |
| Python | 3.14.8, project-local `.venv` |
| MongoDB server | 8.3.9, local `mongodb://localhost:27017` |
| PyMongo | 4.19.0 |
| FastAPI | 0.162.0 |
| Starlette | 1.10.0 |
| Pydantic | 2.14.2 |
| pytest | 8.4.2 |
| Operating system | Linux 7.2.11-1-cachyos, x86_64 |
| CPU | Intel Core i7-14650HX; 16 cores and 24 logical CPUs reported by `lscpu` |
| Memory | 31 GiB total reported by `free -h` |

These are the visible host values. CPU load, cache state, and MongoDB memory
usage were not controlled or measured. No inference about other machines is made.

## 6.3 Dataset Description

The development database is `tech_support_recommender`. At the beginning of
the run, it contained **12 users, 41 knowledge items, and 161 interactions**.
The deterministic seed accounts for 10 users, 40 active items, and 160
interactions. Local manual activity accounts for the additional records; 40
catalog items were active at analysis time. The catalog covers Networking,
Operating Systems, Database Systems, Deployment and DevOps, and Security.
Document types include troubleshooting guides, FAQs, configuration manuals,
and release notes. The seed and its construction are described in
[`dataset_design.md`](dataset_design.md).

The dataset is synthetic. It contains realistic technical vocabulary and
version-specific cases, but its term frequencies, user behavior, and usefulness
feedback do not represent a measured production workload.

## 6.4 Integration Testing Methodology

`tests/test_e2e.py` uses the dedicated database
`tech_support_recommender_e2e_test`. It creates uniquely named accounts through
registration, promotes only the test administrator through the explicit grant
function, and performs login, profile, health, catalog browse and search,
interaction creation, personal history, role checks, update, and soft deletion
through the FastAPI test client. It then checks that the item is hidden from
normal reads and searches while the stored interaction still references it.
Another authenticated account sees its own empty history.

The fixture deletes only the ObjectIds it created and leaves other documents
in the test database alone. Other integration tests also use their own test
databases. The development database is never a test target.

## 6.5 MongoDB Query Analysis Methodology

`python -m scripts.analyze_queries` runs read-only `explain` commands with
`executionStats` verbosity. It records `nReturned`, `totalKeysExamined`,
`totalDocsExamined`, and `executionTimeMillis` directly from the server output.
It traverses nested winning-plan stages, including index names, and records
whether index traversal or a collection scan appears. Missing fields remain
null. The query filters, sorts, projection, limit, database, collection, and
collection size are captured in Extended JSON so ObjectIds retain their type.

| Query | Application pattern | Actual values used |
| --- | --- | --- |
| Q1 | User lookup by normalized email | Seeded `engineer01-e33d8cca4b@example.invalid` |
| Q2 | Active catalog category and product filter | `Networking`, `RouterOS` |
| Q3 | Active catalog text retrieval and score sort | `PostgreSQL authentication` |
| Q4 | Current user's history, timestamp then `_id` descending | First seeded user |
| Q5 | Item usage events, timestamp descending | First seeded knowledge item |

Q1–Q4 follow application read patterns. Q5 is the index-supported item usage
analysis pattern; there is no item usage API. Seeded identifiers are checked
against the database before analysis. No index hints are used, so MongoDB
chooses the winning plan. The script creates no indexes and changes no records.

## 6.6 Lexical Search Analysis

`python -m scripts.analyze_search` calls the existing `search_items` service
with the predefined queries `PostgreSQL authentication`, `VPN troubleshooting`,
and `Linux permissions`. It records every returned ObjectId, title, category,
product, MongoDB text score, and rank. The service uses the `catalog_text`
index over title, description, content, and tags and excludes soft-deleted
items. The result order uses text score followed by the API's deterministic
secondary sort. No independent relevance labels were collected.

## 6.7 Results

The complete query specifications and raw returned metrics are in
[`results/query_analysis.json`](results/query_analysis.json); a readable table
is in [`results/query_analysis.md`](results/query_analysis.md).

| Query | Returned | Keys examined | Docs examined | Time (ms) | Winning index |
| --- | ---: | ---: | ---: | ---: | --- |
| Q1 | 1 | 1 | 1 | 0 | `email_unique` |
| Q2 | 2 | 2 | 2 | 0 | `category_product` |
| Q3 | 5 | 7 | 10 | 0 | `catalog_text` |
| Q4 | 16 | 16 | 16 | 0 | `user_history` |
| Q5 | 8 | 8 | 8 | 0 | `item_usage` |

All five winning plans named the listed index; none contained `COLLSCAN`.
Q1 used MongoDB's `EXPRESS_IXSCAN` stage. Q2–Q4 also included a `SORT` stage,
so index selection did not eliminate all sorting. Q5 did not show a separate
sort stage. A zero-millisecond `executionTimeMillis` is the server's reported
integer value for these tiny operations and is not evidence of zero elapsed
time or API latency.

The search results are in [`results/search_analysis.json`](results/search_analysis.json)
and [`results/search_analysis.md`](results/search_analysis.md). The three
queries returned **5, 5, and 4** documents, respectively. For `PostgreSQL
authentication`, the first two ranked titles describe PostgreSQL 16 and 15
SCRAM mismatches, while the fifth is a Kubernetes private registry document.
For `VPN troubleshooting`, matches span Networking, Security, and Operating
Systems. For `Linux permissions`, the highest-scored title concerns GitHub
Actions token permissions. These are observations of term matching and ranking,
not judgments that any item is objectively relevant or irrelevant.

The complete pytest suite, including the new end-to-end workflow, passed
**93 tests** with one deprecation warning from the installed
Starlette/httpx test-client integration.

## 6.8 Discussion and Limitations

The current synthetic dataset is too small to support claims about throughput,
latency distributions, or scalability. One `explain` execution per query is
diagnostic plan evidence, not a controlled timing experiment. Collection
contents and the query planner's choices may change when more data is added.
`executionTimeMillis` is not end-to-end API response time.

MongoDB text search is lexical. Broad terms and ambiguous technical vocabulary
can retrieve documents from different products and failure contexts; score
alone does not establish whether a document answers a support question. There
are no independently labeled relevance judgments, so Recall@k, MRR, and
nDCG@k are intentionally absent. The synthetic interactions likewise cannot
be treated as validated human relevance feedback.
