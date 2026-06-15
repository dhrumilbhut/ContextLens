# ContextLens

> **ContextLens tells you whether your RAG system failed to find the right document, or found it and the AI ignored it. These need completely different fixes. No current tool makes this distinction.**

Self-hosted. Your data never leaves your infrastructure. You bring your own LLM API key.

---

## The Problem

You've built a RAG system — a chatbot or document QA app that retrieves chunks from a knowledge base and feeds them to an LLM to generate answers. Sometimes the LLM gives wrong answers.

The frustrating part: **you have no idea why — and the fix depends entirely on the reason.**

If the right document was never retrieved, you fix your search. If the right document was retrieved and the AI ignored it, you fix your prompt. These are completely different problems. Current tools give you a single score that conflates them.

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

1. **Decomposing** every LLM response into atomic claims
2. **Attributing** each claim back to the specific retrieved chunk it came from (or flagging it as having no source)
3. **Scoring** whether that chunk actually supports the claim — catching subtle misrepresentations
4. **Aggregating** patterns across queries to surface systemic problems by topic

Instead of "faithfulness score: 0.6" you get:

> *"Claim 3 has no source chunk — your retriever never fetched the refund policy document for this query type. That's a retrieval failure. Fix your search. Claims 1 and 2 were retrieved correctly but the AI dropped 'business' from '30 business days'. That's a generation problem. Tighten your prompt."*

---

## The Two Root Causes (and a Third)

Every wrong answer from a RAG system comes from one of these:

```
No source chunk found          →  RETRIEVAL FAILURE   →  Fix search / chunking / embeddings
Source found, AI misread it    →  GENERATION FAILURE  →  Fix prompt / model
Source found, wrong document   →  ROUTING PROBLEM     →  Fix document metadata / recency
```

ContextLens tells you which one you're dealing with before you touch anything.

---

## Quickstart

```bash
# 1. clone
git clone https://github.com/yourname/contextlens
cd contextlens

# 2. configure — add your OpenAI key, nothing else required
cp .env.example .env

# 3. run
docker-compose up

# dashboard is now at http://localhost:3000
# API is now at http://localhost:8000
```

Then in your RAG app:

```bash
pip install contextlens
```

```python
import contextlens

with contextlens.trace(query=user_query) as trace:
    chunks = your_retriever.fetch(user_query)
    trace.log_chunks(chunks)
    response = your_llm.generate(chunks, user_query)
    trace.log_response(response)
```

Open `http://localhost:3000` and see your traces.

---

## Deployment Model

ContextLens is **self-hosted**. The entire stack runs on your machine or your server:

```
Your infrastructure
├── FastAPI  (port 8000)  — ingest + management API
├── Celery worker         — async attribution pipeline
├── Postgres + pgvector   — all data storage
├── Redis                 — job queue + rate limiting
└── Next.js  (port 3000)  — dashboard
```

**Your data never leaves your infrastructure.**
**Your LLM API key is yours — you pay OpenAI/Anthropic directly.**
**ContextLens costs you nothing to run.**

This is an intentional design decision. See `docs/DECISIONS.md` for the full reasoning.

---

## Documentation

```
README.md                     ← you are here
docs/
  ARCHITECTURE.md             ← system design, components, data flow
  DATA_MODEL.md               ← full database schema with explanation
  PIPELINE.md                 ← the attribution pipeline in detail
  SDK.md                      ← how the Python SDK works
  API.md                      ← all API endpoints
  DASHBOARD.md                ← frontend views and structure
  METERING.md                 ← local abuse prevention
  BUILD_ORDER.md              ← implementation phases and order
  STACK.md                    ← technology choices and reasoning
  DECISIONS.md                ← key product decisions and their reasoning
  CLOUD_FUTURE.md             ← how to extend this to a cloud SaaS later
```

---

## Tech Stack

| Component       | Technology            |
|-----------------|-----------------------|
| SDK             | Python                |
| Backend API     | Python + FastAPI      |
| Async Worker    | Python + Celery       |
| Job Broker      | Redis                 |
| Database        | Postgres + pgvector   |
| Dashboard       | Next.js (TypeScript)  |
| LLM Calls       | OpenAI / Anthropic    |
| Deployment      | Docker Compose        |

---

## Current Scope

ContextLens is intentionally scoped to work well as a self-hosted single-user tool first.
The following are deliberately out of scope for now and planned for later:

- Multi-user accounts / auth system
- Organizations / teams
- Cloud hosting
- Stripe billing / paid plans
- SSO

See `docs/CLOUD_FUTURE.md` for exactly how each of these gets added when the time comes.
