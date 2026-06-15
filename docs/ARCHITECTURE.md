# Architecture

This document explains the full system architecture of ContextLens — every component,
why it exists, and how they talk to each other.

---

## Deployment Model: Self-Hosted

ContextLens runs entirely on the developer's own machine or server via Docker Compose.
There is no central cloud service. No data leaves the developer's infrastructure.

```
Developer's machine / server
│
├── .env                  ← config (OpenAI key, ports, etc.)
├── docker-compose.yml    ← the entire product
│
├── postgres:5432         ← all persistent data
├── redis:6379            ← job queue + rate limiting
├── api:8000              ← FastAPI (ingest + management)
├── worker                ← Celery (attribution pipeline)
└── dashboard:3000        ← Next.js (the UI)
```

The developer's RAG app runs outside Docker (on their machine or their own server)
and talks to ContextLens via the SDK pointing at `localhost:8000`.

### docker-compose.yml Reference

Six services. `api` and `worker` and `beat` use the same Docker image from `./backend` — different start commands.

```yaml
services:

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  worker:
    build: ./backend
    command: celery -A app.worker.celery_app worker --loglevel=info --concurrency=4
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  beat:
    build: ./backend
    # Celery beat — triggers the periodic clustering job
    command: celery -A app.worker.celery_app beat --loglevel=info
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  dashboard:
    build: ./frontend
    ports:
      - "3000:3000"
    env_file: .env
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
```

**Why a separate `beat` service?**
Celery beat is the scheduler that fires periodic tasks (e.g. the clustering job every 6 hours). It must run as its own process — running it inside the worker container is not recommended in production.

---

## Core Design Insight

Every wrong answer in a RAG system has one of two root causes:

```
Retrieval failure   — right document was never fetched → fix the search
Generation failure  — right document was there, AI misrepresented it → fix the prompt
```

These look identical from the outside. The entire pipeline is designed to separate them. A claim with null attribution is a retrieval failure. A claim with high attribution and low faithfulness is a generation failure. The dashboard surfaces this distinction explicitly on every claim.

Before naming any technology, we identify the five jobs this system must do:

```
1. Sit inside someone's existing RAG pipeline and capture data
2. Store that data reliably
3. Process it asynchronously (decompose claims, score faithfulness)
4. Serve the results to a dashboard
5. Aggregate patterns across many queries
```

Every component exists to serve one of these jobs. Nothing else.

---

## Component Map

```
┌──────────────────────────────────────────────────────────────┐
│                    Developer's RAG App                        │
│   (runs outside Docker — their chatbot, doc QA app, etc.)    │
│                                                               │
│   with contextlens.trace(query) as trace:                    │
│       chunks = retriever.fetch(query)                         │
│       trace.log_chunks(chunks)                                │
│       response = llm.generate(chunks, query)                  │
│       trace.log_response(response)                            │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP POST /ingest
                       │ async, background, <5ms overhead
                       │ Authorization: Bearer <local_api_key>
                       ↓
┌──────────────────────────────────────────────────────────────┐
│              FastAPI (api:8000)  [Docker]                     │
│                                                               │
│  POST /ingest                                                 │
│    1. validate local API key                                  │
│    2. check rate limits (Redis)                               │
│    3. store raw trace in Postgres (status: pending)           │
│    4. enqueue job { trace_id } in Redis                       │
│    5. return 202 Accepted immediately                         │
│                                                               │
│  GET /traces, GET /traces/{id}, GET /clusters, etc.           │
│    → no auth needed (localhost only)                          │
│    → reads processed results from Postgres                    │
└──────────┬───────────────────────────────┬───────────────────┘
           │ enqueue job                   │ read/write
           ↓                               ↓
┌─────────────────────┐      ┌─────────────────────────────────┐
│   Redis (redis:6379) │      │     Postgres (postgres:5432)    │
│   [Docker]           │      │     [Docker]                    │
│                      │      │                                 │
│  Celery job queue    │      │  traces       chunks            │
│  Rate limit counters │      │  claims       projects          │
│                      │      │  query_clusters                 │
└──────────┬───────────┘      │  usage_records                  │
           │                  └─────────────────────────────────┘
           ↓                               ↑
┌─────────────────────────────────────────┘
│   Celery Worker  [Docker]
│
│   1. fetch raw trace from Postgres
│   2. call LLM → decompose into claims    ← uses OPENAI_API_KEY from .env
│   3. embed each claim                    ← uses OPENAI_API_KEY from .env
│   4. pgvector similarity search → attribution
│   5. call LLM-as-judge → faithfulness   ← uses OPENAI_API_KEY from .env
│   6. write claims + scores to Postgres
│   7. update trace status → processed
│   (retry on failure: 3 attempts, exponential backoff)
└─────────────────────────────────────────┐
                                          │
┌─────────────────────────────────────────┘
│   Next.js Dashboard (dashboard:3000)  [Docker]
│
│   Reads from FastAPI management API
│   No login required — localhost access is authorization
│
│   View 1: per-query trace detail (claim attribution)
│   View 2: aggregate patterns (clusters, problem docs)
└─────────────────────────────────────────────────────────────┘
```

---

## Authentication Model (Self-Hosted)

Because ContextLens runs on localhost, authentication is deliberately minimal.

**Dashboard → API (management routes):**
No authentication. The dashboard is at `localhost:3000` — if someone has access to
your localhost, they already have access to your machine. No login screen needed.

**SDK → API (ingest route):**
A single local API key defined in `.env`:

```bash
CONTEXTLENS_LOCAL_API_KEY=local_dev_key_change_me
```

This key is set in the SDK:
```bash
CONTEXTLENS_API_KEY=local_dev_key_change_me
CONTEXTLENS_API_URL=http://localhost:8000
```

This prevents accidental cross-contamination if someone runs multiple local services,
and keeps the ingest endpoint consistent with how a cloud version would work — making
the future cloud migration straightforward.

**Why no JWT, no signup, no sessions?**
Because there's only one user — the developer running the tool. Full auth machinery
would add weeks of build time with zero benefit for a single-user local tool.
When multi-user cloud support is needed, the auth layer from `docs/CLOUD_FUTURE.md`
gets added without changing anything else.

---

## Component Responsibilities

### Python SDK

**Job:** Capture RAG pipeline data without affecting performance.

- Non-intrusive — wraps existing code, does not replace it
- Fire-and-forget — sends data in a background thread, never blocks the RAG app
- Fails silently — if ContextLens is down, the RAG app continues unaffected
- Reads `CONTEXTLENS_API_KEY` and `CONTEXTLENS_API_URL` from environment

---

### FastAPI

**Job:** Two route groups, two distinct responsibilities.

**Ingest routes** (`POST /ingest`):
- Validates the local API key
- Stores raw trace (status: pending)
- Enqueues attribution job in Redis
- Returns 202 immediately — never waits for processing

**Management routes** (`GET /traces`, `GET /clusters`, etc.):
- No auth on self-hosted (localhost assumption)
- All queries scoped to `project_id` from the URL
- Reads processed results from Postgres

---

### Redis

**Job:** Two jobs, one service.

1. **Celery broker** — holds the queue of pending attribution jobs
2. **Rate limiting** — per-API-key counters to prevent accidental loops or abuse

---

### Celery Worker

**Job:** Run the slow LLM pipeline asynchronously.

Why async? LLM calls take 5–10 seconds. Processing inline would block the SDK
and make the developer's RAG app noticeably slower. The worker decouples ingestion
from processing — the SDK returns instantly, the worker processes in the background.

Pipeline per trace:
```
decompose claims (LLM) → embed claims → pgvector attribution → faithfulness scoring (LLM)
```

Uses the developer's own `OPENAI_API_KEY` from `.env`.

---

### Postgres + pgvector

**Job:** Store everything. Handle relational queries AND vector similarity search.

The `<=>` pgvector cosine distance operator IS the attribution step:
```sql
SELECT id, 1 - (embedding <=> :claim_embedding) AS score
FROM chunks
WHERE project_id = :project_id
ORDER BY embedding <=> :claim_embedding
LIMIT 1;
```

No separate vector database needed. pgvector handles our scale in one service.

---

### Next.js Dashboard

**Job:** Make the pipeline's output visually legible.

Two core views:
1. Per-query trace detail — claim by claim, with source chunk and scores
2. Aggregate pattern view — clusters, problem documents, faithfulness trends

Talks to FastAPI management API at `http://localhost:8000`.
Accessible at `http://localhost:3000` — no login required.

---

## Data Flow: One Complete Query

```
T=0ms    User asks your chatbot a question

T=10ms   RAG app retrieves chunks, generates response
         SDK captures: query + chunks + response

T=12ms   SDK fires POST /ingest in background thread
         RAG app continues — user gets their response
         RAG app is done with ContextLens

T=15ms   FastAPI validates API key
         Stores raw trace (status: pending)
         Pushes job to Redis queue
         Returns 202

T=20ms   Celery worker picks up job

T=2500ms LLM decomposes response into claims

T=2510ms pgvector finds best matching chunk per claim (attribution)

T=5000ms LLM-as-judge scores faithfulness per claim
         Results written to Postgres (status: processed)

T=later  Developer opens http://localhost:3000
         Sees trace with per-claim attribution
```

---

## What Is Deliberately Not in This Architecture

| Excluded                    | Why                                              |
|-----------------------------|--------------------------------------------------|
| User signup / login / JWT   | Single-user localhost tool — not needed          |
| Email delivery              | No accounts, no verification emails needed       |
| Stripe / billing            | Self-hosted, no subscription to manage           |
| Organizations / teams       | Future — see CLOUD_FUTURE.md                     |
| Separate vector DB          | pgvector handles our scale in one database       |
| Kubernetes                  | Docker Compose is sufficient                     |
| WebSocket real-time updates | Polling is sufficient, data isn't time-critical  |
| GraphQL                     | REST is simpler, sufficient for our API surface  |

---

## Future-Proofing for Cloud

The self-hosted architecture is deliberately structured so that a cloud version
can be added by layering on top, not by rewriting:

```
Self-hosted (now)              Cloud addition (later)
──────────────────             ───────────────────────────────
.env API key          →        user accounts + JWT tokens
localhost assumption  →        proper auth middleware
one project           →        multi-user project isolation
no email              →        SendGrid email delivery
Docker Compose        →        Railway / Render deployment
```

The core pipeline (SDK → ingest → worker → Postgres → dashboard) does not change.
See `docs/CLOUD_FUTURE.md` for the exact migration path.
