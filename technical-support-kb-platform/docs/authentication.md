# Authentication and profile API

These endpoints use the existing `users` collection. Public responses never
contain `password_hash`. JWT access tokens are signed with HS256 and include
the user's ObjectId string in `sub` plus `iat` and `exp` claims. A protected
request verifies the signature and expiry, then loads that user from MongoDB.

Set `JWT_SECRET_KEY` to a private value of at least 32 bytes before starting
the application. Generate one with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Put the generated value in ignored `.env` for local development, or export it
through a deployment secret store. Shell variables override `.env` values.
Do not commit the key or put it in examples. `JWT_EXPIRE_MINUTES` defaults to
30 and must be a positive integer. Changing the secret invalidates existing
tokens.

## Register

`POST /auth/register` accepts JSON with `email`, `name`, and `password`.
Email is stripped and lowercased; a duplicate email returns 409. Passwords
must be 12–128 characters and contain at least one letter and one digit.
Passwords are hashed using pwdlib's Argon2id hasher.

```http
POST /auth/register
Content-Type: application/json

{"email":"engineer@example.invalid","name":"Example Engineer","password":"ExamplePass1234"}
```

Success (201) has public fields only:

```json
{
  "id": "0123456789abcdef01234567",
  "email": "engineer@example.invalid",
  "name": "Example Engineer",
  "role": "support_engineer",
  "preferred_products": [],
  "created_at": "2026-01-01T00:00:00Z"
}
```

The ID and date above illustrate the response shape.

## Log in

`POST /auth/login` accepts OAuth2 password form data. Put the email in the
`username` field. Unknown users, wrong passwords, and disabled or malformed
hashes all return the same 401 response. The 10 seeded synthetic accounts use
`disabled:sha256:` markers and cannot log in.

```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=engineer%40example.invalid&password=ExamplePass1234
```

Success (200):

```json
{"access_token":"<JWT access token>","token_type":"bearer"}
```

Swagger UI at `/docs` uses this login endpoint for its **Authorize** button.

## Read and update your profile

Send `Authorization: Bearer <JWT access token>` on both routes. Missing,
invalid, or expired tokens return 401.

`GET /users/me` returns the same public fields as registration. `PATCH
/users/me` accepts only `name` and `preferred_products` and returns the
updated public profile:

```http
PATCH /users/me
Authorization: Bearer <JWT access token>
Content-Type: application/json

{"name":"Example Support Engineer","preferred_products":["PostgreSQL","Kubernetes"]}
```

Unknown fields, including `id`, `email`, `role`, `password_hash`, and
`created_at`, are rejected with 422. Profile values cannot be null. These
routes update only the authenticated user's document.
