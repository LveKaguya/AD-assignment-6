# User interaction API

Both endpoints require `Authorization: Bearer <access token>` from
`POST /auth/login`. Missing or invalid authentication returns 401. The API
derives the user ID from the JWT, and the client cannot submit `user_id`.

## Record an event

`POST /interactions` appends one event and returns 201. Event meanings:

| Event type | Meaning |
| --- | --- |
| `view` | The user opened a resource. |
| `selection` | The user selected a resource from a list or search result. |
| `helpful` | The user marked the resource helpful. |
| `unhelpful` | The user marked it unhelpful. |
| `rating` | The user gave an integer rating from 1 to 5. |

```http
POST /interactions
Authorization: Bearer <access token>
Content-Type: application/json

{"item_id":"0123456789abcdef01234567","event_type":"rating","rating":4}
```

The `rating` field is required only when `event_type` is `rating`; it is
rejected for every other event type. For example, a view request contains
only `item_id` and `event_type`. The server assigns `_id`, `user_id`, and a
UTC `timestamp`. A successful response has this structure:

```json
{
  "id": "89abcdef0123456701234567",
  "user_id": "abcdef012345670123456789",
  "item_id": "0123456789abcdef01234567",
  "event_type": "rating",
  "rating": 4,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

The IDs and timestamp above illustrate the response shape. A malformed item
ID returns 400. A missing or soft-deleted item returns 404 with
`Knowledge item not found`. Invalid event types, ratings, or unexpected fields
such as `user_id`, `_id`, and `timestamp` return 422. Events are append-only:
recording one never updates an earlier event.

## Read your history

`GET /users/me/history` returns only the authenticated user's events. It
accepts `skip` (default 0, nonnegative), `limit` (default 20, maximum 100),
and optional `event_type` (`view`, `selection`, `helpful`, `unhelpful`, or
`rating`). For example:

```http
GET /users/me/history?event_type=helpful&skip=0&limit=20
Authorization: Bearer <access token>
```

```json
{
  "interactions": [
    {
      "id": "89abcdef0123456701234567",
      "user_id": "abcdef012345670123456789",
      "item_id": "0123456789abcdef01234567",
      "event_type": "helpful",
      "rating": null,
      "timestamp": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

Results sort by `timestamp` descending, then `_id` descending for stable
ties. `total` counts matching events before pagination. A user without events
receives `interactions: []` and `total: 0`. There is no route for reading
another user's history.

The existing `user_history` index starts with `user_id` and then descending
`timestamp`, matching the history access pattern. The `item_usage` index
starts with `item_id` and descending `timestamp` for future per-item usage
analysis. No index was added for these endpoints.

Soft deletion hides an item from normal catalog reads and blocks new events
for it, but the MongoDB item and previously recorded interaction references
remain. Historical events therefore still appear in personal history.

These events could later provide signals for recommendation experiments, but
no recommendation algorithm is implemented here. The original 160 seeded
events are synthetic and their popularity and feedback patterns do not prove
real user usefulness. Logged events also depend on clients reporting actions
accurately; an event is not independent evidence that a document solved a
support problem.
