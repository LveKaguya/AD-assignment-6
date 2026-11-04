# MongoDB database design

Database: `tech_support_recommender` by default. All three collections use
MongoDB ObjectIds in `_id`. Application models accept ObjectIds or valid hex
strings for identifiers, retain ObjectIds for PyMongo, and serialize them as
strings when JSON is needed. Dates are created in UTC.

The models validate application input. They do not install server-side MongoDB
JSON Schema validators, so direct writes to MongoDB must follow this contract.

## `users`

| Field | Type | Purpose |
| --- | --- | --- |
| `_id` | ObjectId | User identifier. |
| `email` | string | Normalized to lowercase; unique account address. |
| `name` | string | Display name. |
| `password_hash` | string | Argon2id hash for registered accounts; synthetic seed accounts carry disabled markers. |
| `role` | string | `support_engineer` by default; explicit CLI promotion can set `catalog_admin` for catalog writes. |
| `preferred_products` | string array | Product preferences belonging to this user. |
| `created_at` | UTC datetime | Creation time. |

**Index:** `email_unique` on `email` ascending, unique, prevents duplicate
normalized emails and supports account lookup. The model normalizes email
before a write; direct database writes should apply the same normalization.

Product preferences are embedded because they are small values owned by one
user and normally read with that user. Knowledge items are referenced from
interactions rather than embedded in user documents, so a user's history can
grow without enlarging the user document.

## `kb_items`

| Field | Type | Purpose |
| --- | --- | --- |
| `_id` | ObjectId | Knowledge item identifier. |
| `title` | string | Document title. |
| `description` | string | Short summary. |
| `content` | string | Main document text. |
| `category` | string | Category for filtering. |
| `document_type` | string | Kind of source document. |
| `product` | string | Product for filtering. |
| `version` | optional string | Applicable product or document version. |
| `tags` | string array | Topic labels. |
| `source` | embedded document | Provenance fields described below. |
| `created_at` | UTC datetime | Creation time. |
| `updated_at` | UTC datetime | Last modification time, including soft deletion. |
| `deleted_at` | optional UTC datetime | Soft deletion time; null or missing means active. |

`source` contains `source_type` (string), `source_uri` (string), optional
`section` (string), and optional `page` (positive integer). It is embedded
because this provenance belongs to one knowledge item and is typically read
with it. It does not need an independent lifecycle.

**Indexes:** `catalog_text` is a MongoDB text index over `title`,
`description`, `content`, and `tags`. `GET /items/search` uses it through
MongoDB `$text` and projects `textScore` for relevance ordering. The index
does not cover `category`, `product`, `document_type`, or source metadata as
text fields. `category_product` is a compound ascending index for queries
filtering by category and product, and also supports category-only filtering
through its leading field.

Normal catalog queries filter on `deleted_at: null`, which also matches the 40
older seeded documents where the field is absent. This avoids a destructive
migration. `DELETE /items/{item_id}` sets `deleted_at` and `updated_at`; it does
not remove the document. Existing interaction references remain valid, while
normal list and detail reads hide the item. Catalog pages sort by `created_at`
descending and `_id` descending for a stable tie-breaker. The existing indexes
are unchanged for this assignment. The catalog currently has a small number
of documents, so search reuses the existing text and metadata indexes. Other
filter and sort patterns should be measured before adding indexes.

## `interactions`

| Field | Type | Purpose |
| --- | --- | --- |
| `_id` | ObjectId | Interaction identifier. |
| `user_id` | ObjectId | Reference to `users._id`. |
| `item_id` | ObjectId | Reference to `kb_items._id`. |
| `event_type` | enum string | `view`, `selection`, `helpful`, `unhelpful`, or `rating`. |
| `rating` | optional integer | Required and 1–5 for a `rating` event; absent for other event types. |
| `timestamp` | UTC datetime | Event time assigned by the server for API-created events. |

**Indexes:** `user_history` on `user_id` ascending and `timestamp`
descending supports `GET /users/me/history` and a user's recent interactions.
The history query also sorts `_id` descending to break timestamp ties; for the
current small corpus, this does not justify changing the existing index.
`item_usage` on `item_id`
ascending and `timestamp` descending supports recent item usage and
time-bounded analysis of an item.

The user and item are referenced by ObjectId because both have independent
lifecycles and can participate in many interactions. Referencing avoids
duplicating full user and knowledge documents for every event. MongoDB does
not enforce these cross-collection references automatically. API creation
checks that the referenced item is active. Soft deletion later preserves the
item record and all historical interaction references.

## Initialization and test isolation

Run `python -m scripts.init_db` after setting `MONGODB_URI` and
`MONGODB_DATABASE`. The script creates collections and indexes without
inserting data. Repeated runs keep the same schema. The integration test uses
`<MONGODB_DATABASE>_test` and does not delete any records or collections.
