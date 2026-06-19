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

- [x] Monorepo folder structure (see bottom of this file)
- [x] `docker-compose.yml` with all five services:
      postgres, redis, api, worker, dashboard
- [x] `.env.example` with all required variables documented
- [x] Database schema: `projects`, `traces`, `chunks`, `claims` tables
- [x] Alembic setup + first migration (`0001_initial_schema.py`)
- [x] FastAPI skeleton: single `POST /ingest` (no auth yet) that stores a trace
- [x] Celery skeleton: task that picks up a job and logs the trace_id
- [x] asyncpg connection pool setup
- [x] Redis connection setup

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

- [x] Claim decomposition: LLM call with JSON output mode
- [x] Claim embedding: `text-embedding-3-small` via OpenAI SDK
- [x] Chunk deduplication: store chunks from ingest payload using `content_hash`
- [x] Chunk embedding: embed each chunk on first ingestion, store in pgvector
- [x] pgvector similarity search: find best matching chunk per claim embedding
- [x] Store attribution results: `attributed_chunk_id` + `attribution_score` in claims
- [x] Attribution threshold: claims below 0.75 similarity get `null` attribution

**Milestone:**
```bash
# send a trace with known chunks and response
# → claims table has rows with attributed_chunk_id and attribution_score
```

---

### Week 3 — Faithfulness Scoring + Reliability

- [x] LLM-as-judge: faithfulness scoring per claim (verdict + score + reasoning)
- [x] Handle null attribution: skip judge call, mark as unfaithful with explanation
- [x] Celery retry logic: 3 attempts, exponential backoff (60s, 120s, 240s)
- [x] Dead letter queue: failed jobs after 3 retries stored for inspection
- [x] Trace status updates: pending → processing → processed / failed
- [x] `GET /traces/{id}` endpoint: returns trace with all claims and scores
      (built as `GET /projects/{project_id}/traces/{trace_id}` — project-scoped from the start)

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

- [x] `POST /projects`, `GET /projects`, `DELETE /projects/{id}`
- [x] `POST /projects/{id}/api-keys` — generate key, return raw once, store hash
- [x] `GET /projects/{id}/api-keys`, `DELETE .../api-keys/{keyId}`
- [x] Add API key validation to `POST /ingest`
      (hash incoming key, look up in `api_keys` table)
- [x] Add `project_id` to `traces`, `chunks` via migration (0003 — claims inherit via trace join)
- [x] Scope all management API queries by `project_id`
- [x] `usage_records` table + increment on every processed trace

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

- [x] Next.js setup: TypeScript, Tailwind, App Router
- [x] API client wrapper (`lib/api.ts`) — handles errors, base URL from env
- [x] Dashboard home (`/dashboard`) — project list
- [x] Create project page (`/projects/new`)
- [x] Project overview page (`/projects/[id]`) — stats summary
- [x] API key management (`/projects/[id]/settings/api-keys`)
      — list keys, create key (show once modal), revoke key

**Milestone:** Developer can create a project and manage API keys in the browser.

---

### Week 6 — Core Data Views

- [x] Trace list (`/projects/[id]/traces`)
      — with filters: status, faithfulness threshold (date range filter not implemented)
- [x] **Trace detail (`/projects/[id]/traces/[traceId]`)** ← most important page
      - Query text
      - LLM response
      - Claims list, each showing:
        - Claim text
        - Color coded: green (faithful) / yellow (partial) / red (unfaithful)
        - Retrieval failure (orange) vs generation failure (purple) badge
        - Attributed source chunk (expanded by default for non-faithful claims)
        - Attribution score + faithfulness score + confidence band (amber for low)
        - Judge reasoning always visible
- [x] Empty state: onboarding checklist with numbered steps and curl example
- [x] Loading states and error states throughout

**Milestone:** A processed trace is visible with per-claim attribution.
Developer can see exactly which claim failed and where it came from.
This is the demo milestone — this is what you show a founder.

---

## Phase 4: Analytics + Polish (Weeks 7–8)

**Goal:** Aggregate intelligence works. The product feels complete.

- [x] Query clustering: scheduled Celery beat job every 6 hours
      (k-means on query embeddings, LLM cluster labeling via gpt-4o-mini)
- [x] Cluster view (`/projects/[id]/clusters`)
- [x] Problem documents view (`/projects/[id]/documents/problems`)
      (URL path is `/documents/problems`, not `/documents`)
- [ ] Faithfulness over time chart on project overview page
      (not built — project overview shows avg_faithfulness_7d as a stat card number;
      the recharts bar chart was built for the usage page showing traces processed per day,
      not faithfulness over time; see build-log.md Phase 4 Part A)
- [x] Rate limiting: Redis-based per-project limits on ingest (per-minute + per-hour windows)
- [x] Abuse detection: volume spike flagging job (hourly Celery beat task)
- [x] Usage stats page (`/projects/[id]/settings/usage`)
      (path is `/settings/usage`, not `/usage`)
- [x] Health endpoint (`GET /health`) — DB + Redis + worker status
- [x] Onboarding flow: first-time setup guide on empty dashboard (Phase 4 Part B)
- [x] `docker-compose up` works cleanly with no manual steps beyond `.env`
- [x] `README.md` quickstart tested and accurate (root README.md rewritten after Phase 4)

**Milestone:** The full product works end to end.
Clone → configure .env → docker-compose up → instrument RAG app →
see per-query attribution → see cluster patterns → see problem documents.

---

## SDK Build (Post-Phase 4)

**Goal:** A Python SDK that developers instrument once and never think about again.
Fire-and-forget, sub-millisecond caller overhead, compatible with real framework objects.

This track was not part of the original four-phase plan. It was built after Phase 4
completed because `SDK.md` had specified the design but no phase had scheduled the
implementation. The mini RAG app (Phase C below) also served as the first organic,
non-synthetic validation of the full pipeline built in Phases 1–4.

### Phase A — Manual context-manager pattern

- [x] `sdk/contextlens/__init__.py` — public surface: `contextlens.trace(query)` returning a `TraceContext`
- [x] `sdk/contextlens/context.py` — `TraceContext` context manager; fires background daemon thread on exit; returns in < 1ms regardless of backend state
- [x] `sdk/contextlens/client.py` — `send_trace()` in background thread; catches all exceptions silently (logs at DEBUG only)
- [x] `sdk/contextlens/config.py` — reads env vars fresh per call; warn-once on missing API key
- [x] `sdk/pyproject.toml` — installable via `pip install -e ./sdk`; single runtime dependency (`httpx`)
- [x] `CONTEXTLENS_ENABLED=false` no-op support

**Milestone:** `with contextlens.trace(query=...) as trace:` exits in < 1ms in all three
scenarios: happy path, unreachable backend, disabled. Validated in sdk-validation/test_manual_pattern.py.

---

### Phase B — Chunk format normalizers

- [x] `sdk/contextlens/normalizers.py` — `normalize_chunks()` auto-detects four formats:
  - `list[str]` — plain text strings
  - `list[dict]` — dicts with `content`, `source`, optional `chunk_index`/`retriever_score`
  - LangChain `Document` objects — `page_content` + `metadata` extracted via duck-typing
  - LlamaIndex `NodeWithScore` objects — `get_content()` + `score` extracted via duck-typing
- [x] Detection is pure duck-typing — no langchain or llama-index dependency in the SDK itself
- [x] `log_chunks()` raises `ContextLensError` synchronously on unrecognised types (programming error, not silenced)
- [ ] LangChain callback handler integration — **not built**; only manual object passing through `log_chunks()` is supported
- [ ] LlamaIndex event handler integration — **not built**; same as above

**Milestone:** `normalize_chunks()` passes all four format scenarios including real LangChain
Document objects (llama-index-core not installed in test env, covered by fake-object tests).

---

### Phase C — Mini RAG app organic validation

- [x] `mini-rag-app/` — full RAG application using 8 policy documents (41 chunks), plain numpy cosine retrieval, gpt-4o-mini generation
- [x] 14 queries run; 13 of 14 traces reached the dashboard with `status=processed`
- [x] First organic (non-synthetic) test of the full pipeline; identified the attribution threshold calibration issue: real LLM claims scoring in 0.65–0.75 range were miscategorised as retrieval failures

**Milestone:** 13/14 traces processed. Attribution threshold issue identified with specific
claim-level evidence — this finding drove Phases D through F.

---

### Phase D — Attribution confidence bands + refusal detection + delivery stats

- [x] Three-band attribution model: `high` (>= 0.75), `low` (0.65–0.74), `null` (< 0.65)
      — migration 0006; both high and low-confidence claims go through the faithfulness judge
- [x] `attribution_confidence` column added to claims table
- [x] Dashboard amber "Low confidence match" badge for low-confidence attributions
- [x] Refusal detection in decomposer prompt — LLM declines stored as `faithfulness_verdict = 'refusal'`, distinct from hallucinations
- [x] `sdk/contextlens/stats.py` — `get_stats()` returning `{attempted, delivered, failed}` counters; process-local, thread-safe, pull-based

**Phase D validation audit (separate session):** Confirmed Phase D fix was genuine for Q12
and Q13 (same claim text, different outcome). Found Phase D's log had compared the wrong
traces for Q06 — the frozen-response retest proved the sub-claim fragmentation problem
persisted for claims landing below 0.65. Drove Phase E.

**Milestone:** Low-confidence band surfaced in dashboard; correct refusals shown as "Declined"
not as hallucinations; delivery stats available without blocking callers.

---

### Phase E — Decomposer prompt: conditional and consequence-chain rules

- [x] `SYSTEM_PROMPT` extended with explicit COMBINE/SPLIT rules and three few-shot examples:
  - Conditional "if A then X, or if not A then Y" structures → one combined claim
  - "X, after which Y" consequence chains → one combined claim
  - Genuinely independent facts about different topics → correctly split
- [x] Q06 frozen-response retest: sub-claims that previously scored 0.6491/0.6446 (both NULL)
      now produce one combined claim at 0.7114 (low confidence, attributed, faithful)
- [x] Q12 and Q13 regression confirmed — correct splits preserved

**Milestone:** Q06 "downgrade or suspend" case correctly produces one attributed claim
instead of two retrieval-failure fragments.

---

### Phase F — Decomposer prompt: flat enumeration rules

- [x] COMBINE rule extended to cover flat enumerations and concessive "but" structures
- [x] Three new few-shot examples added (Examples 4, 5, 6): 2-item enumeration, 3-item enumeration, concessive "but"
- [x] Q14 two NULL claims confirmed as enumeration-dilution artifacts (not genuine retrieval failures — Phase E's log was incorrect, same pattern as Phase D's Q06 premature validation)
- [x] All 7 local test cases pass with no regression on Phase E patterns

**Milestone:** All compound-sentence splitting patterns addressed at the decomposer level.
Remaining NULL claims in the test corpus are chunk-granularity or generation-completeness
issues — not decomposer problems and not fixable by further prompt changes.

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

| Phase | Done When |
|-------|-----------|
| Phase 1 | `curl POST /ingest` → `GET /projects/{id}/traces/{id}` returns claims with scores ✓ |
| Phase 2 | Project API key created in dashboard authenticates ingest; traces are project-scoped ✓ |
| Phase 3 | Trace detail page shows per-claim attribution with color coding and failure-type badges ✓ |
| Phase 4 | Cluster + documents views populated; `docker-compose up` is the full install ✓ |
| SDK Build | Manual pattern validated sub-ms; normalizers handle real LangChain/LlamaIndex objects; mini RAG app stress-tested; three-band attribution, refusal detection, delivery stats, and three rounds of decomposer prompt fixes all validated with frozen-response evidence ✓ |
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
