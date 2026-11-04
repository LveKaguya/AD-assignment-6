# Knowledge base search API

`GET /items/search` requires a Bearer JWT and returns active knowledge items
with pagination. The route is registered before `GET /items/{item_id}` so
`search` is treated as a path segment, not an ObjectId.

## Parameters

| Parameter | Meaning |
| --- | --- |
| `q` | Optional keyword query, at most 200 characters. If supplied, it must contain a letter or digit. |
| `category` | Optional exact match: Networking, Operating Systems, Database Systems, Deployment and DevOps, or Security. |
| `product` | Optional exact product match, at most 100 characters and not blank. |
| `document_type` | Optional exact match: troubleshooting guide, FAQ, configuration manual, or release notes. |
| `skip` | Nonnegative offset; default 0. |
| `limit` | Page size from 1 to 100; default 20. |

Unknown category or document type values, blank queries, and invalid page
sizes return 422. An omitted `q` performs a filter-only query; with no filters
it lists all active items. Empty matches return 200 with `items: []` and
`total: 0`. Authentication failures return 401.

## Examples

```http
GET /items/search?q=PostgreSQL%20authentication&category=Database%20Systems&limit=10
Authorization: Bearer <access token>
```

```http
GET /items/search?product=WireGuard&document_type=troubleshooting%20guide&skip=0&limit=20
Authorization: Bearer <access token>
```

The response has the same item fields as `GET /items`, plus
`relevance_score` on each hit. This example score is illustrative; MongoDB
computes it from the indexed text:

```json
{
  "items": [
    {
      "id": "0123456789abcdef01234567",
      "title": "PostgreSQL authentication guide",
      "description": "A sample technical description.",
      "content": "A sample guide with diagnostic steps and a resolution.",
      "category": "Database Systems",
      "document_type": "troubleshooting guide",
      "product": "PostgreSQL",
      "version": "16",
      "tags": ["authentication"],
      "source": {"source_type": "sample", "source_uri": "https://docs.example.invalid/sample", "section": null, "page": null},
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "deleted_at": null,
      "relevance_score": 2.5
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 10
}
```

For a filter-only query, `relevance_score` is `null` because no text score
is computed. `total` counts all active matches before pagination.

## Index, ranking, and limitations

Keyword queries use the existing `catalog_text` MongoDB text index on
`title`, `description`, `content`, and `tags`. Metadata filters are combined
with the `$text` predicate, and every query excludes documents with a
non-null `deleted_at`. Text results sort by MongoDB `textScore` descending,
then `created_at` and `_id` descending for stable ties. Filter-only results
sort by `created_at` and `_id` descending. No new index is created for this
endpoint.

MongoDB's `$text` search treats separate terms as alternatives by default;
quoted phrases can narrow a query. The score expresses relative lexical
match quality within a query, not a probability or a cross-query quality
measure. The index uses MongoDB's language processing, including stemming
and stop words. It does not provide typo tolerance, prefix matching, semantic
similarity, vector retrieval, or evidence-grounded answers. Technical
identifiers with punctuation may be tokenized differently than users expect.

See MongoDB's official [`$text` query](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
and [`$meta: textScore`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/meta/)
documentation for query and scoring rules.
