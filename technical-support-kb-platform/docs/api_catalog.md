# Knowledge catalog API

All catalog routes require a Bearer token from `POST /auth/login`. A registered
user has the `support_engineer` role and can read the catalog. Only a user
explicitly granted `catalog_admin` may create, update, or delete items.
Registration and profile requests cannot set a role.

The API accepts these categories: `Networking`, `Operating Systems`,
`Database Systems`, `Deployment and DevOps`, and `Security`. Document types are
`troubleshooting guide`, `FAQ`, `configuration manual`, and `release notes`.
Titles must be 5–200 characters, descriptions 10–1000, and content at least
20. Whitespace is trimmed from these fields. `product` is a nonempty string;
`version`, `tags`, and source `section`/`page` are optional. A source needs
`source_type` and `source_uri`; page numbers start at 1.

## Create

`POST /items` requires a catalog administrator and returns 201. Example:

```http
POST /items
Authorization: Bearer <access token>
Content-Type: application/json

{
  "title": "Diagnose replica connection timeout",
  "description": "Clients time out when connecting to a database replica.",
  "content": "Check replica health, DNS resolution, and the connection pool. Compare the advertised host with the reachable network address before retrying.",
  "category": "Database Systems",
  "document_type": "troubleshooting guide",
  "product": "ExampleDB",
  "version": "2.0",
  "tags": ["replica", "timeout"],
  "source": {
    "source_type": "internal guide",
    "source_uri": "https://docs.example.invalid/replica-timeout",
    "section": "Connectivity"
  }
}
```

A successful response includes the generated ObjectId as a string in `id`,
all resource fields, `created_at`, `updated_at`, and `deleted_at: null`. The
server controls ID and lifecycle timestamps. Unknown fields are rejected.

## List and retrieve

`GET /items?skip=0&limit=20&category=Database%20Systems&product=ExampleDB`
returns 200 with this structure:

```json
{
  "items": [{"id": "0123456789abcdef01234567", "title": "Diagnose replica connection timeout", "description": "...", "content": "...", "category": "Database Systems", "document_type": "troubleshooting guide", "product": "ExampleDB", "version": "2.0", "tags": ["replica", "timeout"], "source": {"source_type": "internal guide", "source_uri": "https://docs.example.invalid/replica-timeout", "section": "Connectivity", "page": null}, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z", "deleted_at": null}],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

The list uses exact optional `category`, `product`, and `document_type`
filters. `skip` must be nonnegative; `limit` must be 1–100. Results sort by
newest `created_at`, then `_id` descending. `total` counts active matches
before pagination. `GET /items/{item_id}` returns one active item. A malformed
ObjectId returns 400, and a missing or deleted item returns 404.

## Update and delete

`PATCH /items/{item_id}` requires a catalog administrator. Send any nonempty
subset of `title`, `description`, `content`, `category`, `document_type`,
`product`, `version`, `tags`, and `source`. The `source` field replaces the
embedded source object as a whole. Set `version` to null to clear it. The API
updates `updated_at` and returns the updated item. It rejects `_id`, `id`,
`created_at`, `updated_at`, `deleted_at`, and other unknown fields with 422.

`DELETE /items/{item_id}` returns 204 and sets `deleted_at` and `updated_at`.
It does **not** remove the MongoDB document or its interaction references.
Normal list and detail requests exclude the item afterward; a second delete
returns 404. Missing authentication returns 401, while a support engineer
attempting a write receives 403.

## Grant a local administrator

Register a normal user first, then run:

```bash
python -m scripts.grant_catalog_admin --email engineer@example.invalid
```

The utility displays the selected database and normalized email. It requires
typing that exact email to confirm before changing the stored role to
`catalog_admin`. It refuses unknown users, other roles, and disabled synthetic
accounts. It never runs during registration or seeding. Check the displayed
database before confirming; use a registered account with a usable password.
