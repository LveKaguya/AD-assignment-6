# Technical Support Knowledge Base Recommendation Platform

Assignment #6 for an Advanced Databases master's course. The project is a
starting point for a technical support knowledge base platform, aligned with
the dissertation topic **Hybrid Retrieval and Evidence-Grounded Answer
Generation in RAG for Heterogeneous Technical Support Knowledge Bases**.

## Current scope

This repository provides a small FastAPI application with a `GET /health`
endpoint, validated MongoDB document models, a deterministic synthetic dataset,
account registration, login, profiles, authenticated catalog CRUD and search,
and user interaction tracking. The health endpoint does not query MongoDB.

There is no frontend, vector or semantic search, recommendation algorithm,
vector database, or RAG implementation.

## Requirements

- Python 3.11 or newer
- `pip`
- MongoDB running locally (or a reachable MongoDB URI)

## Setup

Create and activate a standard virtual environment, then install the project
and development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Run the application

No credentials or local configuration files are distributed with this
repository. Generate a new signing secret for your local development session
and supply it through an environment variable:

```bash
# Bash / Zsh
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export JWT_EXPIRE_MINUTES=30
```

For Fish shell, use instead:

```fish
set -gx JWT_SECRET_KEY (python -c 'import secrets; print(secrets.token_urlsafe(48))')
set -gx JWT_EXPIRE_MINUTES 30
```

Keep the same secret across application restarts if previously issued JWTs
should remain valid. Optionally, you may create a private local `.env` file;
the application reads it automatically, but `.gitignore` excludes it from
version control. The application refuses to start when `JWT_SECRET_KEY` is
missing or shorter than 32 bytes, and the token lifetime must be positive.

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` to check the health response, or
`http://127.0.0.1:8000/docs` to view the generated API documentation.
See [docs/authentication.md](docs/authentication.md) for endpoint examples and
the password policy. Seeded synthetic accounts have disabled hashes and
cannot log in.

## Catalog API

Authenticated support engineers can list and read knowledge resources.
Catalog administrators can also create, update, and soft-delete them:

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `/items` | Catalog administrator |
| `GET` | `/items` | Any authenticated user |
| `GET` | `/items/{item_id}` | Any authenticated user |
| `PATCH` | `/items/{item_id}` | Catalog administrator |
| `DELETE` | `/items/{item_id}` | Catalog administrator |
| `GET` | `/items/search` | Any authenticated user |

Listing accepts `skip` (default 0), `limit` (default 20, maximum 100), and
optional `category`, `product`, and `document_type` filters. Delete marks an
item with `deleted_at`; the MongoDB document and interaction references remain,
but normal reads exclude it. See [docs/api_catalog.md](docs/api_catalog.md) for
request, response, and error examples.

`GET /items/search` adds indexed keyword search over titles, descriptions,
content, and tags. It also supports category, product, and document type
filters, including filter-only requests without `q`. Text matches include a
MongoDB relevance score. See [docs/api_search.md](docs/api_search.md) for query
examples and limitations.

## User interactions

Authenticated users can record `view`, `selection`, `helpful`, `unhelpful`, and
`rating` events with `POST /interactions`. The server supplies the user ID and
timestamp. Rating events require an integer from 1 to 5; other event types
cannot carry a rating. `GET /users/me/history` returns only the authenticated
user's events, newest first, with optional event type filtering and pagination.
See [docs/api_interactions.md](docs/api_interactions.md) for examples and
soft-deletion behavior.

To provision a local demonstration administrator, first register a new account
through `/auth/register`, then run:

```bash
python -m scripts.grant_catalog_admin --email engineer@example.invalid
```

The command shows the database and target email and asks you to type the exact
email to confirm. It changes only that existing user's role. Seeded synthetic
accounts have disabled passwords and cannot be promoted by this utility.

## Initialize MongoDB

The initializer uses the database configuration supplied through the shell
(or optional untracked local configuration):

```bash
export MONGODB_URI=mongodb://localhost:27017
export MONGODB_DATABASE=tech_support_recommender
python -m scripts.init_db
```

The command connects, creates the three collections and their indexes, and
prints each collection's indexes. It is safe to run again. It inserts no data.
See [docs/database_design.md](docs/database_design.md) for the schema and index
design.

## Seed synthetic data

After initialization, with the same environment variables set:

```bash
python -m scripts.seed_data
```

This inserts 10 fictional support engineers, 40 knowledge resources, and 160
interaction events. Repeating the command inserts zero new records and does not
overwrite existing records. It prints total collection counts and validates
the seeded interaction references. The command refuses database names ending
in `_test`; it does not initialize indexes. See
[docs/dataset_design.md](docs/dataset_design.md) for composition and limits.

## Integration tests and query analysis

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pytest -q tests/test_e2e.py
.venv/bin/python -m scripts.analyze_queries
.venv/bin/python -m scripts.analyze_search
```

The analysis scripts use the configured MongoDB connection and write four
files under [`docs/results/`](docs/results/):
`query_analysis.json`, `query_analysis.md`, `search_analysis.json`, and
`search_analysis.md`. The scripts use read-only queries and do not initialize
indexes. They require the deterministic seed data to be present. See
[`docs/experimental_methodology.md`](docs/experimental_methodology.md) for the
query shapes, environment, results, and interpretation limits.

Database integration tests use separate databases ending in `_test`. The seed
test removes only its own records, identified by a unique test namespace. The
authentication tests use a separate `_auth_test` database and remove only
their test-created users. Catalog tests use `_catalog_test` and remove only
their test-created users, items, and interactions. Interaction API tests use
`_interactions_test` and remove only their test-created users, items, and
events. The end-to-end test uses `_e2e_test` and removes only its own accounts,
item, and interaction.

The `docs/evidence/` directory contains selected screenshots of the
implementation and tests. `docs/results/` contains saved query analysis
results. Both are included for reproducibility.
# AD-assignment-6
# AD-assignment-6
