# API Reference

All endpoints, their inputs, outputs, and auth requirements.

---

## Base URL

```
Local (self-hosted):  http://localhost:8000
Cloud (future):       https://api.contextlens.dev
```

---

## Auth Model (Self-Hosted)

```
POST /ingest              → Authorization: Bearer <project_api_key>
All other routes          → No auth required (localhost assumption)
```

Project API keys are generated through the dashboard (Settings > API Keys)
or via `POST /projects/{id}/api-keys`. The raw key is shown once at creation
and never again — only the SHA256 hash is stored. Keys are prefixed with `cl_`.

Set the key in the SDK with the `CONTEXTLENS_API_KEY` environment variable
or by calling `contextlens.configure(api_key="cl_...")` directly.

When the cloud version is added, management routes will require
`Authorization: Bearer <jwt_access_token>`. See `CLOUD_FUTURE.md`.

---

## Project Routes

### GET /projects

List all projects.

**Response 200:**
```json
{
  "projects": [
    {
      "id": "proj_abc123",
      "name": "Customer Support Bot",
      "description": "Internal support chatbot",
      "trace_count": 1847,
      "avg_faithfulness": 0.73,
      "created_at": "2026-05-01T10:00:00Z"
    }
  ]
}
```

---

### POST /projects

Create a new project.

**Request:**
```json
{
  "name": "Customer Support Bot",
  "description": "Optional description"
}
```

**Response 201:**
```json
{
  "id": "proj_abc123",
  "name": "Customer Support Bot",
  "created_at": "2026-06-04T10:00:00Z"
}
```

---

### GET /projects/{project_id}

Get a single project with summary stats.

**Response 200:**
```json
{
  "id": "proj_abc123",
  "name": "Customer Support Bot",
  "trace_count": 1847,
  "avg_faithfulness_7d": 0.73,
  "unfaithful_claim_rate": 0.18,
  "top_problem_documents": [
    { "source": "old-policy.pdf", "unfaithful_claims": 47 }
  ]
}
```

---

### DELETE /projects/{project_id}

Delete a project and all its data. Irreversible.

**Response 200:**
```json
{ "message": "Project deleted." }
```

---

## API Key Routes

### GET /projects/{project_id}/api-keys

List API keys for a project (raw key never shown — only prefix and metadata).

**Response 200:**
```json
{
  "api_keys": [
    {
      "id": "key_abc123",
      "name": "Local Dev Key",
      "key_prefix": "cl_proj_abc1...",
      "last_used_at": "2026-06-04T09:00:00Z",
      "revoked_at": null,
      "created_at": "2026-05-01T10:00:00Z"
    }
  ]
}
```

---

### POST /projects/{project_id}/api-keys

Create a new API key. **Raw key returned exactly once — store it now.**

**Request:**
```json
{ "name": "Local Dev Key" }
```

**Response 201:**
```json
{
  "id": "key_abc123",
  "name": "Local Dev Key",
  "key": "cl_proj_abc123xyz...",
  "key_prefix": "cl_proj_abc1..."
}
```

---

### DELETE /projects/{project_id}/api-keys/{key_id}

Revoke an API key. Stops working immediately.

**Response 200:**
```json
{ "message": "API key revoked." }
```

---

## Ingest Route

### POST /ingest

Receive a trace from the SDK. Stores it and enqueues for processing.

**Auth:** `Authorization: Bearer <local_api_key>`

**Request:**
```json
{
  "query": "What is the refund policy?",
  "chunks": [
    {
      "content": "Refunds are processed within 30 business days.",
      "source": "refund-policy.pdf",
      "chunk_index": 3,
      "retriever_score": 0.89
    }
  ],
  "response": "Your refund window is 30 days...",
  "latency_ms": 1243
}
```

**Response 202** (accepted, queued for processing):
```json
{
  "trace_id": "tr_abc123",
  "status": "pending"
}
```

**Response 401:** Invalid or revoked API key
```json
{ "detail": "Invalid API key" }
```

**Response 429:** Per-minute or per-hour rate limit exceeded
```json
{ "detail": "Rate limit exceeded: too many requests per minute" }
```
Rate limits are configured via `PER_MINUTE_RATE_LIMIT` and `HOURLY_INGEST_RATE_LIMIT` in `.env`.
The daily processing limit does **not** return 429 — traces are always accepted and stored
with `status: pending`; processing is deferred until the next day's limit resets.

---

## Trace Routes

### GET /projects/{project_id}/traces

List recent traces with summary info.

**Query params:**
- `limit` (default: 50, max: 200)
- `offset` (default: 0)
- `status` — `pending` | `processing` | `processed` | `failed`
- `min_faithfulness` — float 0.0–1.0

**Response 200:**
```json
{
  "traces": [
    {
      "id": "tr_abc123",
      "query_text": "What is the refund policy?",
      "status": "processed",
      "claim_count": 3,
      "faithful_claim_count": 2,
      "avg_faithfulness": 0.67,
      "created_at": "2026-06-04T09:00:00Z"
    }
  ],
  "total": 1847
}
```

---

### GET /projects/{project_id}/traces/{trace_id}

Full trace detail with all claims and attribution.

**Response 200:**
```json
{
  "id": "tr_abc123",
  "query_text": "What is the refund policy?",
  "llm_response": "Your refund window is 30 days...",
  "status": "processed",
  "latency_ms": 1243,
  "created_at": "2026-06-04T09:00:00Z",
  "claims": [
    {
      "id": "cl_abc123",
      "claim_text": "The refund window is 30 days from purchase.",
      "claim_index": 0,
      "attribution": {
        "chunk_id": "ch_abc123",
        "chunk_content": "Returns must be initiated within 30 days of purchase.",
        "source_document": "refund-policy.pdf",
        "chunk_index": 1,
        "attribution_score": 0.91,
        "confidence": "high"
      },
      "faithfulness_verdict": "partial",
      "faithfulness_score": 0.6,
      "is_faithful": false,
      "judge_reasoning": "[source: \"Returns must be initiated within 30 days of purchase.\"] The chunk says 'initiate a return' but the claim states the refund is 'processed' within 30 days — these are different things."
    },
    {
      "id": "cl_def456",
      "claim_text": "Cancellations require 7 days notice before the next billing cycle.",
      "claim_index": 1,
      "attribution": {
        "chunk_id": "ch_def456",
        "chunk_content": "Subscription cancellations must be submitted at least 7 business days before the next billing cycle.",
        "source_document": "terms-of-service.pdf",
        "chunk_index": 2,
        "attribution_score": 0.71,
        "confidence": "low"
      },
      "faithfulness_verdict": "partial",
      "faithfulness_score": 0.7,
      "is_faithful": false,
      "judge_reasoning": "[source: \"...must be submitted at least 7 business days...\"] The claim drops the qualifier 'business' from '7 business days'."
    },
    {
      "id": "cl_ghi789",
      "claim_text": "No information about enterprise pricing was found in the provided context.",
      "claim_index": 2,
      "attribution": null,
      "faithfulness_verdict": "refusal",
      "faithfulness_score": null,
      "is_faithful": null,
      "judge_reasoning": "LLM correctly declined to answer — no relevant context was retrieved."
    }
  ]
}
```

**`faithfulness_verdict` values:**
- `faithful` — claim accurately reflects the attributed source chunk
- `partial` — claim was attributed but contains an inaccuracy (qualifier dropped, number changed, etc.)
- `unfaithful` — no source chunk was found (retrieval failure); `attribution` is null
- `refusal` — the LLM explicitly declined to answer because the retrieved context did not cover the question. For refusal claims: `attribution` is null, `faithfulness_score` is null, `is_faithful` is null, and `judge_reasoning` holds the fixed string `"LLM correctly declined to answer — no relevant context was retrieved."` rather than LLM-generated reasoning. Refusals are distinct from hallucinations — both show null attribution, but a refusal means the system is working correctly.

**`attribution.confidence` values:**
- `high` — attribution score >= 0.75; clear match
- `low` — attribution score 0.65–0.74; real source found but match is less certain; claim still goes through the faithfulness judge
- `null` (field absent or attribution object null) — no source found above threshold

---

## Analytics Routes

### GET /projects/{project_id}/clusters

Query clusters with faithfulness stats.

**Response 200:**
```json
{
  "clusters": [
    {
      "id": "clust_abc123",
      "label": "questions about billing and refunds",
      "trace_count": 234,
      "avg_faithfulness": 0.58,
      "unfaithful_rate": 0.34
    }
  ]
}
```

---

### GET /projects/{project_id}/documents/problems

Source documents ranked by unfaithful claim count.

**Query params:**
- `days` (default: 7)
- `limit` (default: 20)

**Response 200:**
```json
{
  "documents": [
    {
      "source_document": "old-policy-2021.pdf",
      "total_claims": 89,
      "unfaithful_claims": 47,
      "unfaithful_rate": 0.53,
      "avg_faithfulness": 0.41
    }
  ]
}
```

---

### GET /projects/{project_id}/usage

Daily usage stats for a project.

**Response 200:**
```json
{
  "today": {
    "traces_ingested": 847,
    "traces_processed": 847,
    "processing_limit": 10000,
    "limit_reached": false
  },
  "last_7_days": [
    { "date": "2026-06-04", "traces_processed": 847 },
    { "date": "2026-06-03", "traces_processed": 1203 }
  ]
}
```

---

## Health Route

### GET /health

Status of all system components.

**Response 200:**
```json
{
  "status": "ok",
  "components": {
    "database": "ok",
    "redis": "ok",
    "worker": "ok"
  },
  "version": "0.1.0"
}
```

**Response 503** (component down):
```json
{
  "status": "degraded",
  "components": {
    "database": "ok",
    "redis": "error",
    "worker": "unknown"
  }
}
```
