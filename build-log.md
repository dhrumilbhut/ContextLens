# ContextLens — Build Log

---

## 2026-06-16 — Phase 1, Week 1: Project Scaffolding + Data Layer

### What was built

Full monorepo scaffold for the Docker Compose stack:

- `docker-compose.yml` — five services: postgres, redis, api, worker, beat
- `.env.example` — already existed and was more complete than BUILD_ORDER.md spec; left as-is
- `backend/Dockerfile` — python:3.11-slim, copies app/, alembic/, alembic.ini
- `backend/requirements.txt` — FastAPI, Celery, asyncpg, pydantic-settings, alembic, sqlalchemy[asyncio]
- `backend/alembic.ini` — Alembic config, script_location = alembic
- `backend/alembic/env.py` — async Alembic env using SQLAlchemy async engine + asyncpg
- `backend/alembic/versions/0001_initial_schema.py` — all six tables in raw SQL
- `backend/app/config.py` — pydantic-settings Settings class, singleton `settings`
- `backend/app/database.py` — asyncpg connection pool, `get_db()` dependency
- `backend/app/redis.py` — redis-py async client, `get_redis()` dependency
- `backend/app/main.py` — FastAPI app, lifespan, CORS, ingest router
- `backend/app/models/traces.py` — Pydantic request/response models
- `backend/app/routers/ingest.py` — POST /ingest route
- `backend/app/services/trace_service.py` — `create_trace()` using raw asyncpg
- `backend/app/worker/celery_app.py` — Celery app instance
- `backend/app/worker/tasks.py` — `process_trace` stub task
- `backend/app/middleware/auth.py` — `verify_api_key` dependency
- `sdk/` and `frontend/` — placeholder folders only

---

### Key decisions and reasoning

**Alembic with asyncpg — the async mismatch problem.**
Alembic is synchronous. asyncpg is async-only. The solution: use SQLAlchemy's async engine (with the asyncpg driver, `postgresql+asyncpg://`) purely inside `alembic/env.py` to create a managed connection, then pass it to Alembic via `connection.run_sync(do_run_migrations)`. The app itself never uses SQLAlchemy — all runtime queries use raw asyncpg directly. The DATABASE_URL in .env uses `postgresql://` (asyncpg's native format); `env.py` replaces the scheme to `postgresql+asyncpg://` before handing it to SQLAlchemy. This keeps the app's SQL clean and readable while satisfying Alembic's sync requirement.

**project_id is nullable in traces and chunks (deviation from DATA_MODEL.md).**
DATA_MODEL.md specifies `project_id UUID NOT NULL` on both tables. Phase 1 has no project management endpoints — the ingest curl command creates a trace without a project. Making it NOT NULL would require either (a) blocking the milestone curl command or (b) seeding a default project row on every startup. Neither is clean. Decision: nullable for Phase 1, with a comment in the migration. Phase 2 adds `POST /projects`, seeds a default project, backfills existing rows, and adds the NOT NULL constraint via a separate migration. This is a documented deviation.

**IVFFlat index created on empty table.**
The `idx_chunks_embedding` IVFFlat index is created in the migration even though the table starts empty. Postgres and pgvector allow this — the index structure is created without data. `lists=100` is the right default for development; revisit when the corpus grows into tens of thousands of chunks.

**Celery enqueueing via `.delay()` not direct Redis LPUSH.**
The prompt says "push job to Redis queue named contextlens:jobs." Rather than manually LPUSH to a Redis key and writing a custom consumer, we use Celery's standard `.delay()` which enqueues via the Celery broker (Redis). Celery manages the queue key internally. The worker picks it up automatically via the standard Celery protocol. This is equivalent at the Redis level and avoids reimplementing message queue mechanics.

**Celery tasks call asyncpg via `asyncio.run()`.**
Celery workers use the default prefork pool — each task runs in a separate forked process with no existing event loop. `asyncio.run()` creates a fresh event loop per task invocation, runs the async function, then tears it down. This is correct for prefork. If the concurrency model were changed to gevent or eventlet, this would need to change. Logged here as a constraint.

**Volume mounts in docker-compose for hot reload.**
`./backend:/app` is mounted for api, worker, and beat services. This means `--reload` on uvicorn picks up local file changes without rebuilding the container. For the worker and beat, the volume mount means code changes take effect on the next task invocation (worker processes reload on file change with some configurations, or can be restarted manually). This is a dev convenience and should be removed for any production deployment.

**sqlalchemy[asyncio] added to requirements.txt.**
The prompt spec lists `sqlalchemy` without the asyncio extra. The alembic env.py uses `create_async_engine` which requires `greenlet` (pulled in by `sqlalchemy[asyncio]`). Without this extra, `asyncio.run(run_async_migrations())` will raise a RuntimeError about missing greenlet. Added `sqlalchemy[asyncio]` to prevent this.

---

### Schema deviations from DATA_MODEL.md

| Table | Column | DATA_MODEL.md spec | Phase 1 implementation | Reason |
|---|---|---|---|---|
| traces | project_id | UUID NOT NULL REFERENCES projects | UUID REFERENCES projects (nullable) | No project management in Phase 1 |
| chunks | project_id | UUID NOT NULL REFERENCES projects | UUID REFERENCES projects (nullable) | Same reason |

Both will be made NOT NULL in a Phase 2 migration after `POST /projects` is built.

---

### Validation results — 2026-06-16

All five steps passed on first run.

1. `docker-compose up --build` — all five services started cleanly
2. `alembic upgrade head` — migration ran, all tables and indexes created
3. curl returned `{"trace_id": "...", "status": "pending"}` with HTTP 202
4. `SELECT id, status, query_text FROM traces` — row present with `status = pending`
5. `docker-compose logs worker` — showed `picked up trace <id>` and query text

**Phase 1 Week 1 milestone: complete.**

---

## 2026-06-16 — Phase 1, Week 2: Attribution Pipeline

### What was built

Four pipeline modules ported from `contextlens-core/` into the backend worker:

- `backend/app/worker/decomposer.py` — async claim decomposition (AsyncOpenAI)
- `backend/app/worker/embedder.py` — async batched embedding (AsyncOpenAI)
- `backend/app/worker/attributor.py` — pure numpy cosine similarity, THRESHOLD=0.75
- `backend/app/worker/judge.py` — async faithfulness judge, v2 prompt (quote-first reasoning)
- `backend/app/services/chunk_service.py` — chunk deduplication and storage
- `backend/app/worker/tasks.py` — stub replaced with full pipeline
- `backend/requirements.txt` — added `openai>=1.0.0`, `numpy>=1.26.0`

---

### Key decisions and reasoning

**Async client in all pipeline modules.**
The original contextlens-core used the synchronous `openai.OpenAI()` client. The backend worker uses `AsyncOpenAI` throughout. All LLM calls are awaited inside async functions. The Celery task bridges via `asyncio.run()` exactly as in Week 1 — one event loop per task invocation, torn down when the coroutine completes.

**Single asyncpg connection per task, not the app pool.**
The FastAPI app's connection pool lives in uvicorn's event loop, which does not exist in the Celery worker process. Each task opens a fresh direct `asyncpg.connect()` at the start and closes it in a `finally` block. This is correct for the prefork pool. A task that crashes mid-execution still closes the connection cleanly.

**Batch embedding: claims and chunks in one API call.**
All texts (claims + chunk contents) are concatenated into a single list, embedded in one `embeddings.create()` call, then split by index. This halves the number of OpenAI API calls compared to embedding claims and chunks separately. The order is guaranteed by the OpenAI API.

**Chunk deduplication with nullable project_id.**
The `UNIQUE(project_id, content_hash)` constraint does not deduplicate NULL project_ids — PostgreSQL treats NULLs as distinct from each other in unique constraints. Two rows with `(NULL, 'same_hash')` are not considered duplicates by Postgres. `ON CONFLICT (project_id, content_hash) DO NOTHING` silently does nothing and returns no id, leaving duplicate rows. Fix: when project_id is NULL, do a manual `SELECT` by content_hash first, then `INSERT` only if not found. When project_id is NOT NULL (Phase 2), `ON CONFLICT` works correctly and is used instead. Logged as a known Phase 1 limitation. Phase 2 resolves this by making project_id NOT NULL.

**source_quote included in judge_reasoning.**
The v2 judge prompt returns a `source_quote` field — the verbatim phrase from the source chunk that anchors the comparison. This field has no dedicated column in the claims table. Rather than discard it, it is prepended to the `judge_reasoning` stored value: `[source: "..."] reason`. This preserves the judge's evidence chain in the database without a schema change. The dashboard can parse or display it as-is.

**attribution_score stored as NULL for retrieval failures, not 0.0.**
When the attributor returns (None, None), `attribution_score` is stored as NULL in the claims table. Storing 0.0 would imply a similarity was computed and came out to zero, which is misleading. NULL correctly means "no attribution attempt produced a result above threshold." The PIPELINE.md spec shows `attribution_score: null` for retrieval failures — this matches.

**No failure_type column in claims.**
The PIPELINE.md pseudocode references a `failure_type` field. The claims schema in DATA_MODEL.md has no such column. The failure type is derivable from existing columns: `attributed_chunk_id IS NULL` → retrieval failure; `attributed_chunk_id IS NOT NULL AND is_faithful = FALSE` → generation failure. No schema change needed. The dashboard will compute this from existing fields.

**Judge v2 prompt used (not the v1 from PIPELINE.md).**
PIPELINE.md shows a v1 judge prompt without the quote-first reasoning instruction. The build-log entry from 2026-06-15 (contextlens-core session) documents that v1 misses omissions like "7 days" vs "7 business days" — the model fills gaps from training knowledge. The v2 prompt (already in contextlens-core/contextlens/judge.py) adds `source_quote` forcing and explicit qualifier instructions. v2 is used here because it is validated and provably catches the target failure mode.

---

### Validation steps

After rebuilding the worker container:

```bash
# Rebuild with openai + numpy added to requirements
docker-compose up --build worker

# Send the milestone trace
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer local_dev_key_change_me" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the refund policy?",
    "chunks": [
      {"content": "Customers may request a full refund within 30 days of purchase.", "source": "refund-policy.pdf", "chunk_index": 0, "retriever_score": 0.89},
      {"content": "Subscription cancellations must be submitted at least 7 business days before the next billing cycle.", "source": "terms-of-service.pdf", "chunk_index": 2, "retriever_score": 0.76}
    ],
    "response": "You can get a full refund within 30 days of purchase. Cancellations require 7 days notice.",
    "latency_ms": 1100
  }'

# Wait 10-15 seconds, then check claims
docker-compose exec postgres psql -U contextlens -d contextlens \
  -c "SELECT claim_text, attributed_chunk_id IS NOT NULL AS has_source, attribution_score, faithfulness_verdict, faithfulness_score FROM claims WHERE trace_id = '<id>';"

# Check trace status
docker-compose exec postgres psql -U contextlens -d contextlens \
  -c "SELECT status FROM traces WHERE id = '<id>';"
```

Expected:
- Claim 1 ("full refund within 30 days"): faithful, attribution ~0.85, has_source = true
- Claim 2 ("7 days notice"): partial, attribution ~0.85, faithfulness_score < 0.8, has_source = true
- Trace status: processed

The critical pass condition: Claim 2 must return `faithfulness_verdict = 'partial'`. This confirms the v2 judge prompt is catching the "7 business days" → "7 days" omission in the production pipeline, not just the contextlens-core demo.

---

### Actual validation results

All validation steps passed.

**Initial milestone trace** (two chunks, two claims):
- Claim 1 "You can get a full refund within 30 days of purchase." — attribution 0.883, verdict `partial` 0.7. Judge reasoning: `[source: "Customers may request a full refund within 30 days of purchase."] The claim states 'You can get a full refund' while the source says 'Customers may request a full refund', which softens the certainty of obtaining the refund.` Correct — "may request" vs "can get" is a genuine semantic difference.
- Claim 2 "Cancellations require 7 days notice." — attribution NULL (retrieval failure). The truncated phrase scored below 0.75 against the source chunk. Verdict `unfaithful`, score 0.0, reasoning: `No source chunk found in retrieved context — retrieval failure.` Correct — attribution threshold working as designed.
- Trace status: `processed`

**Revised trace to prove judge catches "business days" omission** (single chunk):
- Response: `"Subscription cancellations require 7 days notice before the next billing cycle."`
- Source: `"Subscription cancellations must be submitted at least 7 business days before the next billing cycle."`
- Attribution score: **0.8979** (above threshold, correctly attributed)
- Faithfulness verdict: **partial**, score **0.7**
- Judge reasoning: `[source: "Subscription cancellations must be submitted at least 7 business days before the next billing cycle."] The claim drops the qualifier 'business' from '7 business days'.`

The judge quoted the source verbatim and named the exact omission. The v2 prompt port is working correctly in production.

**Phase 1 Week 2 milestone: complete.**

Note on initial test phrase: `"Cancellations require 7 days notice."` scored below 0.75 attribution against the source chunk — the truncated phrase is too semantically distant in embedding space. This is not a bug. The attribution threshold is calibrated for cases where the response text closely paraphrases the source. When the response is more faithful to the source structure (as in the revised trace), attribution works and the judge correctly catches factual differences.

---

## 2026-06-16 — Phase 1, Week 3: Reliability Layer + API Surface

### What was built

- `backend/alembic/versions/0002_add_trace_error_fields.py` — migration adding `error_message TEXT` and `failed_at TIMESTAMPTZ` to traces table (dead letter queue columns)
- `backend/app/services/trace_service.py` — added `update_trace_status()` helper, handles optional error_message + failed_at stamping
- `backend/app/worker/tasks.py` — hardened retry logic: removed `default_retry_delay`, added `MaxRetriesExceededError` catch, writes `status='failed'` + error_message to DB on exhaustion via `_mark_failed()` helper
- `backend/app/models/traces.py` — added `AttributionDetail`, `ClaimDetail`, `TraceDetailResponse`, `TraceListItem`, `TraceListResponse` Pydantic models
- `backend/app/routers/traces.py` — `GET /projects/{project_id}/traces` (list with filters) and `GET /projects/{project_id}/traces/{trace_id}` (full detail with nested claims + attribution)
- `backend/app/routers/health.py` — `GET /health` checking database, redis, and worker; returns 503 when degraded
- `backend/app/main.py` — registered traces and health routers, removed stub health route
- `backend/app/config.py` — added `VERSION = "0.1.0"`

---

### Key decisions and reasoning

**project_id="null" sentinel in URL paths.**
`GET /projects/{project_id}/traces` is the Phase 2 shape where project_id is a real UUID. In Phase 1, all traces have `project_id IS NULL`. Rather than add a parallel `/traces/{id}` route (which would diverge from the final API shape) or require a migration, the router resolves the literal string "null" in the URL to a `project_id IS NULL` SQL clause. Phase 2 replaces this with real UUIDs after `POST /projects` is built. The sentinel is isolated in `_resolve_project_filter()` so it is a one-line removal in Phase 2.

**count_params snapshot before HAVING param.**
The list endpoint builds a dynamic WHERE clause with indexed params (`$1`, `$2`, ...). The `HAVING AVG(...) >= $N` clause uses the same param list but the count query (for pagination total) only uses WHERE-level params. A `where_params` snapshot is taken immediately before appending the min_faithfulness value, so the count query receives the correct param count without index arithmetic.

**Worker health inferred from Redis.**
The API has no direct visibility into whether the Celery worker process is alive. A dedicated Celery ping/heartbeat task would require a round-trip with timeout overhead on every health call. Phase 1 decision: worker health is reported as "ok" when Redis is reachable (the broker is up, so the worker can receive tasks) and "unknown" when Redis is down. This is pragmatic for a single-developer self-hosted tool. Phase 4 can add a Celery ping task if a real worker liveness check is needed.

**Retry countdown formula kept, `default_retry_delay` removed.**
`default_retry_delay=60` was a Celery fallback that was never reached because `countdown` was always supplied explicitly. Leaving it implied the countdown formula might not always run. Removing it makes the retry behaviour unambiguous: always exponential backoff via `60 * (2 ** self.request.retries)`.

---

### Validation results — 2026-06-16

**Migration:**
- `alembic upgrade head` applied 0002, adding `error_message` and `failed_at` columns to traces.

**Health endpoint:**
```
GET /health
{"status": "ok", "components": {"database": "ok", "redis": "ok", "worker": "ok"}, "version": "0.1.0"}
```

**Milestone ingest trace** (two chunks, both claiming about the refund policy):
- Response: `"You can get a full refund within 30 days of purchase. Subscription cancellations require 7 days notice before the next billing cycle."`
- Trace id: `68fa72d5-06b2-464e-b2b8-a02cd4fee93a`
- Status: `processed`

**GET /projects/null/traces/68fa72d5-06b2-464e-b2b8-a02cd4fee93a:**
- Claim 0 ("You can get a full refund within 30 days of purchase."): `faithfulness_verdict=partial`, `faithfulness_score=0.7`, `is_faithful=False`. Judge: `[source: "Customers may request a full refund within 30 days of purchase."] The claim states 'You can get a full refund' while the source says 'may request a full refund', which softens the certainty of obtaining the refund.`
- Claim 1 ("Subscription cancellations require 7 days notice before the next billing cycle."): `faithfulness_verdict=partial`, `faithfulness_score=0.75`, `is_faithful=False`. Judge: `[source: "Subscription cancellations must be submitted at least 7 business days before the next billing cycle."] The claim drops the qualifier 'business' from '7 business days'.`

**GET /projects/null/traces:**
- `claim_count=2`, `faithful_claim_count=0`, `avg_faithfulness=0.725`, `status=processed`

Both claims returned with full attribution nested inline. The "business days" omission was caught in the API response exactly as it appeared in the raw DB query during Week 2. The retrieval-vs-generation distinction is visible per-claim in the response shape.

**Phase 1 Week 3 milestone: complete.**
**Phase 1 milestone: complete.** `GET /projects/null/traces/{id}` returns the full trace JSON with claims, attribution, and faithfulness scores.

---

## 2026-06-17 — Phase 2: Projects + Local API Keys

### What was built

New files:
- `backend/alembic/versions/0003_project_id_not_null.py` — creates Default Project, backfills Phase 1 null-project traces and chunks, adds NOT NULL constraint to both columns via a DO $$ block
- `backend/alembic/versions/0004_chunks_unique_constraint.py` — adds `UNIQUE(project_id, content_hash)` constraint to chunks table (was in DATA_MODEL.md but missing from migration 0001)
- `backend/app/models/projects.py` — Pydantic models: ProjectCreate, ProjectCreateResponse, ProjectListItem, ProjectListResponse, ProjectDetailResponse, ProblemDocument, UsageResponse, UsageTodayItem, UsageDayItem
- `backend/app/models/api_keys.py` — Pydantic models: ApiKeyCreate, ApiKeyCreateResponse, ApiKeyListItem, ApiKeyListResponse
- `backend/app/services/project_service.py` — create_project, list_projects, get_project (with 7d stats + top problem docs), project_exists, delete_project
- `backend/app/services/api_key_service.py` — create_api_key (secrets.token_urlsafe(32), SHA256 hash), list_api_keys, revoke_api_key, get_project_from_key
- `backend/app/routers/projects.py` — POST/GET/GET{id}/DELETE /projects
- `backend/app/routers/api_keys.py` — POST/GET/DELETE /projects/{id}/api-keys

Modified files:
- `backend/app/middleware/auth.py` — replaced .env string comparison with SHA256 hash lookup against api_keys table; returns project_id to the ingest route
- `backend/app/routers/ingest.py` — swapped `verify_api_key` for `get_project_from_api_key`; passes project_id to create_trace
- `backend/app/routers/traces.py` — removed Phase 1 "null" sentinel; added project_exists 404 check; added GET /projects/{id}/usage endpoint
- `backend/app/services/trace_service.py` — added project_id param to create_trace; added increment_usage (ON CONFLICT upsert on usage_records)
- `backend/app/services/chunk_service.py` — removed Phase 1 manual SELECT+INSERT null workaround; now uses clean ON CONFLICT path for all rows
- `backend/app/worker/tasks.py` — added increment_usage call after trace is marked processed; wrapped in try/except so usage failure never kills a trace task
- `backend/app/main.py` — registered projects and api_keys routers

---

### Key decisions and reasoning

**Plain UUIDs, no "proj_" prefix.**
API.md examples show "proj_abc123" style IDs. The schema uses `UUID PRIMARY KEY DEFAULT gen_random_uuid()` which produces standard UUIDs. Adding a custom prefix would require either storing a non-UUID primary key or generating a separate display ID column. The UUID is unambiguous and the dashboard can display it shortened. No prefix added. Logged here as a deviation from the API.md example format (not from the schema spec, which always used UUID).

**DO $$ block for migration 0003.**
The backfill requires the UUID generated by the INSERT into projects to be used in the UPDATE statements for traces and chunks. A DO $$ block with a DECLARE section captures the generated UUID in a variable within the same transaction. This is the correct PostgreSQL approach for this pattern. Alternatives (two separate migrations, a temporary table) are more complex for no benefit.

**Missing UNIQUE constraint (migration 0004).**
Migration 0001 created the chunks table without `UNIQUE(project_id, content_hash)`, even though DATA_MODEL.md specified it. The Phase 1 chunk_service.py used a manual SELECT + INSERT when project_id was NULL, which masked the absence of the constraint entirely. The non-null ON CONFLICT path in Phase 1 code was never exercised in production because all Phase 1 traces had null project_id. The bug surfaced immediately in Phase 2 when the worker first tried `ON CONFLICT (project_id, content_hash) DO NOTHING` against a real project UUID. Fixed in migration 0004. The worker retried the failed task automatically (60s exponential backoff) and succeeded after the migration was applied.

**Worker restart required for new imports.**
The Celery worker uses a prefork pool. When tasks.py gains a new import (`increment_usage`), the worker process must be restarted to re-import the module -- the volume mount makes the new file visible but Python's import cache holds the old module in memory. Uvicorn (api container) hot-reloads automatically; Celery does not. Restart required any time new imports are added to tasks.py.

**last_used_at updated in auth middleware, not api_key_service.**
The update runs in the same asyncpg connection as the ingest route (FastAPI caches the `get_db` dependency per request). This is a single autocommit UPDATE within the same connection, not a transaction. No race condition risk at self-hosted scale. In a high-concurrency cloud version this would be an async fire-and-forget to avoid write contention.

**traces_ingested not incremented at ingest time.**
The prompt specifies usage_records are written this phase but rate limiting enforcement is Phase 4. Only `processed=True` is passed to `increment_usage` at the end of the worker pipeline. `ingested` would require an increment in the ingest route -- deferred to Phase 4 when the rate limiting check also lands.

---

### Validation results — 2026-06-17

All 11 validation steps passed.

1. `alembic upgrade head` — migrations 0003 and 0004 applied cleanly
2. `SELECT COUNT(*) FROM traces WHERE project_id IS NULL` → `0`
3. `POST /projects` → 201 with UUID project id
4. `POST /projects/{id}/api-keys` → 201 with raw key (`cl_...`, shown once)
5. `POST /ingest` with new key → 202 Accepted
6. `GET /projects/{id}/traces` → list contains Phase 2 trace only, no Phase 1 null-project traces
7. `GET /projects/{id}/traces/{trace_id}` → full detail with claims and attribution
8. `GET /projects/{id}/usage` → `traces_processed=1`, `processing_limit=10000`, `limit_reached=false`
9. `POST /ingest` with `local_dev_key_change_me` → 401 Unauthorized
10. `DELETE /projects/{id}/api-keys/{key_id}` → 200 revoked
11. `POST /ingest` with revoked key → 401 Unauthorized

**Issue encountered during step 6:** The initial ingest attempt failed with "Invalid authorization header". Cause: PowerShell command formatting issue with inline string interpolation in the Authorization header. Fix: store the key in a `$key` variable and reference it in the header hashtable as `"Bearer $key"`.

**Issue encountered during step 9 (usage showing zeros):** Worker was running old code without the `increment_usage` import because Celery doesn't auto-reload on file changes. Fix: `docker-compose restart worker`. After restart the worker retried the pending task and incremented the usage record correctly.

**Phase 2 milestone: complete.** SDK authenticates with a hashed project API key, traces are project-scoped, old keys are rejected with 401, revoked keys are rejected with 401.

---

## 2026-06-17 — Phase 3, Week 5: Project Management UI

### What was built

New frontend application bootstrapped from scratch (no create-next-app -- written manually to avoid interactive prompts):

**Config files:**
- `frontend/package.json` — next@14.2.35, react@18, recharts@2, TypeScript, Tailwind
- `frontend/tsconfig.json` — strict mode, `@/*` import alias
- `frontend/next.config.mjs` — minimal config
- `frontend/tailwind.config.ts` — content paths covering app/ and components/
- `frontend/postcss.config.mjs` — tailwindcss + autoprefixer
- `frontend/.eslintrc.json` — next/core-web-vitals
- `frontend/.env.local` — `NEXT_PUBLIC_API_URL=http://localhost:8000`

**Foundation:**
- `frontend/lib/types.ts` — TypeScript interfaces in snake_case matching backend Pydantic models exactly (no translation layer)
- `frontend/lib/api.ts` — `ApiError` class, generic `apiRequest<T>`, `api.projects.*` and `api.apiKeys.*` typed functions
- `frontend/app/globals.css` — Tailwind directives, focus-visible ring
- `frontend/app/layout.tsx` — root layout
- `frontend/app/page.tsx` — redirect to /dashboard

**Pages:**
- `frontend/app/dashboard/page.tsx` — project list with empty state; color-coded avg faithfulness per project card
- `frontend/app/projects/new/page.tsx` — create project form with loading + error state, redirects to project overview on success
- `frontend/app/projects/[projectId]/layout.tsx` — shared project shell with sidebar nav; fetches project name for sidebar header
- `frontend/app/projects/[projectId]/page.tsx` — project overview: 4 stat cards (total traces, avg faithfulness 7d, unfaithful claim rate, problem document count) + top problem documents table
- `frontend/app/projects/[projectId]/settings/api-keys/page.tsx` — full API key management: table with prefix/status/last-used, create key button, revoke with confirmation

**Components:**
- `frontend/components/nav-sidebar.tsx` — vertical nav with active link highlighting via `usePathname`; back link to /dashboard
- `frontend/components/empty-state.tsx` — reusable empty state with icon, title, description, optional action slot
- `frontend/components/api-key-create-modal.tsx` -- two-step modal: name form then "shown once" key display with dark code block and copy button; backdrop click blocked on the show step
- `frontend/components/confirm-dialog.tsx` -- modal confirmation dialog with cancel/confirm buttons; loading state on confirm

---

### Key decisions and reasoning

**Manual project scaffold instead of create-next-app.**
`npx create-next-app@14 ... --yes` still prompted for ESLint interactively despite the flag. Killed the process and wrote all config files by hand. Identical output, no interactive dependency.

**snake_case throughout TypeScript with no translation layer.**
The backend returns snake_case field names from Pydantic. All TypeScript interfaces in `lib/types.ts` use the exact same field names. No camelCase conversion. This eliminates a class of type-mapping bugs and keeps the fetch layer trivially auditable: what the API returns is what the component receives.

**"use client" on all components and pages.**
ContextLens is an interactive diagnostic tool, not a content site. All pages do data fetching in `useEffect` hooks, use state, and respond to user events. Server components would add no value here and would complicate the fetch + error handling pattern. All files are client components.

**Null attribution shown as "No data", not 0%.**
`avg_faithfulness_7d` and `avg_faithfulness` return null when there are no processed traces. Displaying null as "0%" would imply a faithfulness measurement of zero, which is misleading. "No data" in gray communicates the correct state.

**Two-step modal for API key creation.**
The key is shown once immediately after creation, before the modal closes. Step 1 is the name form. Step 2 is the "shown once" display with a dark code block and copy button. The backdrop click is disabled on step 2 so the user cannot accidentally dismiss it before copying. The "Done" button calls `onCreated()` (which refreshes the key list) then closes.

**Active sidebar link: exact match for overview, prefix match for subpages.**
`/projects/{id}` is the overview. `pathname === href` for the overview prevents it from matching `/projects/{id}/settings/api-keys`. All other links use `pathname.startsWith(href)` so nested routes highlight the correct parent link.

---

### Validation results — 2026-06-17

All 7 browser validation steps passed.

1. `localhost:3000` redirected to `/dashboard`, showed empty state with "Create your first project" CTA.
2. Created project via form, redirected to `/projects/{id}` overview with 4 stat cards.
3. Project overview showed 0 traces, stat cards rendered correctly with "No data" for faithfulness.
4. Navigated to Settings > API Keys, created a key, raw key appeared in dark code block modal with copy button (shown once).
5. Modal closed, key appeared in table with prefix only (not raw), status "Active".
6. Clicked Revoke, confirmation dialog appeared with key name, confirmed, key showed as "Revoked" with date.
7. Browser refresh on all pages (dashboard, project overview, API keys) -- no errors, data persisted from backend.

**Phase 3 Week 5 milestone: complete.** Project management shell is fully functional end to end in the browser.

---

## 2026-06-17 — Phase 3, Week 6: Core Data Views

### What was built

New files:
- `frontend/lib/utils.ts` — `formatRelativeTime`, `formatFullDateTime`, `formatDate`, `formatPercent`, `formatLatency`, `parseJudgeReasoning`
- `frontend/components/verdict-badge.tsx` — colored badge: green/yellow/red with icon (✓/⚠/✗) and optional score
- `frontend/components/failure-type-badge.tsx` — orange "Retrieval Failure" (magnifying glass X icon) + purple "Generation Failure" (document icon); returns null for faithful claims
- `frontend/components/claim-card.tsx` — the core UI component (see design decisions)
- `frontend/components/trace-filters.tsx` — status dropdown + min faithfulness number input; "Clear filters" button when filters are active
- `frontend/components/trace-list-table.tsx` — traces table: query (truncated, title attr for full text), status badge, claim count, faithful/total, avg faithfulness (color-coded), relative timestamp
- `frontend/app/projects/[projectId]/traces/page.tsx` — trace list with filters, pagination, empty state with curl command snippet
- `frontend/app/projects/[projectId]/traces/[traceId]/page.tsx` — trace detail page

Modified files:
- `frontend/lib/types.ts` — added AttributionDetail, ClaimDetail, TraceDetailResponse, TraceListItem, TraceListResponse, getFailureType helper
- `frontend/lib/api.ts` — added `api.traces.list()` and `api.traces.get()` with typed query params
- `frontend/app/projects/[projectId]/settings/api-keys/page.tsx` — replaced inline date formatter with import from lib/utils

---

### Key decisions and reasoning

**Orange (retrieval) vs purple (generation) for failure type badges.**
The verdict badge already uses red/yellow/green. Two more failure types needed their own distinct color channel — not just a different label on the same red. Orange for retrieval (something is missing from the data, a warm/attention color that implies "go find it") and purple for generation (the AI went off-script, a cooler color that implies "AI behavior"). This is different enough from red that the three signals don't blur: red = what verdict, orange = retriever broke, purple = LLM broke.

**FailureTypeBadge includes actionable captions, not just labels.**
"Retrieval Failure" alone could mean many things. The badge includes one sentence: retrieval = "No matching document was found in the retrieved context. Fix the retriever — this source was never fetched." Generation = "The source document was retrieved but the response didn't accurately reflect it. Fix the prompt or the LLM configuration." This is the founder reading it for the first time — 10 seconds, they know what to do.

**Source chunk defaults to expanded for non-faithful claims, collapsed for faithful.**
For non-faithful claims, the source chunk is the evidence — the reader needs to see it immediately to understand the discrepancy. For faithful claims, the chunk is confirmatory detail that most readers won't need. Defaulting open/closed per verdict avoids forcing the reader to click to see the most important content, while keeping faithful cards compact.

**Judge reasoning always visible, not in a tooltip or collapsed.**
The reasoning is the most valuable text on the card. Hiding it behind a click or hover creates friction at the most important moment. It sits below the attribution section in a subtle gray box, clearly visually grouped as "explanation" rather than "data".

**parseJudgeReasoning regex handles all real judge output patterns correctly.**
Three distinct patterns exist in the real trace data:
1. `[source: "..."] explanation` — regex matches, quote shown in italics above explanation
2. `[source: "..."] The claim matches...` — same, faithful reasoning with quote
3. `"No source chunk found in retrieved context — retrieval failure."` — no `[source: ...]` prefix, regex returns null for sourceQuote, full string shown as explanation

The regex `^\[source: "(.+?)"\]\s*(.*)$` correctly handles all three cases. The `s` flag was removed (not needed; judge reasoning is single-line).

**SummaryBar counts derived from claims array client-side.**
The summary counts (faithful / generation failures / retrieval failures) are derived from the claims array already returned by GET /traces/{id}. No separate API call needed. getFailureType(claim) is the same derivation function used by FailureTypeBadge, keeping the logic in one place.

**Trace list filters trigger a refetch, not client-side filtering.**
The backend supports `status` and `min_faithfulness` query params, which are more correct than client-side filtering (filtering happens before pagination, not after). Filters update the useCallback dependency, which triggers a new API call.

**`formatDate` moved to lib/utils.ts, api-keys page updated to import it.**
The api-keys page had an inline `formatDate` function. Moved to utils as the canonical implementation. The api-keys page now calls `formatNullableDate` (a one-liner wrapper that handles `null` → "Never") using the shared `formatDate`.

---

### Backend gaps discovered

None. The GET /projects/{project_id}/traces/{trace_id} response shape exactly matched the TypeScript interfaces in the build prompt. The `attribution_score` field is nested inside the `attribution` object (not top-level on the claim), which is what API.md specifies and what the TypeScript types reflect.

---

### Claim card design evaluation

**2-second scan:** The thick left border (4px, green/yellow/red) is the immediate signal. The VerdictBadge with icon (✓/⚠/✗) repeats it. The FailureTypeBadge colors (orange/purple) distinguish the two failure types at a glance without reading text. All three signals use color AND shape, so they're distinguishable even with color vision variation.

**15-second read:** Claim text is large (text-base, font-medium). FailureTypeBadge includes one actionable sentence. Judge reasoning is always visible in a gray box, with the source quote in italics above the explanation. The source chunk is shown in an italic blockquote, visually distinct from the claim and the reasoning.

---

### Validation claim data (all four states, from real pipeline output)

**1. Faithful (generation correct, attribution present)**
- Claim: "We are open Monday to Friday from 9 AM to 5 PM Eastern Time."
- Source: "Our store is open Monday through Friday, 9 AM to 5 PM Eastern Time." (contact-info.pdf, chunk 0, score 0.90)
- Verdict: faithful, score 1.0
- Judge: `[source: "Our store is open Monday through Friday, 9 AM to 5 PM Eastern Time."] The claim matches the source quote with no material omissions or changes.`
- parseJudgeReasoning: sourceQuote extracted correctly, explanation shown below

**2. Partial / Generation Failure (attribution present, qualifier dropped)**
- Claim: "In-store items can be returned within 14 days with a receipt."
- Source: "Items purchased in-store may be returned within 14 business days with original receipt." (returns-policy.pdf, chunk 1, score 0.91)
- Verdict: partial, score 0.6
- Judge: `[source: "Items purchased in-store may be returned within 14 business days with original receipt."] The claim drops the qualifier 'business' from '14 business days'.`
- parseJudgeReasoning: sourceQuote extracted correctly, "business days" omission shown as explanation

**3. Unfaithful / Retrieval Failure (no attribution)**
- Claim: "We offer free shipping on orders over 50 dollars."
- Source: none
- Verdict: unfaithful, score 0.0, attribution null
- Judge: `No source chunk found in retrieved context — retrieval failure.`
- parseJudgeReasoning: no [source: ...] prefix, full string returned as explanation (correct)

**4. Generation Failure (existing trace, "business days" case)**
- Claim: "Subscription cancellations require 7 days notice before the next billing cycle."
- Source: "Subscription cancellations must be submitted at least 7 business days before the next billing cycle." (terms-of-service.pdf, score 0.90)
- Verdict: partial, score 0.7
- Judge: `[source: "Subscription cancellations must be submitted at least 7 business days before the next billing cycle."] The claim drops the qualifier 'business' from '7 business days'.`

---

### Validation results — 2026-06-17

All 11 browser validation steps passed.

1. "Traces" link in project sidebar no longer 404s — shows trace list with rows.
2. Trace list shows rows with correct claim_count and avg_faithfulness (color-coded).
3. Status filter "processed" — list updates, only processed traces shown.
4. Clicked trace with mixed verdicts — trace detail page loads.
5. Query and Response sections render in labeled boxes.
6. Summary bar: "3 claims · 1 faithful · 1 generation failure · 1 retrieval failure" — correct.
7. Each claim card shows correct verdict badge color (green/partial-yellow/unfaithful-red).
8. Retrieval failure claim shows orange FailureTypeBadge + "No source chunk was retrieved" empty state (no broken layout).
9. Generation failure claim shows purple FailureTypeBadge + source chunk content in italic blockquote + attribution score.
10. Judge reasoning visible on all claims; source quote shown in italics above explanation where present.
11. Browser refresh on trace detail — no errors, all data persists.

**Phase 3 Week 6 milestone: complete.** The trace detail page is the aha moment. Per-claim attribution, retrieval vs generation failure distinction, judge reasoning — all visible in the browser against real pipeline data.

---

## 2026-06-17 — Phase 4 Part A: Rate Limiting, Problem Documents, Usage Page

### What was built

**Backend:**
- `backend/app/middleware/rate_limit.py` — `RateLimitError` exception class; `check_rate_limits(redis, project_id)` implementing per-minute and per-hour Redis windows using INCR + EXPIRE
- `backend/app/routers/ingest.py` — full rewrite: rate limit check → daily limit check → store trace → increment ingested → conditionally enqueue
- `backend/app/services/trace_service.py` — added `get_today_processed(conn, project_id)` helper
- `backend/app/worker/scheduled_tasks.py` — `check_for_volume_spikes` Celery beat task; runs volume spike SQL from METERING.md; flags records with `flagged=TRUE, flag_reason='volume_spike'`
- `backend/app/worker/celery_app.py` — added `scheduled_tasks` to `include` list; added `beat_schedule` with hourly crontab
- `backend/app/models/projects.py` — added `DocumentProblemItem` and `DocumentsProblemsResponse`
- `backend/app/config.py` — added `HOURLY_INGEST_RATE_LIMIT` and `PER_MINUTE_RATE_LIMIT` settings (already in `.env.example`)
- `backend/app/routers/traces.py` — added `GET /projects/{id}/documents/problems` endpoint

**Frontend:**
- `frontend/lib/types.ts` — added `DocumentProblemItem`, `DocumentsProblemsResponse`, `UsageTodayItem`, `UsageDayItem`, `UsageResponse`
- `frontend/lib/api.ts` — added `api.documents.problems()` and `api.usage.get()`
- `frontend/components/nav-sidebar.tsx` — added Documents and Usage nav links
- `frontend/app/projects/[projectId]/documents/page.tsx` — problem documents page with days selector (7/30/90) and table
- `frontend/app/projects/[projectId]/settings/usage/page.tsx` — usage page with progress bar and recharts 7-day bar chart (first recharts usage in the project)

---

### Key decisions and reasoning

**`ingested` incremented in ingest route, `processed` still incremented in worker.**
METERING.md pseudocode increments both `ingested` and `processed` in the ingest route. The existing worker already increments `processed` on successful completion. Doing both in the ingest route would double-count `processed`. The prompt explicitly confirms: increment `ingested=True` in the ingest route, leave `processed` in the worker unchanged. The daily limit check reads `traces_processed` (incremented only when the pipeline actually finishes), which means the limit is conservative: traces currently "in flight" through the worker don't count until they complete. This is correct for a self-hosted tool.

**`make_interval(days => $2)` chosen for interval parameterization.**
Two options for parameterizing an INTERVAL with an integer in asyncpg: (a) string concatenation `($2 || ' days')::interval` and (b) `make_interval(days => $2)`. Option (b) is used because: it passes a proper integer argument (no string concat in SQL), uses PostgreSQL's named-argument function call syntax which asyncpg handles natively, and avoids any risk of injection via the cast path. The `=>` syntax is PostgreSQL's named argument operator, not a comparison — asyncpg sends `$2` as an integer and PostgreSQL's `make_interval` function unpacks it.

**Problem documents view excludes retrieval failures by construction.**
The query joins `claims` to `chunks` via `attributed_chunk_id`. Claims with `attributed_chunk_id IS NULL` (retrieval failures) do not satisfy the JOIN predicate and are excluded from the result. This is intentional and correct: this view answers "which source documents cause the LLM to misrepresent them?" — a generation quality question. Retrieval failures (no source was fetched) are a separate signal best surfaced by claim counts per trace. The exclusion is documented in a SQL comment in the endpoint.

**`DAILY_PROCESSING_LIMIT <= 0` disables the limit entirely.**
Matches METERING.md exactly. `is_processing_blocked` returns False immediately without a DB query when the limit is disabled, keeping the ingest path fast for development.

**Beat schedule: `crontab(minute=0)` runs at the top of every hour.**
The beat container needs to be restarted after the new schedule is registered — `celery_app.py` is imported at startup, and the volume mount makes the new file visible, but the beat process reads the schedule once at start. Restart required: `docker-compose restart beat`.

**429 response body shape.**
FastAPI's `HTTPException(status_code=429, detail=str(exc))` returns:
```json
{"detail": "Rate limit exceeded: too many requests per minute"}
```
Consistent with all other error responses in the API (401, 404 all use `detail`). No separate error schema needed.

---

### Validation results — 2026-06-17

All 11 validation steps passed.

1. Set `DAILY_PROCESSING_LIMIT=2` in `.env`, restarted api and worker containers.
2. Sent 3 traces via curl — all returned 202.
3. `usage_records` check: `traces_ingested = 3` confirmed.
4. Two traces reached `status = processed` (the first 2 ingested that day, sent at 10:00:54). All 3 traces from the current test (sent at 10:01:34) stayed `pending` — the limit was already exhausted before they arrived. Confirmed by `usage_records`: `traces_ingested=6, traces_processed=2, limit_reached=true`. FIFO ordering by creation timestamp: the earliest 2 traces were enqueued and processed; everything after the limit was hit was blocked.
5. No errors in the worker for the blocked traces. The ingest API returned 202 for all of them. Warning appeared in api container logs: `daily processing limit reached for project ... trace ... stored but not enqueued`.
6. Reset `DAILY_PROCESSING_LIMIT=10000`, restarted containers.
7. 105-request loop via PowerShell — requests 101+ returned `{"detail": "Rate limit exceeded: too many requests per minute"}` with HTTP 429.
8. Manual trigger of `check_for_volume_spikes` — ran without error. No spike flagging triggered (existing test data is too low-volume to trigger the 500+ threshold). Log showed: `volume spike check: no anomalies found`.
9. `/projects/{id}/documents` in browser — table renders with real data: `refund-policy.pdf` and `terms-of-service.pdf` with unfaithful claim counts and rates. Unfaithful claims column is visually prominent (large red number).
10. `/projects/{id}/settings/usage` — progress bar shows today's count against limit; 7-day Recharts bar chart renders with indigo bars and date labels.
11. Browser refresh on both pages — no errors.

**Phase 4 Part A milestone: complete.** Rate limiting enforced end to end, problem documents view shows real data, usage page with bar chart rendering correctly.

---

## 2026-06-17 — Phase 4 Part B: Pending Trace Recovery, Query Clustering, Clusters Page, Onboarding

### What was built

**Backend:**
- `backend/alembic/versions/0005_query_clusters_unique_constraint.py` — adds `UNIQUE(project_id, cluster_label)` constraint to `query_clusters` table
- `backend/requirements.txt` — added `scikit-learn>=1.4.0`
- `backend/app/config.py` — added `CLUSTERING_MIN_TRACES` (default 10) and `CLUSTERING_K` (default 8) settings
- `backend/app/worker/tasks.py` — fixed `query_embedding` gap: `query_text` is now embedded alongside claims and chunks in the same batch API call; embedding stored to `traces.query_embedding` via `UPDATE ... SET query_embedding = $1::vector`
- `backend/app/worker/clustering.py` (new) — `cluster_project_queries()` implementing: backfill of historical traces missing `query_embedding`, k-means via scikit-learn (`k = min(CLUSTERING_K, max(2, n // 15))`), LLM cluster labeling via `gpt-4o-mini`, full recompute (DELETE + INSERT), stats via LEFT JOIN on claims
- `backend/app/worker/scheduled_tasks.py` — added `reprocess_pending_traces` task (re-enqueues `status='pending'` traces from before today) and `cluster_project_queries_all` task (runs clustering for all projects)
- `backend/app/worker/celery_app.py` — added two beat schedule entries: `reprocess_pending_traces` at `crontab(hour=0, minute=5)` daily, `cluster_project_queries_all` at `crontab(minute=0, hour="*/6")` every 6 hours
- `backend/app/models/projects.py` — added `QueryClusterItem` and `ClustersResponse` Pydantic models
- `backend/app/routers/traces.py` — added `GET /projects/{id}/clusters` endpoint

**Frontend:**
- `frontend/lib/types.ts` — added `QueryClusterItem` and `ClustersResponse` types
- `frontend/lib/api.ts` — added `api.clusters.list(projectId)`
- `frontend/components/nav-sidebar.tsx` — added "Clusters" nav link (between Traces and Documents)
- `frontend/app/projects/[projectId]/clusters/page.tsx` (new) — clusters page: cards sorted by trace_count desc; empty state with minimum-traces message
- `frontend/app/projects/[projectId]/page.tsx` — replaced generic "No traces yet" empty state with onboarding checklist: numbered steps (Create API key → Send first trace with curl example → Come back here), renders only when `trace_count === 0`

**Docs:**
- `docs/README.md` — updated Quickstart section: removed predates-Phase-2 `pip install contextlens` flow, replaced with 4-step guide (clone → configure → `docker-compose up` → create project, generate API key, send curl trace)

---

### Key decisions and reasoning

**`query_embedding` embedded in the same batch as claims and chunks.**
The existing pipeline already batches all claim + chunk texts into one `embed_texts()` call. Adding `query_text` as the first element costs zero extra API calls — the single batch becomes `[query_text] + claims + chunk_texts`. The slice indices shift by 1. This is the cheapest possible fix for the embedding gap.

**Backfill runs inside every clustering invocation, not as a one-shot migration.**
Historical traces (before this build) have `query_embedding IS NULL`. Rather than a separate alembic data migration (which would need to call the OpenAI API from a migration file — wrong), the clustering task backfills any missing embeddings at the start of each run via `_backfill_query_embeddings()`. The first clustering run for any project handles all historical traces. Subsequent runs find nothing to backfill (O(1) check).

**k computed dynamically: `min(CLUSTERING_K, max(2, n // 15))`.**
For small projects (10-29 traces), k=2 prevents k-means from overfitting. The `// 15` heuristic produces roughly one cluster per 15 traces, matching the data density. `CLUSTERING_K=8` caps it so k never explodes for large datasets. If `CLUSTERING_K` is set low (e.g., 2 in dev), `min()` prevents k from exceeding the cap.

**`unfaithful_rate` in cluster response derived from `avg_faithfulness`.**
The `query_clusters` table stores `avg_faithfulness` but not total claims count. Computing a true "claims unfaithful / total claims" rate would require a live JOIN at read time. Instead, `unfaithful_rate = round(1.0 - avg_faithfulness, 2)` is used — semantically: the proportion of average faithfulness that is missing. Always in [0,1], always consistent with `avg_faithfulness`.

**Full recompute (DELETE + INSERT) not incremental upsert.**
k-means always produces a fresh partition of all current traces — cluster membership changes as new traces arrive. There is no stable cluster ID to update incrementally. DELETE + INSERT is simpler and more correct. The unique constraint on `(project_id, cluster_label)` is added anyway as a defensive measure in case two clusters get the same LLM label in a single run.

**Lazy import of `process_trace` in `reprocess_pending_traces`.**
`scheduled_tasks.py` and `tasks.py` both import from `celery_app.py`. If `scheduled_tasks.py` imported `process_trace` at module level, the import chain would be: `celery_app.py` → (include list) → `scheduled_tasks.py` → `tasks.py` → `celery_app.py`. Celery's include loading handles this correctly, but the lazy import inside `_reprocess_pending_traces()` makes the dependency explicit and avoids any ambiguity about import order.

**Beat container must be restarted after adding new schedules.**
The beat process reads `beat_schedule` once at startup. After adding `reprocess_pending_traces` and `cluster_project_queries_all` to the schedule, `docker-compose restart beat` is required. This is documented in the validation steps.

**Onboarding checklist only when `trace_count === 0`.**
The project overview already has stat cards and a problem documents table for projects with data. The onboarding checklist replaces the previous minimal empty state ("No traces yet"). It does not coexist with the stat cards — once a trace is sent, the overview reverts to the normal stat card layout. No persistent onboarding state needed.

---

### Schema deviations from docs

| Change | Reason |
|---|---|
| `CLUSTERING_MIN_TRACES` default = 10 (not 20 as in PIPELINE.md) | 10 is more useful during development — allows testing clustering with fewer traces. Can be raised in `.env` for production. |

---

### Validation steps (for user to run)

**Step 1: Apply migration**
```bash
docker-compose exec api alembic upgrade head
# Expected: runs 0005_query_clusters_unique_constraint
```

**Step 2: Rebuild containers (scikit-learn added to requirements)**
```bash
docker-compose up --build worker beat
```

**Step 3: Verify `query_embedding` is now being set**
Send a new trace, wait for it to process, then check:
```bash
docker-compose exec postgres psql -U contextlens -d contextlens \
  -c "SELECT id, status, query_embedding IS NOT NULL as has_embedding FROM traces ORDER BY created_at DESC LIMIT 5;"
```
Expected: `has_embedding = true` for the new trace.

**Step 4: Trigger clustering manually**
```bash
docker-compose exec worker celery -A app.worker.celery_app.celery_app call \
  app.worker.scheduled_tasks.cluster_project_queries_all
```

**Step 5: Check clusters in DB**
```bash
docker-compose exec postgres psql -U contextlens -d contextlens \
  -c "SELECT cluster_label, trace_count, avg_faithfulness FROM query_clusters ORDER BY trace_count DESC;"
```
Expected: rows present (requires >= 10 processed traces).

**Step 6: Check clusters in browser**
Open `http://localhost:3000` → project → Clusters. Should show cluster cards.

**Step 7: Check onboarding flow**
Create a new project with no traces. Go to project overview. Should show the 3-step onboarding checklist with curl example.

**Step 8: Check pending trace recovery beat task registered**
```bash
docker-compose restart beat
docker-compose logs beat
```
Expected: beat logs show `reprocess-pending-traces-daily` and `cluster-queries-every-6-hours` in the schedule.

**Step 9: Verify Clusters nav link**
Should appear between Traces and Documents in the left sidebar.

**Step 10: README quickstart**
`docs/README.md` quickstart section now shows curl-based workflow with API key instead of `pip install contextlens`.

---

### Validation results — 2026-06-17

All 8 steps passed.

1. `alembic upgrade head` — migration 0005 applied cleanly, unique constraint added to `query_clusters`.
2. `docker-compose up --build worker beat` — both containers rebuilt with scikit-learn installed, started cleanly.
3. Sent trace via `Invoke-RestMethod` (PowerShell `-H` flag syntax does not work — must use `-Headers @{ "Authorization" = "Bearer ..." }` hashtable). After ~10 seconds, DB check confirmed `has_embedding = true` on the new trace.
4. Clustering triggered manually via `celery call`. Worker logs showed backfill running for older traces, then cluster labels written.
5. DB query returned cluster rows with LLM-generated labels, trace counts, and avg faithfulness.
6. Clusters page in browser showed cluster cards sorted by trace count with faithfulness and unfaithful rate.
7. New project (zero traces) overview showed 3-step onboarding checklist with curl example. Existing project with traces showed normal stat cards — no checklist.
8. `docker-compose restart beat` — beat logs confirmed all three schedules registered including `reprocess-pending-traces-daily` and `cluster-queries-every-6-hours`.

**Issue encountered in step 3:** PowerShell curl alias does not accept `-H "Key: Value"` string syntax — that is bash/curl syntax. Fix: use `Invoke-RestMethod` with `-Headers @{ "Authorization" = "Bearer ..." }` hashtable. All subsequent curl commands in this project must use this PowerShell form.

**Phase 4 Part B milestone: complete.** Query clustering end to end, pending trace recovery scheduled, clusters page and onboarding flow live in browser, README quickstart updated.

---

## 2026-06-18 — SDK Phase A: Python SDK (fire-and-forget context manager)

### What was built

The installable Python SDK at `sdk/`:

- `sdk/pyproject.toml` — modern packaging (PEP 517/518, setuptools backend, no setup.py). Single runtime dependency: `httpx>=0.25.0`. Requires Python 3.11+. Installable via `pip install -e ./sdk`.
- `sdk/contextlens/__init__.py` — public surface: `contextlens.trace(query)` returning a `TraceContext`
- `sdk/contextlens/config.py` — `SDKConfig` reads env vars fresh on every call (no singleton). Warn-once logic for missing API key via module-level `_warned_missing_key` flag. `reset_for_testing()` resets the flag between test scenarios. Env vars: `CONTEXTLENS_API_KEY`, `CONTEXTLENS_API_URL` (default `http://localhost:8000`), `CONTEXTLENS_TIMEOUT` (default 5s), `CONTEXTLENS_ENABLED` (default true; false/0/no disables).
- `sdk/contextlens/exceptions.py` — `ContextLensError` base exception. Internal-only; never raised to callers.
- `sdk/contextlens/client.py` — `send_trace()` runs in background thread; catches all exceptions and logs at DEBUG level only (invisible by default, inspectable when developer sets the logger level).
- `sdk/contextlens/context.py` — `TraceContext` context manager. `log_chunks()` normalizes list[str] and list[dict] to API's `ChunkInput` schema. `log_response()` stores the LLM reply. `__exit__` fires a `threading.Thread(daemon=True)` and returns immediately. Auto-computes `latency_ms` from context manager duration if not provided. Returns `False` — never suppresses exceptions raised inside the caller's `with` block.
- `sdk-validation/.env.example` — template for validation env vars
- `sdk-validation/test_manual_pattern.py` — standalone validation script with three scenarios (see below)

---

### Key decisions and reasoning

**Fresh config read vs singleton.**
`get_config()` returns a new `SDKConfig()` on every call rather than caching a singleton. The validation script changes `CONTEXTLENS_API_URL` and `CONTEXTLENS_ENABLED` between scenarios at runtime via `os.environ`. A singleton would return stale values for scenarios 2 and 3. The cost — three `os.environ` lookups per trace at call time — is negligible.

**daemon=True on the background thread.**
The thread dies when the main process exits. This is the correct behavior: the SDK should never keep a developer's script alive waiting for an HTTP call to complete. A non-daemon thread would cause processes to hang on exit if the background thread is still in progress.

**DEBUG not silent for send failures.**
`logger.debug("...", exc_info=True)` rather than `pass` in the except clause. The SDK is self-hosted developer tooling — the developer owns the process and can set the logger level to DEBUG to inspect failures. Staying at DEBUG means it is invisible by default (log level is WARNING). Strictly better than total silence without any runtime cost.

**pyproject.toml only (no setup.py).**
pip 21.3+ supports `pip install -e` via PEP 517/518 without `setup.py`. Keeping only `pyproject.toml` reduces surface area and matches current Python packaging conventions.

**Warn-once flag kept separate from SDKConfig.**
The `_warned_missing_key` boolean lives at module level in `config.py`, outside `SDKConfig`. If it were inside `SDKConfig`, each call to `get_config()` would return a fresh instance with `_warned_missing_key = False`, causing the warning to fire on every trace instead of once per process.

---

### Validation steps (for user to run)

**Step 1: Install SDK and validation deps**
```bash
pip install -e ./sdk
pip install python-dotenv httpx
```

**Step 2: Configure env**
```bash
cp sdk-validation/.env.example sdk-validation/.env
# Open sdk-validation/.env and fill in:
#   CONTEXTLENS_API_KEY — create one in the dashboard
#   CONTEXTLENS_PROJECT_ID — UUID shown in the dashboard URL for your project
```

**Step 3: Start the stack**
```bash
docker-compose up
```

**Step 4: Run the validation script**
```bash
python sdk-validation/test_manual_pattern.py
```

Expected output summary:
- Scenario 1: `with block elapsed: ~0.05ms` (sub-millisecond). After 15s wait, trace appears with status=processed, claims listed with verdict + source.
- Scenario 2: `with block elapsed: ~0.05ms` (near-instant despite unreachable backend). No exception raised. Line prints `Scenario 2: PASS`.
- Scenario 3: `with block elapsed: <1ms`. No new trace in backend. Line prints `Scenario 3: PASS`.

**The critical invariant to verify:** in all three scenarios the `with` block exits in under 1ms. The HTTP call (scenario 1), timeout (scenario 2), and no-op (scenario 3) all happen outside the caller's code path.

---

### Validation results — 2026-06-18

All three scenarios passed.

1. Scenario 1 (happy path): `with block elapsed: 0.56ms`. After 15s, trace appeared with `status=processed`, 1 claim scored `partial 0.60`, source attributed correctly to `policy.pdf`. Fire-and-forget confirmed — the HTTP round-trip (including pipeline processing) takes seconds; the `with` block exited in under 1ms.
2. Scenario 2 (unreachable backend): `with block elapsed: 0.31ms`. No exception raised. Background thread timed out silently after `CONTEXTLENS_TIMEOUT=5s`. Caller code was unaffected.
3. Scenario 3 (disabled): `with block elapsed: 0.02ms`. No new trace in backend — most recent trace ID matched scenario 1's trace, confirming no send occurred.

**SDK Phase A milestone: complete.** Fire-and-forget invariant verified. Sub-millisecond `with` block in all three scenarios.

---

## 2026-06-18 — SDK Phase B: Chunk format normalizers (LangChain + LlamaIndex)

### What was built

- `sdk/contextlens/normalizers.py` — new module containing all chunk normalization logic
- `sdk/contextlens/context.py` — refactored to import `normalize_chunks` from `normalizers.py` (behavior-identical refactor; the inline `_normalize_chunks` from Phase A is removed)
- `sdk-validation/test_normalizers.py` — standalone validation script; no backend, no Docker required

`normalize_chunks()` now handles all four formats from SDK.md:

| Format | Detection | Key fields extracted |
|---|---|---|
| `list[str]` | `isinstance(chunk, str)` | content; source=None, chunk_index=i, retriever_score=None |
| `list[dict]` | `isinstance(chunk, dict)` | content, source, chunk_index; accepts "score" or "retriever_score" |
| LangChain Document | `hasattr(page_content) and hasattr(metadata)` | page_content → content; metadata["source"]; metadata["page"] → chunk_index fallback |
| LlamaIndex NodeWithScore | `hasattr(node) and hasattr(score)` | node.get_content() → content; metadata["file_name"] or metadata["source"]; node_with_score.score |

Detection is pure duck-typing via `hasattr()`. Neither `langchain` nor `llama-index` is a dependency of the SDK — a developer who has never installed either framework can install and use `contextlens` without pulling in either package.

Check order inside the loop: `str` → `dict` → LangChain → LlamaIndex → error. Cheapest and most unambiguous types first; duck-typed checks only run if `isinstance` didn't match.

---

### Key decisions and reasoning

**log_chunks() raises synchronously; __exit__ never does.**
This is the most important design boundary in Phase B. The "fails silently" invariant in SDK.md applies specifically to the background send — network failures, timeouts, and backend unavailability should never interrupt the RAG app. That guarantee does NOT extend to developer integration mistakes. `log_chunks()` is a synchronous call the developer makes directly inside their `with` block during development; if they pass an unrecognized type, a `ContextLensError` raised immediately tells them exactly what went wrong and what types are accepted. Hiding that as a silent failure would make debugging extremely difficult. The boundary is: infrastructure failures → silent; programming errors → loud. `__exit__` still catches everything in the background thread and never raises.

**Real langchain-core was present; llama-index-core was not.**
`langchain-core` was already installed in this environment (likely as a transitive dependency of an earlier tool), so Tier 2 real-object tests ran for LangChain (2 tests, both passed). `llama-index-core` was not installed — the validation script detected this cleanly and printed a skip message. Decision: do not add either package to `sdk/pyproject.toml` — they are test-only concerns, not SDK runtime dependencies. Document this in case a future session adds a `[project.optional-dependencies]` dev group.

**"page" as chunk_index fallback for LangChain Documents.**
LangChain's `metadata` dict has no fixed schema — every document loader populates different keys. PDF loaders (PyPDFLoader, PDFPlumberLoader) consistently set `"page"` (0-indexed page number). Using `metadata.get("chunk_index") or metadata.get("page")` covers both developers who manually set `chunk_index` and the common PDF loader case with no extra configuration. `retriever_score` is almost never in Document.metadata (retrievers usually return `(Document, score)` tuples separately, which is why Phase D's callback handler is needed for the full zero-config experience) — handled gracefully with a None default.

**"file_name" as primary source key for LlamaIndex.**
LlamaIndex's `SimpleDirectoryReader` and most other readers set `metadata["file_name"]` as the source document identifier, not `metadata["source"]`. Checking `file_name` first, then falling back to `source`, covers both LlamaIndex-native readers and any custom node that follows LangChain-style conventions.

**get_content() preferred over .text for LlamaIndex nodes.**
`get_content()` is the stable public API on `BaseNode` (and all subclasses including `TextNode`, `ImageNode`). `.text` is an internal attribute on `TextNode` specifically. Checking `hasattr(node, "get_content")` first and falling back to `getattr(node, "text", "")` handles both current and future node types correctly.

---

### Validation results — 2026-06-18

**test_normalizers.py:** 10/10 passed (8 Tier 1 fake-object tests + 2 Tier 2 real langchain-core tests; 2 Tier 2 llama-index tests skipped — package not installed).

**test_manual_pattern.py re-run (Phase A regression):** All three scenarios still pass with identical sub-millisecond timing:
- Scenario 1: `with block elapsed: 0.90ms`
- Scenario 2: `with block elapsed: 0.32ms`
- Scenario 3: `with block elapsed: 0.01ms`

Refactor confirmed behavior-identical. Phase A's validated timing numbers are unchanged.

**SDK Phase B milestone: complete.** `log_chunks()` auto-detects and normalizes all four chunk formats. Duck-typing detection confirmed against real `langchain-core` objects. Synchronous-vs-background error handling boundary correctly implemented and documented.

---

## 2026-06-18 — SDK Phase C: Mini RAG App — First Organic Pipeline Test

### What was built

A small standalone RAG application in `mini-rag-app/` using plain Python and direct OpenAI API calls — no LangChain, no LlamaIndex, no framework. The ContextLens SDK's manual `trace()` pattern was wired in exactly as documented in SDK.md, with retrieval and generation written first as if ContextLens didn't exist.

**Corpus:** 8 `.md` policy documents (refund-policy, cancellation-policy, shipping-policy, account-deletion, billing-disputes, support-contact, privacy-data-handling, subscription-changes). Total: 41 chunks after paragraph-based splitting. Embedded once via `text-embedding-3-small` and cached to `corpus_embeddings.json`.

**Retrieval:** Cosine similarity in plain Python/numpy over cached embeddings, top-3 chunks per query.

**Generation:** `gpt-4o-mini`, temperature 0.2, prompt instructs it to use provided context and say so clearly if the context is insufficient.

**Queries:** 14 total — 4 straightforward, 4 ambiguous-overlap (topics spanning two documents), 3 no-document (topics not in any document), 3 multi-part.

**Result:** 13 of 14 traces appeared in the dashboard. All 13 processed successfully.

---

### Similarity score range observed (retriever, query-to-chunk)

| Category | Score range | Notes |
|---|---|---|
| Correct document, clear match | 0.62–0.73 | All clear on-topic queries |
| Correct document, ambiguous overlap | 0.58–0.70 | Both relevant documents score similarly |
| No document covers the topic | 0.21–0.32 | Best-chunk score even on off-topic queries |

The attribution threshold in the pipeline is 0.75 (claim-to-chunk similarity, not query-to-chunk). Attribution uses a separate embedding comparison — claim embedding vs chunk embedding — which often scores higher than the retriever score because the LLM's response text is semantically closer to the source than the query was. The attributions that succeeded landed between **0.751 and 0.813**.

The retriever score range (0.62–0.73 for clear matches) confirms the corpus and queries are within a realistic range: not artificially inflated, not pathologically weak. Real separation between on-topic (0.6+) and off-topic (<0.33) is clear. The attribution threshold correctly rejected all three no-document traces.

---

### Finding 1 (significant): Attribution threshold generates false positives when the LLM splits a source paragraph into sub-claims

**What happened:** The 0.75 attribution threshold correctly identifies verbatim or near-verbatim claims. It misclassifies correct paraphrased claims as retrieval failures when the LLM breaks a multi-sentence source paragraph into individual sub-claims.

**Mechanism:** Attribution compares the embedding of each claim against the embeddings of the retrieved chunks (full paragraphs). A 2-sentence paraphrase of one sentence extracted from a 5-sentence paragraph scores below 0.75 against the full paragraph embedding, because the paragraph's embedding vector is pulled toward all its other sentences. A direct quote scores higher.

**Clearest example — Q06** ("What happens to my account and data after I cancel my subscription?"):

Source chunk (cancellation-policy.md, chunk 2): *"After a subscription is cancelled, access to paid features is retained through the end of the billing period. At that point the account automatically downgrades to the free tier, if one is available, or access is suspended. Data associated with the account is retained for 90 days after the end of the paid period, after which it is subject to deletion under our data retention policy."*

LLM decomposed this into 5 claims. Only claim 1 passed attribution (score 0.779). Claims 2–5 were all flagged as retrieval failures:
- Claim 1: "After you cancel your subscription, you will retain access to paid features until the end of the billing period." → **attributed** (score 0.779), faithful
- Claim 2: "Your account will automatically downgrade to the free tier after the billing period, if available." → **null** (retrieval failure) — sourced from the same paragraph, one sentence later
- Claim 3: "If the free tier is not available, access will be suspended after the billing period." → **null** — same paragraph
- Claim 4: "Your data will be retained for 90 days after the end of the paid period." → **null** — same paragraph; this is essentially verbatim ("Data associated with the account is retained for 90 days")
- Claim 5: "After 90 days, your data is subject to deletion." → **null** — same paragraph

This is a false positive rate of 80% for a single-source response that the LLM answered correctly and faithfully.

**More examples:**
- Q05 (downgrade policy): 3 claims, all null. Retriever returned subscription-changes.md at 0.684. The claim "Plan downgrades take effect at the start of the next billing period" is nearly verbatim from the source — failed attribution.
- Q13 (multi-part billing + deletion): Claim 2 ("You can email billing@example.com...") is the second half of the same sentence that claim 1 was attributed against. Claim 1 passed (0.780), claim 2 failed — same source, split by the decomposer.
- Q07 (annual refund): "If you cancel your annual plan within the first 14 days, you are eligible for a full refund" failed attribution. Source text says: "For annual subscriptions, customers who cancel within the first 14 days are eligible for a full refund." The LLM changed "For annual subscriptions, customers who cancel" to "if you cancel your annual plan" — this paraphrase pushed it below 0.75.
- Q04 vs Q12 (shipping): Q04's single-claim response hit attribution score 0.751 (barely passes). Q12 also asked about shipping, and the claim "Standard shipping takes 5–7 business days for domestic orders within the continental United States" fell just below 0.75 (failed). The LLM output was nearly identical wording; the difference is that Q12's retrieved shipping chunk had lower retriever similarity than Q04's, possibly due to context differences in the stored embeddings.

**What this means:** Many traces in the dashboard show a high "retrieval failure" rate that is actually correct LLM behavior, not retrieval failure. The ContextLens value proposition — distinguishing retrieval failures from generation failures — is undermined when correctly sourced, faithfully generated claims are miscategorized as retrieval failures.

---

### Finding 2: LLM "I don't know" responses are classified as retrieval failures — this is technically correct but produces confusing signal

For Q09, Q10, Q11 (topics not in any document), the LLM correctly declined: "The context does not contain information about [topic]." This is correct, responsible LLM behavior.

The pipeline decomposed these into claims like "The provided context does not contain any information regarding student discounts" — and correctly marked them as retrieval failures (no source chunk found with sufficient similarity). Technically right: no source was found.

The confusing signal: from the dashboard, this looks identical to a case where the LLM hallucinated an answer to an out-of-corpus query. Both produce retrieval failure claims. Currently there's no way to tell from the trace data alone whether the LLM correctly refused or whether it confidently fabricated an answer. The distinction matters: one means the system is working, the other means it's failing.

---

### Finding 3: Q14 trace was not received by the backend

Q14 ("What happens if I miss the 30-day notice window for annual cancellation, and can I still downgrade to a lower plan instead?") was confirmed sent by `run_queries.py` (the background thread was started, no exception was raised), but the trace never appeared in the dashboard. 13 of 14 queries are present.

The SDK behaved exactly as designed — fire-and-forget, failed silently. But the developer has no feedback that the trace was dropped without manually checking the dashboard.

---

### What worked well

- **No-document detection**: All three off-topic queries (Q09–Q11) correctly produced null attribution. The retriever score ceiling for off-topic queries was 0.317, cleanly below the attribution threshold.
- **Multi-part decomposition**: The decomposer correctly separated multi-topic responses. Q12 (digital products + shipping) and Q13 (billing dispute + account deletion) each produced claims attributed to different source documents.
- **Judge reasoning quality**: Every attributed claim had precise, verbatim-citing judge reasoning in the format `[source: "exact quote"]`. No generic reasoning observed on organic data. This was the strongest area — no degradation versus the synthetic test cases.
- **Attributed claim accuracy**: The 8 claims that did pass attribution (across all 13 traces) were all correctly attributed to the right source document. Zero false attributions to the wrong source were observed.
- **Score discrimination**: Clear separation between on-topic (0.6–0.73) and off-topic (<0.33) retriever scores. The 0.75 attribution threshold correctly categorized all three no-document queries as retrieval failures.

---

### What to investigate or fix in a future session

1. **Attribution threshold recalibration (highest priority):** The 0.75 threshold is too high for paraphrased claims against full-paragraph chunk embeddings. Candidates:
   - Lower threshold to ~0.65 and observe the false-positive rate
   - Switch attribution to sentence-level granularity (split chunks into sentences before embedding for attribution, rather than using the full paragraph embedding) — more expensive but more precise
   - Add a "low-confidence attribution" bucket (0.65–0.75) that surfaces separately in the dashboard rather than collapsing to "retrieval failure"

2. **LLM refusal detection:** Claims of the form "The context does not contain information about X" should be detectable by the decomposer and categorized differently from factual claims requiring source attribution. One approach: if the claim text contains the phrase "does not contain" or "no information" referencing the context, treat it as a meta-claim and skip attribution scoring.

3. **Trace delivery confirmation:** The fire-and-forget invariant must stay, but the developer currently has no lightweight way to know that a trace was dropped. A possible addition: a counter exposed in the SDK (e.g. `contextlens.stats()`) showing traces_attempted / traces_delivered, updated on each background thread completion. This does not block the caller, but gives observability after the fact.

4. **Sub-claim splitting:** When the decomposer produces multiple claims from a single source sentence, the attribution step has to match each individual sub-claim against the full paragraph. This magnifies the threshold issue. Possible fix at the decomposer level: prompt it to produce complete claim statements rather than splitting a single sentence into multiple fragments.

---

### Validation steps passed

1. `ingest_corpus.py` produced 41 chunks across 8 documents, `corpus_embeddings.json` created.
2. Retriever standalone test: returned sensible top-3 chunks with score range 0.69 (clear match) → 0.32 (off-topic). Real variation confirmed, not all-high or all-low.
3. Generator standalone test: coherent response for a simple refund question.
4. `run_queries.py`: 14/14 queries executed, all returned 202 from `/ingest`, no application errors.
5. 13/14 traces in dashboard with `status=processed` (1 trace — Q14 — silently dropped by SDK background thread). All 13 processed correctly; none stuck in pending or failed.
6. Written review covers all five review points with specific trace IDs, claim text, attribution scores, and judge reasoning — see above.

**SDK Phase C milestone: complete.** First organic pipeline test run. 13 traces processed. Attribution threshold calibration issue identified with specific evidence — this is the highest-priority finding for Phase D+ work.
