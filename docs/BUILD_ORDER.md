# Build Order

Exact implementation phases, week by week.
The guiding principle: ship the core pipeline first. Everything else is secondary.

---

## Guiding Principle

> A trace goes in, claims come out. That's Phase 1.
> Everything else — auth, dashboard, analytics — layers on top of a working pipeline.

---

## Phase 1: Core Pipeline (Weeks 1–3)

**Goal:** A trace goes in and claims + scores come out. No auth, no dashboard.
Just the pipeline working end to end, verifiable via curl.

### Week 1 — Project Scaffolding + Data Layer

- [ ] Monorepo folder structure (see bottom of this file)
- [ ] `docker-compose.yml` with all five services:
      postgres, redis, api, worker, dashboard
- [ ] `.env.example` with all required variables documented
- [ ] Database schema: `projects`, `traces`, `chunks`, `claims` tables
- [ ] Alembic setup + first migration (`0001_initial_schema.py`)
- [ ] FastAPI skeleton: single `POST /ingest` (no auth yet) that stores a trace
- [ ] Celery skeleton: task that picks up a job and logs the trace_id
- [ ] asyncpg connection pool setup
- [ ] Redis connection setup

**Milestone:**
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer local_dev_key" \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "chunks": [...], "response": "test response"}'
# → trace row in DB, worker logs "picked up trace tr_123"
```

---

### Week 2 — Attribution Pipeline

- [ ] Claim decomposition: LLM call with JSON output mode
- [ ] Claim embedding: `text-embedding-3-small` via OpenAI SDK
- [ ] Chunk deduplication: store chunks from ingest payload using `content_hash`
- [ ] Chunk embedding: embed each chunk on first ingestion, store in pgvector
- [ ] pgvector similarity search: find best matching chunk per claim embedding
- [ ] Store attribution results: `attributed_chunk_id` + `attribution_score` in claims
- [ ] Attribution threshold: claims below 0.75 similarity get `null` attribution

**Milestone:**
```bash
# send a trace with known chunks and response
# → claims table has rows with attributed_chunk_id and attribution_score
```

---

### Week 3 — Faithfulness Scoring + Reliability

- [ ] LLM-as-judge: faithfulness scoring per claim (verdict + score + reasoning)
- [ ] Handle null attribution: skip judge call, mark as unfaithful with explanation
- [ ] Celery retry logic: 3 attempts, exponential backoff (60s, 120s, 240s)
- [ ] Dead letter queue: failed jobs after 3 retries stored for inspection
- [ ] Trace status updates: pending → processing → processed / failed
- [ ] `GET /traces/{id}` endpoint: returns trace with all claims and scores

**Milestone:**
```bash
curl http://localhost:8000/traces/tr_123
# → full trace JSON with claims, attribution scores, faithfulness scores,
#   judge reasoning, and status: "processed"
```

At this point the core product works. Everything after this is packaging.

---

## Phase 2: Projects + Local API Keys (Week 4)

**Goal:** Multiple projects can coexist. SDK authenticates via a local key.
Data is scoped to projects.

- [ ] `POST /projects`, `GET /projects`, `DELETE /projects/{id}`
- [ ] `POST /projects/{id}/api-keys` — generate key, return raw once, store hash
- [ ] `GET /projects/{id}/api-keys`, `DELETE .../api-keys/{keyId}`
- [ ] Add API key validation to `POST /ingest`
      (hash incoming key, look up in `api_keys` table)
- [ ] Add `project_id` to `traces`, `chunks`, `claims` via migration
- [ ] Scope all management API queries by `project_id`
- [ ] `usage_records` table + increment on every processed trace

**Milestone:**
```bash
# create a project
curl -X POST http://localhost:8000/projects -d '{"name": "My Bot"}'
# → { "id": "proj_abc", "name": "My Bot" }

# create an API key for it
curl -X POST http://localhost:8000/projects/proj_abc/api-keys -d '{"name": "local"}'
# → { "key": "cl_proj_xyz..." }  ← shown once

# send a trace with that key
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer cl_proj_xyz..." \
  -d '{...}'

# see traces scoped to project
curl http://localhost:8000/projects/proj_abc/traces
# → only traces for this project
```

---

## Phase 3: Dashboard (Weeks 5–6)

**Goal:** The attribution results are visible in a browser. The "aha moment" works.

### Week 5 — Project Management UI

- [ ] Next.js setup: TypeScript, Tailwind, App Router
- [ ] API client wrapper (`lib/api.ts`) — handles errors, base URL from env
- [ ] Dashboard home (`/dashboard`) — project list
- [ ] Create project page (`/projects/new`)
- [ ] Project overview page (`/projects/[id]`) — stats summary
- [ ] API key management (`/projects/[id]/settings/api-keys`)
      — list keys, create key (show once modal), revoke key

**Milestone:** Developer can create a project and manage API keys in the browser.

---

### Week 6 — Core Data Views

- [ ] Trace list (`/projects/[id]/traces`)
      — with filters: status, date range, faithfulness threshold
- [ ] **Trace detail (`/projects/[id]/traces/[traceId]`)** ← most important page
      - Query text
      - LLM response
      - Claims list, each showing:
        - Claim text
        - Color coded: green (faithful) / yellow (partial) / red (unfaithful)
        - Attributed source chunk (expandable)
        - Attribution score + faithfulness score
        - Judge reasoning
- [ ] Empty state: what to show when no traces exist yet (onboarding nudge)
- [ ] Loading states and error states throughout

**Milestone:** A processed trace is visible with per-claim attribution.
Developer can see exactly which claim failed and where it came from.
This is the demo milestone — this is what you show a founder.

---

## Phase 4: Analytics + Polish (Weeks 7–8)

**Goal:** Aggregate intelligence works. The product feels complete.

- [ ] Query clustering: scheduled Celery beat job
      (k-means on query embeddings, LLM cluster labeling)
- [ ] Cluster view (`/projects/[id]/clusters`)
- [ ] Problem documents view (`/projects/[id]/documents`)
- [ ] Faithfulness over time chart on project overview page
- [ ] Rate limiting: Redis-based per-project limits on ingest
- [ ] Abuse detection: volume spike flagging job
- [ ] Usage stats page (`/projects/[id]/usage`)
- [ ] Health endpoint (`GET /health`) — DB + Redis + worker status
- [ ] Onboarding flow: first-time setup guide on empty dashboard
- [ ] `docker-compose up` works cleanly with no manual steps beyond `.env`
- [ ] `README.md` quickstart tested and accurate

**Milestone:** The full product works end to end.
Clone → configure .env → docker-compose up → instrument RAG app →
see per-query attribution → see cluster patterns → see problem documents.

---

## Phase 5: Cloud / Multi-User (Future — Not Now)

Do not build these now. The architecture is designed so they layer on cleanly.

- [ ] User accounts: signup, email verification, login, JWT, password reset
- [ ] Multi-user project isolation: `user_id` on projects, auth middleware
- [ ] Cloud deployment: Railway / Render
- [ ] Email delivery: SendGrid
- [ ] Stripe billing: paid plans, usage limits
- [ ] Organizations / team accounts
- [ ] SSO / Google OAuth
- [ ] TypeScript SDK
- [ ] Framework auto-integrations (LangChain, LlamaIndex callbacks)
- [ ] Webhook alerts
- [ ] Configurable embedding model per project

See `docs/CLOUD_FUTURE.md` for the detailed migration plan.

---

## Folder Structure

```
ContextLens/
├── README.md
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── AUTH.md
│   ├── PIPELINE.md
│   ├── SDK.md
│   ├── API.md
│   ├── DASHBOARD.md
│   ├── METERING.md
│   ├── STACK.md
│   ├── BUILD_ORDER.md
│   ├── DECISIONS.md
│   └── CLOUD_FUTURE.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   └── app/
│       ├── main.py             ← FastAPI entry point
│       ├── config.py           ← settings from env vars
│       ├── database.py         ← asyncpg connection pool
│       ├── redis.py            ← Redis connection
│       ├── models/             ← Pydantic request/response schemas
│       │   ├── projects.py
│       │   ├── traces.py
│       │   └── claims.py
│       ├── routers/            ← FastAPI route handlers
│       │   ├── ingest.py
│       │   ├── projects.py
│       │   ├── traces.py
│       │   └── analytics.py
│       ├── services/           ← business logic (no HTTP concerns)
│       │   ├── project_service.py
│       │   ├── trace_service.py
│       │   └── usage_service.py
│       ├── worker/             ← Celery tasks
│       │   ├── celery_app.py
│       │   ├── tasks.py        ← process_trace task
│       │   ├── decomposer.py   ← claim decomposition
│       │   ├── embedder.py     ← claim + chunk embedding
│       │   ├── attributor.py   ← pgvector similarity search
│       │   └── judge.py        ← faithfulness scoring
│       └── middleware/
│           ├── auth.py         ← local API key validation
│           └── rate_limit.py   ← Redis rate limiting
│
├── sdk/
│   ├── setup.py
│   ├── pyproject.toml
│   └── contextlens/
│       ├── __init__.py         ← public API: trace()
│       ├── client.py           ← HTTP client, fire-and-forget
│       ├── context.py          ← TraceContext (context manager)
│       ├── normalizers.py      ← normalize chunk formats
│       └── config.py           ← env var config
│
└── frontend/
    ├── package.json
    ├── tsconfig.json
    └── app/
        ├── dashboard/
        ├── projects/
        │   ├── new/
        │   └── [projectId]/
        │       ├── page.tsx
        │       ├── traces/
        │       │   ├── page.tsx
        │       │   └── [traceId]/page.tsx   ← most important page
        │       ├── clusters/
        │       ├── documents/
        │       └── settings/api-keys/
        ├── lib/
        │   └── api.ts          ← API client wrapper
        └── components/
            ├── claim-card.tsx  ← core UI component
            ├── trace-list.tsx
            └── faithfulness-chart.tsx
```

---

## Definition of Done Per Phase

| Phase   | Done When |
|---------|-----------|
| Phase 1 | `curl POST /ingest` → `GET /traces/{id}` returns claims with scores |
| Phase 2 | SDK authenticates with project API key, traces are project-scoped |
| Phase 3 | Trace detail page shows per-claim attribution with color coding |
| Phase 4 | Cluster + documents views populated; `docker-compose up` is the full install |
| Phase 5 | (future) Multi-user cloud version deployed and accessible via URL |

---

## .env.example

```bash
# ── LLM ──────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-your-openai-key-here
CONTEXTLENS_EMBEDDING_MODEL=text-embedding-3-small
CONTEXTLENS_JUDGE_MODEL=gpt-4o-mini
CONTEXTLENS_DECOMPOSE_MODEL=gpt-4o-mini

# ── Local API Key (SDK uses this to authenticate with ingest API) ─
CONTEXTLENS_LOCAL_API_KEY=local_dev_key_change_me

# ── Database ──────────────────────────────────────────────────────
POSTGRES_USER=contextlens
POSTGRES_PASSWORD=contextlens
POSTGRES_DB=contextlens
DATABASE_URL=postgresql://contextlens:contextlens@postgres:5432/contextlens

# ── Redis ─────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── Pipeline Settings ─────────────────────────────────────────────
ATTRIBUTION_THRESHOLD=0.75      # min cosine similarity to count as attributed
DAILY_PROCESSING_LIMIT=10000    # max traces processed per project per day

# ── Dashboard ─────────────────────────────────────────────────────
NEXT_PUBLIC_API_URL=http://localhost:8000
```
