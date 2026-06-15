# Auth

This document explains the authentication model for ContextLens.

Because ContextLens is self-hosted and single-user, the auth system is
intentionally minimal. This document also covers exactly what gets added
when a cloud/multi-user version is built later.

---

## Current Model: Self-Hosted (Single User)

There are two communication channels that need some form of identity:

```
SDK → FastAPI ingest API       uses a local API key
Dashboard → FastAPI management API   no auth (localhost assumption)
```

That's it. No accounts. No login. No sessions. No JWT.

---

## Channel 1: SDK → Ingest API (Local API Key)

The SDK sends traces to `POST /ingest`. We use a simple shared secret
defined in `.env` to prevent accidental requests from other local services.

**Two env var names, same value:**

| Env var | Where it lives | Used by |
|---|---|---|
| `CONTEXTLENS_LOCAL_API_KEY` | ContextLens `.env` (server side) | FastAPI validates incoming requests against this |
| `CONTEXTLENS_API_KEY` | Developer's RAG app `.env` (client side) | SDK sends this as `Authorization: Bearer` header |

Both must be set to the same string. The different names exist because they live in different `.env` files on potentially different machines.

```bash
# ContextLens .env (server side)
CONTEXTLENS_LOCAL_API_KEY=local_dev_key_change_me
```

```bash
# developer's RAG app .env (client side)
CONTEXTLENS_API_KEY=local_dev_key_change_me
CONTEXTLENS_API_URL=http://localhost:8000
```

**Validation in FastAPI:**

```python
from fastapi import Header, HTTPException
from app.config import settings

async def validate_local_api_key(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")

    key = authorization.split(" ")[1]

    if key != settings.LOCAL_API_KEY:
        raise HTTPException(401, "Invalid API key")
```

**Why have any key at all on localhost?**

Three reasons:
1. Prevents accidental trace ingestion if another local service hits the same port
2. Keeps the ingest route shape identical to what it will be in a cloud version
   (same header, same validation pattern — just a different backend lookup)
3. Makes it obvious to developers that they need to configure the key,
   which teaches good credential hygiene

---

## Channel 2: Dashboard → Management API (No Auth)

The dashboard at `localhost:3000` calls the management API at `localhost:8000`.
No authentication is required on these routes.

**Why no auth for the dashboard?**

If someone has access to `localhost:3000` on your machine, they already have
access to your machine. Adding a login screen would protect against nothing
while adding friction and build time. For a single-user local tool, localhost
access is the authorization.

**Practical implication:**

All management routes are open when running locally:

```
GET /projects          → no auth header needed
GET /traces            → no auth header needed
GET /clusters          → no auth header needed
```

In the cloud version, every one of these routes gets a JWT validation
dependency added — but the route handlers themselves don't change.

---

## Future: Cloud / Multi-User Auth

When adding a cloud version, the full auth system gets layered on.
Nothing in the current architecture breaks — we're adding a layer, not rewriting.

Here is exactly what gets built:

### New Tables

```sql
-- user accounts
users (id, email, hashed_password, verified, created_at)

-- email verification
email_verification_tokens (id, user_id, token_hash, expires_at)

-- password reset
password_reset_tokens (id, user_id, token_hash, expires_at, used_at)

-- stay-logged-in sessions
refresh_tokens (id, user_id, token_hash, expires_at, revoked_at)
```

### New Auth Routes

```
POST /auth/signup          create account, send verification email
POST /auth/verify          verify email with token from email
POST /auth/login           validate credentials, return JWT + refresh token
POST /auth/refresh         exchange refresh token for new access token
POST /auth/logout          revoke refresh token
POST /auth/forgot-password send reset email
POST /auth/reset-password  set new password with token from email
```

### Token System (Two Tokens)

**Access token** — short-lived JWT (15 minutes):
```json
{
  "user_id": "usr_abc123",
  "email": "alice@company.com",
  "exp": 1234567890
}
```
Stored in memory in the browser (not localStorage — XSS safety).
Sent as `Authorization: Bearer <token>` on every API request.

**Refresh token** — long-lived (30 days):
Stored in an httpOnly cookie (JavaScript cannot read it — XSS attacks cannot steal it).
Used only to get a new access token when the current one expires.
Stored as a hash in the database — can be revoked server-side.

**Why two tokens?**
If an access token is stolen, it expires in 15 minutes.
If a refresh token is stolen, we can revoke it in the database.
Together: short blast radius for theft + server-side revocation capability.

### Password Storage

```python
import bcrypt

# on signup
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))

# on login
is_valid = bcrypt.checkpw(password.encode(), hashed)
```

bcrypt is intentionally slow (2^12 iterations) — makes brute force impractical.
Never use MD5 / SHA256 for passwords — they're too fast.

### API Key Changes for Cloud

In the cloud version, API keys are per-project, per-user, stored as hashes:

```sql
api_keys (
  id, project_id, key_hash, key_prefix,
  name, last_used_at, revoked_at, created_at
)
```

The raw key is shown once at creation and never stored.
Validation hashes the incoming key and compares to stored hash.
Multiple keys per project allow zero-downtime rotation.

### Management Route Auth Changes

Every management route gets a `get_current_user` dependency:

```python
# self-hosted (now)
@router.get("/traces")
async def get_traces(project_id: str):
    return await db.get_traces(project_id)

# cloud (later) — same handler, auth dependency added
@router.get("/traces")
async def get_traces(
    project_id: str,
    current_user: User = Depends(get_current_user)  ← this line added
):
    # verify ownership
    project = await db.get_project(project_id)
    if project.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return await db.get_traces(project_id)
```

The route handler body barely changes. The auth is in the dependency.

---

## Summary

| Feature                  | Self-Hosted (now) | Cloud (later)         |
|--------------------------|-------------------|-----------------------|
| Dashboard login          | None (localhost)  | Email + password      |
| Session management       | None              | JWT + refresh tokens  |
| Ingest auth              | Single .env key   | Per-project API keys  |
| Password storage         | N/A               | bcrypt                |
| Email verification       | N/A               | SendGrid              |
| Password reset           | N/A               | Token via email       |
| Multi-user isolation     | N/A               | user_id scoping       |
