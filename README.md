# ContextLens

> **ContextLens tells you whether your RAG system failed to find the right document, or found it and the AI misrepresented it. These need completely different fixes. No current tool makes this distinction.**

Self-hosted. Your data never leaves your infrastructure. You bring your own LLM API key.

---

## The Problem

You've built a RAG system — a chatbot or document QA app that retrieves chunks from a knowledge base and feeds them to an LLM to generate answers. Sometimes the LLM gives wrong answers.

The frustrating part: **you have no idea why — and the fix depends entirely on the reason.**

If the right document was never retrieved, you fix your search. If the right document was retrieved and the AI misrepresented it, you fix your prompt. These are completely different problems. Current tools give you a single score that conflates them.

- Which document caused it?
- Which specific chunk was retrieved?
- Was the right chunk even retrieved, or did the retriever fetch wrong content entirely?
- Is this a one-off, or does this *type of question* always produce bad answers?

Current tools give you aggregate metrics like "faithfulness score: 0.6" — which tells you *something is wrong* but not *where or why*, and not *which of the two problems you're dealing with*.

---

## The Solution

ContextLens instruments your RAG pipeline and makes the critical split explicit on every query:

**Retrieval failure** — the right document was never fetched. Fix your search, your chunking, or your embedding strategy.

**Generation hallucination** — the right document was there and the AI ignored or misrepresented it. Fix your prompt or your model.

These look identical from the outside. ContextLens separates them by:

1. **Decomposing** every LLM response into atomic, self-contained claims
2. **Attributing** each claim back to the specific retrieved chunk it came from (or flagging it as having no source)
3. **Scoring** whether that chunk actually supports the claim — catching subtle misrepresentations like dropped qualifiers
4. **Aggregating** patterns across queries to surface systemic problems by topic and by source document

Instead of "faithfulness score: 0.6" you get:

> *"Claim 3 has no source chunk — your retriever never fetched the refund policy document for this query type. That's a retrieval failure. Fix your search. Claims 1 and 2 were retrieved correctly but the AI dropped 'business' from '30 business days'. That's a generation problem. Tighten your prompt."*

---

## Quickstart

**Prerequisites:** Docker Compose, Python 3.11+, an OpenAI API key.

```bash
# 1. Clone and configure
git clone https://github.com/yourname/contextlens
cd contextlens
cp .env.example .env
# Open .env and fill in OPENAI_API_KEY at minimum

# 2. Start the stack
docker-compose up

# 3. Run database migrations (first time only)
docker-compose exec api alembic upgrade head
```

The dashboard is now at `http://localhost:3000`. The API is at `http://localhost:8000`.

**Step 1: Create a project**

Open `http://localhost:3000`, click "New project", give it a name.

**Step 2: Generate an API key**

In your project, go to Settings > API Keys and create a key. Copy the key immediately — it is shown once. The key is prefixed with `cl_`.

**Step 3: Install the SDK and instrument your RAG app**

```bash
pip install -e ./sdk
```

```python
import contextlens

contextlens.configure(
    api_key="cl_your_key_here",
    api_url="http://localhost:8000",  # default; omit if running locally
)

# Wrap your existing RAG pipeline — no other changes needed
with contextlens.trace(query=user_query) as trace:
    chunks = your_retriever.fetch(user_query)
    trace.log_chunks(chunks)
    response = your_llm.generate(chunks, user_query)
    trace.log_response(response)
```

The `with` block exits in under 1ms regardless of what the backend does. The HTTP send runs in a daemon thread and never blocks your application.

`log_chunks()` auto-detects and normalizes four formats without any extra configuration:
- `list[str]` — plain text chunks
- `list[dict]` — dicts with `content`, `source`, and optional `chunk_index`/`retriever_score` keys
- LangChain `Document` objects — `page_content` and `metadata` extracted automatically
- LlamaIndex `NodeWithScore` objects — `get_content()` and `score` extracted automatically

Note: the SDK accepts LangChain and LlamaIndex chunk objects passed manually inside a `with` block. It does not yet provide a zero-line LangChain callback handler or LlamaIndex event handler — those require you to call `trace.log_chunks()` explicitly with the chunks your retriever returns.

**Step 4: See the results**

Open `http://localhost:3000` → your project → Traces. Click a trace to see per-claim attribution with the retrieval-vs-generation distinction visible on every claim.

**Fallback: send a trace with curl (for testing without the SDK)**

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Authorization: Bearer cl_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the refund policy?",
    "chunks": [{
      "content": "Refunds are processed within 30 business days of purchase.",
      "source": "refund-policy.pdf",
      "chunk_index": 0
    }],
    "response": "Your refund will be processed in 30 days."
  }'
```

The API returns immediately (`202 Accepted`) with a `trace_id`. Processing runs in the background in the Celery worker and takes 5–10 seconds.

---

## What the Developer Sees

The trace detail page shows each claim with its full diagnosis. Here is what a real mixed-result trace looks like:

```
Query: "What is the refund policy?"

✓  "You can get a full refund within 30 days of purchase."
   Source: refund-policy.pdf, chunk 0   Score: 0.88 (high)
   Verdict: faithful

⚠  "Cancellations require 7 days notice before the next billing cycle."
   Source: terms-of-service.pdf, chunk 2   Score: 0.90 (high)
   Verdict: partial
   Judge: [source: "...must be submitted at least 7 business days..."]
          The claim drops the qualifier 'business' from '7 business days'.
   → GENERATION FAILURE — source was retrieved; the AI misrepresented it

✗  "Refunds are processed within 2 to 3 business days."
   Source: none found
   Verdict: unfaithful
   → RETRIEVAL FAILURE — no matching document was in the retrieved context
```

The dashboard also shows:
- **Amber "Low confidence match"** for claims attributed with moderate certainty (score 0.65–0.74) — these are linked to a source and go through faithfulness scoring, but the match is less certain than a high-confidence attribution
- **"Declined"** for claims where the LLM correctly refused to answer because the retrieved context didn't cover the question — shown as a distinct state, not grouped with hallucinations

---

## How the SDK Stays Out of Your Way

Every key invariant from `docs/SDK.md` is validated and holds in production:

- The `with` block exits in under 1ms regardless of backend availability
- If the backend is unreachable, the SDK times out silently in the background thread — your application sees no error and no latency
- If `CONTEXTLENS_ENABLED=false`, the `with` block is a no-op with negligible overhead
- Exceptions inside your `with` block propagate normally — the SDK never suppresses them
- An unrecognized chunk format raises `ContextLensError` synchronously (a programming error during development, not a runtime infrastructure failure)

To check delivery stats in a batch script:

```python
stats = contextlens.get_stats()
# {'attempted': 14, 'delivered': 13, 'failed': 1}
```

`attempted` increments when a background send starts. `delivered` increments on any HTTP response from the backend. `failed` increments on network errors and timeouts. Counters reset on process restart.

---

## Features

**Attribution pipeline**
- Claim decomposition — every LLM response broken into atomic, self-contained claims
- Three-band confidence model: high (>= 0.75), low (0.65–0.74), no attribution (< 0.65)
- Faithfulness scoring for both high and low-confidence attributed claims
- Retrieval failure vs generation failure distinction on every claim
- Correct LLM refusals detected and shown as "Declined" — not as hallucinations

**Dashboard**
- Project list with per-project average faithfulness
- Trace list with filters (status, minimum faithfulness) and pagination
- Trace detail page with per-claim verdict, source chunk, judge reasoning, and failure type
- Problem documents view — ranked by unfaithful claim rate, for generation failures only
- Query clusters — automatically groups similar queries and labels them with an LLM-generated topic label; runs every 6 hours
- Usage page — daily processing count vs limit, 7-day bar chart

**Project and API key management**
- Multiple named projects, each isolated
- API keys are hashed at rest — the raw key is shown once at creation
- Keys can be revoked without affecting other keys in the same project
- New API keys take effect immediately; revoked keys are rejected with 401

**Rate limiting and reliability**
- Per-minute and per-hour ingest rate limits enforced at the API level (configurable in `.env`)
- Daily processing limit — traces are always ingested and stored when the limit is hit; processing pauses gracefully and resumes the next day. The calling application always receives `202`, never an error.
- Pending trace recovery — a nightly scheduled task re-enqueues traces that were ingested but not processed

**Retry and fault tolerance**
- Failed Celery tasks retry with exponential backoff (60s, 120s, 240s)
- Tasks that exhaust retries are marked `failed` in the database with an error message

---

## Deployment Model

ContextLens is **self-hosted**. The entire stack runs on your machine or your server:

```
Your infrastructure
├── FastAPI  (port 8000)  — ingest + management API
├── Celery worker         — async attribution pipeline
├── Celery beat           — scheduled recovery + clustering jobs
├── Postgres + pgvector   — all data storage
├── Redis                 — job queue + rate limiting windows
└── Next.js  (port 3000)  — dashboard
```

**Your data never leaves your infrastructure.**
**Your LLM API key is yours — you pay OpenAI directly.**
**ContextLens costs you nothing to run beyond your own OpenAI usage.**

---

## Current Limitations

Two failure modes are understood, documented, and correctly out of scope for the current architecture:

**Chunk granularity dilution.** When a single source chunk covers multiple distinct policy topics in one dense paragraph, a claim about any single topic within it may score below the attribution threshold even though the information is technically present in the chunk. The full-paragraph embedding is distributed across all its sentences; a one-topic claim cannot sustain cosine similarity > 0.65 against that centroid. The low-confidence band (0.65–0.74) captures many of these cases, but claims that land below 0.65 appear as retrieval failures. The correct long-term fix is sentence-level chunk splitting at ingestion time — a retrieval architecture change, not a pipeline change.

**Generation incompleteness.** ContextLens cannot detect when the LLM generates a true-but-incomplete claim that drops a real qualifier from the source. For example: source says "annual plans are non-refundable but the subscription remains active for the full 12-month period"; LLM says "annual plans are non-refundable." The claim is true as far as it goes, but it drops material information. The claim embedding is pulled away from the source chunk embedding by the dropped content, so attribution may fail — not because the source wasn't there, but because the claim doesn't cover enough of it. The faithfulness judge only runs on attributed claims, so a dropped claim never reaches the judge. There is currently no signal for this failure mode.

Both limitations are visible in the test corpus results in `build-log.md` with specific scores and trace IDs.

---

## Tech Stack

| Component | Technology | Entry point |
|---|---|---|
| SDK | Python, `contextlens` package | `sdk/contextlens/__init__.py` |
| Backend API | FastAPI + asyncpg | `backend/app/main.py` |
| Async Worker | Celery | `backend/app/worker/tasks.py` |
| Job Queue + Rate Limiting | Redis | `backend/app/redis.py` |
| Database | Postgres + pgvector | `backend/app/database.py` |
| Migrations | Alembic | `backend/alembic/versions/` |
| Dashboard | Next.js + TypeScript + Tailwind | `frontend/app/` |

Python 3.11+. Node 18+. Postgres 16 (`pgvector/pgvector:pg16`). Redis 7.

---

## Documentation

| File | What it covers |
|---|---|
| `docs/ARCHITECTURE.md` | System design, components, data flow |
| `docs/DATA_MODEL.md` | Full database schema with explanation |
| `docs/PIPELINE.md` | The attribution pipeline in detail |
| `docs/SDK.md` | Python SDK — integration patterns and internals |
| `docs/API.md` | All API endpoints with request/response examples |
| `docs/DASHBOARD.md` | Frontend views and component structure |
| `docs/METERING.md` | Rate limiting and abuse prevention |
| `docs/STACK.md` | Technology choices and reasoning |
| `docs/DECISIONS.md` | Key product and architecture decisions |
| `docs/CLOUD_FUTURE.md` | How to extend this to a cloud SaaS |
| `build-log.md` | Complete build history with validation evidence |

---

## What Is Deliberately Not in This Architecture

These are intentionally out of scope and planned for later:

- Multi-user accounts and organizations
- Cloud hosting and managed deployment
- Stripe billing or paid plans
- SSO or enterprise auth

See `docs/CLOUD_FUTURE.md` for exactly how each gets added when the time comes.

---

## Environment Variables

```bash
OPENAI_API_KEY=sk-...              # required — used by the Celery worker
CONTEXTLENS_LOCAL_API_KEY=...      # legacy dev key — not used for ingest auth in Phase 2+
DAILY_PROCESSING_LIMIT=10000       # set to 0 to disable; traces always stored regardless
HOURLY_INGEST_RATE_LIMIT=500       # requests per hour per project
PER_MINUTE_RATE_LIMIT=100          # requests per minute per project
CLUSTERING_MIN_TRACES=10           # minimum traces before clustering runs
CLUSTERING_K=8                     # maximum number of query clusters per project
```

See `.env.example` for the full list with defaults.
