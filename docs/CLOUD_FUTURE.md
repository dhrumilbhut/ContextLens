# Cloud Future

This document describes exactly how ContextLens transitions from a self-hosted
single-user tool to a cloud multi-user SaaS — without rewriting the core.

The self-hosted architecture was designed with this migration in mind.
Every decision in `DECISIONS.md` accounts for it.

---

## The Core Principle

> The pipeline doesn't change. We add an identity layer on top.

The attribution pipeline (SDK → ingest → worker → Postgres → dashboard) is identical
in both versions. What changes is:

1. Who can access what (auth + ownership)
2. Where the service runs (deployment)
3. Who pays for LLM calls (billing)
4. How developers find the service (a URL instead of localhost)

---

## What Gets Added (In Order)

### Step 1: User Accounts + Auth System

Add the full auth system described in `AUTH.md` (cloud section).

**New tables via Alembic migration:**
```sql
-- 0002_add_users_auth.py

CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE,
  hashed_password TEXT NOT NULL,
  verified        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE email_verification_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE password_reset_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE refresh_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**New routes:**
```
POST /auth/signup
POST /auth/verify
POST /auth/login
POST /auth/refresh
POST /auth/logout
POST /auth/forgot-password
POST /auth/reset-password
```

**Dashboard changes:**
- Add login page (`/login`)
- Add signup page (`/signup`)
- Add email verification page (`/verify`)
- Add auth context (JWT in memory, refresh token in httpOnly cookie)
- Add auto-refresh logic (refresh access token every 14 minutes)

---

### Step 2: Project Ownership

Attach projects to users.

```sql
-- 0003_add_project_ownership.py

ALTER TABLE projects ADD COLUMN user_id UUID REFERENCES users(id);

-- assign existing projects to a seeded admin user
-- (for anyone migrating from self-hosted to cloud)
UPDATE projects SET user_id = (SELECT id FROM users LIMIT 1);

ALTER TABLE projects ALTER COLUMN user_id SET NOT NULL;
```

**Management route changes:**
Every management route gets a `get_current_user` dependency and an ownership check:

```python
# before (self-hosted)
@router.get("/projects/{project_id}/traces")
async def get_traces(project_id: str):
    return await trace_service.get_traces(project_id)

# after (cloud)
@router.get("/projects/{project_id}/traces")
async def get_traces(
    project_id: str,
    current_user: User = Depends(get_current_user)   # ← added
):
    project = await project_service.get_project(project_id)
    if project.user_id != current_user.id:            # ← added
        raise HTTPException(403, "Access denied")
    return await trace_service.get_traces(project_id)
```

The route handler body barely changes. Auth is in the dependency.

---

### Step 3: Per-User API Keys

The current `api_keys` table already has `project_id` as the foreign key.
No schema change needed for this.

**Behavioral change:**
The ingest route's key validation currently checks against a single `.env` value.
In the cloud version, it looks up the hash in the `api_keys` table — which it
was already designed to do (see `AUTH.md`).

```python
# self-hosted (current)
async def validate_local_api_key(authorization: str = Header(...)):
    key = authorization.split(" ")[1]
    if key != settings.LOCAL_API_KEY:
        raise HTTPException(401, "Invalid API key")

# cloud (replacement)
async def validate_api_key(authorization: str = Header(...)):
    raw_key = authorization.split(" ")[1]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key_record = await db.get_api_key_by_hash(key_hash)
    if not api_key_record or api_key_record.revoked_at:
        raise HTTPException(401, "Invalid API key")
    return await db.get_project(api_key_record.project_id)
```

One function swap. The SDK doesn't change at all.

---

### Step 4: Usage Metering at User Level

```sql
-- 0004_usage_per_user.py

ALTER TABLE usage_records ADD COLUMN user_id UUID REFERENCES users(id);
```

Limits move from per-project `.env` config to per-user plan limits:

```python
# cloud usage check
user = await db.get_user_with_plan(project.user_id)
monthly_limit = PLAN_LIMITS[user.plan]
monthly_usage = await db.get_monthly_usage(user.id)

if monthly_usage >= monthly_limit:
    # block processing (not ingestion)
    ...
```

---

### Step 5: Email Delivery

Add SendGrid for transactional emails:
- Signup verification
- Password reset
- Usage limit warnings (approaching plan limit)

```python
# services/email_service.py
import sendgrid
from sendgrid.helpers.mail import Mail

async def send_verification_email(to_email: str, token: str):
    verify_url = f"{settings.FRONTEND_URL}/verify?token={token}"
    message = Mail(
        from_email="noreply@contextlens.dev",
        to_emails=to_email,
        subject="Verify your ContextLens account",
        html_content=f'<a href="{verify_url}">Click to verify</a>'
    )
    sg = sendgrid.SendGridAPIClient(settings.SENDGRID_API_KEY)
    sg.send(message)
```

**New env vars:**
```bash
SENDGRID_API_KEY=SG.xxx
FROM_EMAIL=noreply@contextlens.dev
FRONTEND_URL=https://contextlens.dev
```

---

### Step 6: Deployment

Move from Docker Compose on localhost to a cloud hosting platform.

**Recommended: Railway**

Railway supports:
- Docker deployments from a GitHub repo
- Managed Postgres (with pgvector) — one click
- Managed Redis — one click
- Multiple services (api, worker, dashboard) from one repo
- Environment variable management
- Automatic deploys on git push

**Deployment structure:**
```
Railway project
  ├── postgres service (managed, pgvector enabled)
  ├── redis service (managed)
  ├── api service (Docker, ./backend)
  ├── worker service (Docker, ./backend, different start command)
  └── dashboard service (Docker, ./frontend)
```

All `localhost:xxxx` references in `.env` become Railway internal hostnames.
The `DATABASE_URL` and `REDIS_URL` are provided by Railway automatically.

**Alternative: Render**
Similar to Railway, slightly different pricing model.
Both work well for this architecture.

---

### Step 7: Stripe Billing (Optional)

When adding paid plans:

```sql
-- 0005_add_billing.py

ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;

CREATE TABLE billing_subscriptions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                UUID NOT NULL REFERENCES users(id),
  stripe_subscription_id TEXT NOT NULL UNIQUE,
  plan                   TEXT NOT NULL,
  status                 TEXT NOT NULL,
  current_period_end     TIMESTAMPTZ NOT NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**New routes:**
```
POST /billing/create-checkout-session  → creates Stripe checkout URL
POST /billing/webhook                  → receives Stripe events (plan changes)
GET  /billing/portal                   → Stripe customer portal URL
```

**Plan enforcement:**
```python
PLAN_LIMITS = {
    "free":       10_000,   # traces/month
    "pro":        50_000,
    "team":      200_000,
    "enterprise": None
}
```

---

## Migration Timeline (Estimate)

If starting from a complete self-hosted v1:

| Step | Estimated Time |
|------|---------------|
| Step 1: Auth system | 1 week |
| Step 2: Project ownership | 1–2 days |
| Step 3: Per-user API keys | 1 day |
| Step 4: Usage at user level | 1 day |
| Step 5: Email delivery | 1–2 days |
| Step 6: Deployment | 2–3 days |
| Step 7: Stripe billing | 1 week |

**Total: ~3–4 weeks to go from self-hosted v1 to cloud SaaS.**

The reason it's this fast: the core (pipeline, data model, API routes)
doesn't change. We're adding a layer, not rebuilding.

---

## What Doesn't Change

This is worth stating explicitly so it's clear how stable the foundation is:

| Component | Changes? |
|-----------|---------|
| Attribution pipeline | ✗ No change |
| Celery worker tasks | ✗ No change |
| pgvector schema (core tables) | ✗ No change |
| SDK (Python package) | ✗ No change |
| Management API route handlers (body) | Minor (ownership check added) |
| Ingest API validation | Minor (lookup strategy changes) |
| Dashboard views (trace, cluster, documents) | ✗ No change |
| Docker Compose (local dev) | ✗ Still works for local development |

---

## Keeping Self-Hosted Option After Cloud Launch

The best developer tools offer both.
Langfuse does this: free cloud tier + self-hosted via Docker Compose.

When the cloud version launches, the self-hosted version continues to work.
The `docker-compose.yml` remains the self-hosted installation.
The cloud version runs the same code on Railway.

The difference from the user's perspective:
- Self-hosted: `docker-compose up`, their data, their LLM key, zero cost
- Cloud: sign up at contextlens.dev, managed hosting, LLM cost included in plan

Both use the same SDK. Same API. Same dashboard.
Only the `CONTEXTLENS_API_URL` in the developer's `.env` differs.
ENDOFFILE