# Stack

Every technology choice and the reasoning behind it.

---

## Deployment: Docker Compose

**The entire product ships as a `docker-compose.yml`.**

```yaml
services:
  postgres:   image: pgvector/pgvector:pg16
  redis:      image: redis:7-alpine
  api:        build: ./backend
  worker:     build: ./backend   # same image, different command
  dashboard:  build: ./frontend
```

Installation is:
```bash
git clone ... && cd contextlens && cp .env.example .env && docker-compose up
```

**Why Docker Compose and not Kubernetes?**
Docker Compose runs the full stack on a single machine with one command.
Kubernetes is a cluster orchestrator — it solves problems (rolling deploys,
pod autoscaling, multi-node coordination) we don't have yet.
Using Kubernetes here would add weeks of operational complexity with zero benefit.

**Why not "just run it natively" without Docker?**
Docker normalizes the environment. Without it, every developer would need to
manually install Postgres with pgvector, the right Python version, Redis, etc.
Docker Compose means the exact same environment runs on Mac, Linux, and Windows.

---

## Backend: Python + FastAPI

**Why Python?**

The entire LLM/RAG ecosystem is Python-first:
- OpenAI SDK, Anthropic SDK — Python primary
- LangChain, LlamaIndex — Python primary
- All embedding libraries — Python primary
- RAGAS, DeepEval, evaluation libraries — Python primary

Building the backend in Python means direct access to every relevant library
without writing wrappers. The SDK and backend share the same language —
same Pydantic models validate both outgoing SDK payloads and incoming API payloads.

**Why FastAPI over Flask or Django?**

- **Async-native** — the ingest API handles many simultaneous SDK posts.
  FastAPI uses asyncio natively. Flask is sync-first (WSGI). Django REST Framework
  is heavier than needed.
- **Pydantic** — automatic request/response validation. Define a model,
  FastAPI validates inputs and serializes outputs automatically.
- **Auto-generated OpenAPI docs** — `/docs` works out of the box.
  Useful during development and for eventual public API documentation.

**Python's honest limitation:**
Python's GIL limits true CPU parallelism. But our bottleneck is LLM API latency
(2–5 seconds, I/O bound) — not CPU. FastAPI's async I/O handles I/O-bound
concurrency correctly. The GIL is not a meaningful constraint here.

---

## Async Worker: Celery + Redis

**Why async processing at all?**

The attribution pipeline (claim decomposition + faithfulness scoring) takes 5–10 seconds.
Processing inline in the ingest API would make the SDK hang that long,
blocking the developer's RAG app response. The queue decouples ingestion
from processing — the SDK returns in <50ms, the worker processes in the background.

**Why Celery?**
- Python-native — consistent with the rest of the backend
- Mature and battle-tested — production at thousands of companies for 10+ years
- Retries with exponential backoff — built in, one decorator argument
- Task routing and scheduling — needed for the clustering background job
- Works with Redis as broker out of the box

**Why Redis as the broker (not RabbitMQ)?**
- We already use Redis for rate limiting — one less service to run
- Simpler to configure and operate
- Sufficient throughput — Redis handles millions of queue ops/second
- RabbitMQ offers more advanced routing we don't need

---

## Database: PostgreSQL + pgvector

**Why Postgres?**

The pgvector extension is the key reason. We need:
1. **Vector similarity search** — for the attribution step (find the chunk most similar
   to each claim)
2. **Relational queries** — for projects, traces, claims, usage records

pgvector adds a `vector` column type to Postgres with a cosine distance operator.
We get both capabilities in one database — no need to run a separate vector DB.

**Why not a dedicated vector DB (Pinecone, Qdrant, Weaviate)?**

Adding a dedicated vector DB means:
- Running another Docker service
- Managing another connection in the application
- Duplicating data between the relational DB and the vector DB
- Learning another query interface

At our scale (thousands of chunks, not billions), pgvector with an IVFFlat index
handles similarity search perfectly. One database is simpler, faster to develop,
and easier to back up and restore.

**Why not MongoDB?**

Our data is relational. Traces have claims. Claims reference chunks.
Projects contain traces. These relationships are expressed naturally in SQL
with foreign keys and JOINs. A document DB would require managing these
relationships manually in application code.

**pgvector index:**

```sql
-- IVFFlat: good speed/memory balance at our scale
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

IVFFlat is the right default. If similarity search latency becomes a bottleneck
at larger scale, migrate to HNSW (faster queries, more memory).

**Migrations: Alembic**

Standard migration tool for FastAPI/SQLAlchemy projects.
Every schema change is a versioned file in `alembic/versions/`.
Never alter the schema by hand.

---

## Job Queue / Cache: Redis

Used for two things:

1. **Celery broker** — holds the queue of pending attribution jobs
2. **Rate limiting** — atomic increment counters per project per time window

Redis is in-memory — enqueue/dequeue and rate limit checks are microseconds.
Both use cases are well-suited to Redis's data structures (lists for queues,
strings with TTL for rate limit counters).

---

## Frontend: Next.js + TypeScript

**Why Next.js?**
- **App Router** — file-based routing and layouts make the page structure clean
- **Server-side rendering** — data-heavy dashboard pages load fast
- **TypeScript** — API response shapes are typed, catches integration bugs at compile time
- Industry standard for React apps

**Why not a plain React SPA (Vite)?**
Server-side rendering improves initial load for data-heavy pages.
Next.js also handles routing, which a Vite app needs a separate library for.
The overhead of Next.js is worth it for the dashboard use case.

**Styling: Tailwind CSS**
Utility-first CSS — faster to build with than custom CSS.
No need for a component library; we're building a focused tool, not a design system.

**Charts: Recharts**
React-native charting library. Handles the faithfulness-over-time line chart
and cluster bar charts with minimal setup. No heavyweight dependencies.

---

## LLM Provider: OpenAI (Default) / Configurable

**Default models (from `.env`):**
```bash
CONTEXTLENS_EMBEDDING_MODEL=text-embedding-3-small   # for chunk + claim embeddings
CONTEXTLENS_DECOMPOSE_MODEL=gpt-4o-mini              # for claim decomposition
CONTEXTLENS_JUDGE_MODEL=gpt-4o-mini                  # for faithfulness scoring
```

**Why gpt-4o-mini for pipeline tasks?**
- Cheap — ~10x cheaper than gpt-4o
- Fast — lower latency, important for the async worker throughput
- Good at structured JSON output — exactly what decomposition and judging need
- Sufficient accuracy for claim extraction and binary faithfulness verdicts

**Why make it configurable?**
Some developers use Anthropic's Claude or run local models via Ollama.
The LLM calls are abstracted behind a thin interface in the worker —
swapping the model is a `.env` change, not a code change.

**The developer pays their own LLM bill.**
This is a core self-hosted principle. ContextLens passes through to the
developer's own API key. We incur zero LLM cost.

---

## Version Requirements

| Component | Version |
|---|---|
| Python | **3.11+** |
| Node | **18+** |
| Postgres | **16** (via `pgvector/pgvector:pg16` image) |
| Redis | **7** (via `redis:7-alpine` image) |

**Key Python dependencies:**
- `fastapi`, `uvicorn` — API server
- `celery[redis]` — async worker + beat scheduler
- `asyncpg` — async Postgres driver (no ORM — raw SQL throughout)
- `openai` — LLM + embedding calls
- `pydantic` — request/response validation
- `alembic` — database migrations
- `scikit-learn` — k-means for query clustering
- `httpx` — HTTP client in SDK (fire-and-forget sending)

**Key Node dependencies:**
- `next` (14, App Router)
- `typescript`
- `tailwindcss`
- `recharts` — faithfulness charts

---

## What We're Deliberately NOT Using

| Technology           | Why Not                                                  |
|----------------------|----------------------------------------------------------|
| Separate vector DB   | pgvector handles our scale in one database               |
| Kubernetes           | Docker Compose is sufficient, K8s adds overhead          |
| SQLAlchemy ORM       | asyncpg with raw SQL gives more control and performance  |
| GraphQL              | REST is simpler and sufficient for our API surface       |
| WebSockets           | Polling sufficient — dashboard data isn't time-critical  |
| Microservices        | Monorepo with clear internal separation is faster        |
| Stripe               | No billing in self-hosted version                        |
| SendGrid             | No user accounts, no emails needed                       |
| JWT / sessions       | Single-user localhost — not needed                       |
