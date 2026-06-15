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
POST /ingest              → Authorization: Bearer <local_api_key>
All other routes          → No auth required (localhost assumption)
```

The local API key is set in `.env` as `CONTEXTLENS_LOCAL_API_KEY`
and in the SDK's environment as `CONTEXTLENS_API_KEY`.

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

**Response 401:** Invalid API key

**Response 429:** Rate limit exceeded

---

## Trace Routes

### GET /projects/{project_id}/traces

List recent traces with summary info.

**Query params:**
- `limit` (default: 50, max: 200)
- `offset` (default: 0)
- `status` — `pending` | `processing` | `processed` | `failed`
- `min_faithfulness` — float 0.0–1.0
- `from` — ISO date
- `to` — ISO date

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
        "attribution_score": 0.91
      },
      "faithfulness_verdict": "partial",
      "faithfulness_score": 0.6,
      "is_faithful": false,
      "judge_reasoning": "The chunk says 'initiate a return within 30 days' but the claim states the refund is processed within 30 days — these are different things."
    }
  ]
}
```

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
