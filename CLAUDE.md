# ContextLens — Developer Guide

ContextLens is a self-hosted developer tool that diagnoses AI hallucinations in RAG systems by making the critical distinction explicit: **did the retriever fail to find the right document, or did the AI find it and misrepresent it?** These two failure types look identical from the outside but need completely different fixes. ContextLens separates them by instrumenting the pipeline, decomposing every LLM response into atomic claims, attributing each claim back to its source document chunk, and scoring whether the AI accurately represented that chunk.

**Status:** Pre-build. All architecture, data model, API, and pipeline decisions are fully documented. No code exists yet. Start from Phase 1 of `docs/BUILD_ORDER.md`.

---

## How to Run

```bash
cp .env.example .env        # fill in OPENAI_API_KEY at minimum
docker-compose up           # starts all 5 services
# API:       http://localhost:8000
# Dashboard: http://localhost:3000
```

Run database migrations (first time only):
```bash
docker-compose exec api alembic upgrade head
```

---

## Docs Map

Read these in order for a full picture. Each doc is self-contained.

| File | What it covers |
|---|---|
| `CLAUDE.md` | This file — entry point, how to run, docs map |
| `docs/BUILD_ORDER.md` | **Start here to build.** Exact phases, week by week, with milestones and folder structure |
| `docs/ARCHITECTURE.md` | System design, all components, data flow, auth model, docker-compose |
| `docs/PIPELINE.md` | The attribution pipeline in full detail — claim decomposition, embedding, attribution, faithfulness scoring, clustering |
| `docs/DATA_MODEL.md` | Full database schema with every table, column, and rationale |
| `docs/SDK.md` | Python SDK — integration patterns, fire-and-forget internals, LangChain/LlamaIndex integrations |
| `docs/API.md` | All API endpoints with request/response examples |
| `docs/DASHBOARD.md` | All dashboard views with wireframes and component details |
| `docs/AUTH.md` | Auth model — self-hosted (minimal) and cloud (full JWT) |
| `docs/METERING.md` | Rate limiting and abuse prevention |
| `docs/STACK.md` | Every technology choice and the reasoning behind it |
| `docs/DECISIONS.md` | Key product and architecture decisions with full reasoning |
| `docs/CLOUD_FUTURE.md` | Exact migration path from self-hosted to cloud SaaS |
| `docs/archive/PRODUCT_OVERVIEW.md` | Non-technical product description — pre-build artifact, archived |

---

## Build Order Summary

Full detail in `docs/BUILD_ORDER.md`. Phases must be built in order — each phase depends on the previous.

| Phase | What Gets Built | Done When |
|---|---|---|
| 1 (Weeks 1–3) | Core pipeline — ingest → Celery worker → claims + scores | `curl POST /ingest` → `GET /traces/{id}` returns claims with scores |
| 2 (Week 4) | Projects + API key auth | SDK authenticates, traces are project-scoped |
| 3 (Weeks 5–6) | Dashboard — trace detail page | Per-claim attribution visible in browser |
| 4 (Weeks 7–8) | Analytics, clustering, rate limiting, polish | Full product works end to end |
| 5 (Future) | Cloud / multi-user | Not now — see `docs/CLOUD_FUTURE.md` |

---

## Key Invariants — Never Violate These

1. **SDK never blocks the RAG app.** All trace sending is fire-and-forget in a daemon thread. The SDK catches all exceptions silently.

2. **Ingest API returns immediately.** `POST /ingest` stores the trace and enqueues a job. It never waits for LLM processing. Always returns 202.

3. **Pipeline runs async in the Celery worker.** Claim decomposition + faithfulness scoring takes 5–10 seconds. Never process inline.

4. **Data never leaves the developer's machine.** No telemetry, no central service, no external calls except the developer's own OpenAI API key.

5. **Null attribution is a first-class signal — not an error.** A claim with no attributed chunk means the retriever failed, not that the pipeline failed. Surface it clearly in the dashboard as a retrieval failure. Do not treat it as a processing error.

6. **The retrieval vs generation split must always be explicit.** Every flagged claim falls into one of two categories: the source was never retrieved (retrieval failure — fix the search) or the source was retrieved but misrepresented (generation failure — fix the prompt). The dashboard and API responses must make this distinction clear on every claim. Never collapse them into a single score without exposing the underlying category.

7. **Claim embeddings and chunk embeddings must use the same model.** Comparing embeddings from different models produces meaningless similarity scores. Default is `text-embedding-3-small`. If the user's RAG system uses a different model, configure `CONTEXTLENS_EMBEDDING_MODEL` to match.

---

## Tech Stack Quick Reference

| Component | Technology | Entry point |
|---|---|---|
| SDK | Python, `contextlens/` package | `sdk/contextlens/__init__.py` |
| Backend API | FastAPI + asyncpg | `backend/app/main.py` |
| Async Worker | Celery | `backend/app/worker/tasks.py` |
| Job Queue + Rate Limiting | Redis | `backend/app/redis.py` |
| Database | Postgres + pgvector | `backend/app/database.py` |
| Migrations | Alembic | `backend/alembic/versions/` |
| Dashboard | Next.js + TypeScript + Tailwind | `frontend/app/` |

---

## Environment Variables

See `.env.example` for the full list. Minimum to get started:

```bash
OPENAI_API_KEY=sk-...          # required — used by the Celery worker for LLM calls
CONTEXTLENS_LOCAL_API_KEY=...  # any string — SDK uses this to authenticate with ingest API
```

---

## Python & Node Versions

- Python: **3.11+**
- Node: **18+**
- Postgres: **16** (pgvector image: `pgvector/pgvector:pg16`)
- Redis: **7**
