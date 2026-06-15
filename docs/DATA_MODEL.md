# Data Model

This document explains every database table, every column, and why each piece of data exists.

---

## Design Principle: Tables Come From the Pipeline

We derive the schema by tracing what happens during one RAG query:

```
User query arrives
  → Retriever fetches chunks          → store: query + chunks
  → LLM generates response            → store: the response
  → We decompose into claims          → store: each claim
  → We attribute each claim           → store: claim → chunk link + score
  → We score faithfulness             → store: faithfulness score + reasoning
  → We cluster similar queries        → store: cluster metadata
```

Plus the identity layer:

```
What project is this trace for?   → projects, api_keys (local)
How much has been processed?      → usage_records
```

---

## Self-Hosted Schema (Current)

No user accounts. No auth tables. Minimal identity layer.

### `projects`

One row per RAG application being monitored.
In self-hosted mode, all projects belong to the single local user.

```sql
CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,        -- "Customer Support Bot"
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Note: No `user_id` column in self-hosted mode. When cloud is added,
this column is added via migration and all existing rows get the
first registered user's ID assigned.

---

### `api_keys`

The local API key(s) that the SDK uses to authenticate with the ingest endpoint.

```sql
CREATE TABLE api_keys (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  key_hash     TEXT NOT NULL UNIQUE,  -- SHA256 of the key, never the raw key
  key_prefix   TEXT NOT NULL,         -- first 16 chars, shown in dashboard
  name         TEXT NOT NULL,         -- "Local Dev Key", "Staging Key"
  last_used_at TIMESTAMPTZ,
  revoked_at   TIMESTAMPTZ,           -- null = active
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Even in self-hosted mode we store only the hash — good practice that
carries forward cleanly to the cloud version.

---

### `traces`

One row per RAG query that was instrumented. The top-level record.
Everything else (claims) hangs off this.

```sql
CREATE TABLE traces (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  query_text       TEXT NOT NULL,
  query_embedding  vector(1536),      -- set after ingestion, used for clustering
  retrieved_chunks JSONB NOT NULL,    -- the raw chunks from the retriever
  llm_response     TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
                   -- 'pending' | 'processing' | 'processed' | 'failed'
  latency_ms       INTEGER,           -- RAG app's total response time
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_traces_project_id  ON traces(project_id);
CREATE INDEX idx_traces_created_at  ON traces(created_at DESC);
CREATE INDEX idx_traces_status      ON traces(status);
```

**Why store `retrieved_chunks` as JSONB?**
The SDK sends chunks as a JSON array. Storing as JSONB preserves structure,
allows querying inside the array if needed, and avoids an unnecessary join
just to reconstruct raw retriever output.

**Why `status`?**
The ingest API stores with `pending`. Worker sets `processing` when it starts,
`processed` when done, `failed` after retries exhausted. The dashboard uses
this to show processing state and to identify stuck traces.

---

### `chunks`

One row per unique document chunk. Deduplicated across traces —
if the same chunk is retrieved 1,000 times, it's stored once.

```sql
CREATE TABLE chunks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  content         TEXT NOT NULL,
  content_hash    TEXT NOT NULL,           -- SHA256, for deduplication
  source_document TEXT NOT NULL,           -- "refund-policy.pdf"
  chunk_index     INTEGER,                 -- position within document
  embedding       vector(1536) NOT NULL,   -- for pgvector similarity search
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(project_id, content_hash)
);

CREATE INDEX idx_chunks_project_id ON chunks(project_id);

-- pgvector approximate nearest neighbor index
-- IVFFlat: good balance of speed and memory for our scale
CREATE INDEX idx_chunks_embedding ON chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

**Why deduplicate?**
The same chunk from `refund-policy.pdf` may be retrieved thousands of times.
Storing it once saves space and makes attribution queries clean —
we join once to get the source document name and content.

**Why IVFFlat and not HNSW?**
IVFFlat uses less memory and is simpler to tune. HNSW is faster for queries
but uses significantly more memory. At our scale, IVFFlat is the right default.
Migrate to HNSW if similarity search latency becomes a bottleneck.

---

### `claims`

One row per atomic claim extracted from a trace's LLM response.
This is the core table — it holds the attribution and faithfulness results.

```sql
CREATE TABLE claims (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id             UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
  claim_text           TEXT NOT NULL,       -- "The refund window is 30 days."
  claim_index          INTEGER NOT NULL,    -- order in the response (0, 1, 2...)
  attributed_chunk_id  UUID REFERENCES chunks(id),  -- null = no source found
  attribution_score    FLOAT,               -- cosine similarity (0.0–1.0), null if no match
  faithfulness_verdict TEXT,               -- 'faithful' | 'partial' | 'unfaithful'
  faithfulness_score   FLOAT,              -- 0.0–1.0
  is_faithful          BOOLEAN,            -- simple true/false for filtering
  judge_reasoning      TEXT,               -- LLM judge's explanation
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claims_trace_id        ON claims(trace_id);
CREATE INDEX idx_claims_attributed_chunk ON claims(attributed_chunk_id);
CREATE INDEX idx_claims_is_faithful     ON claims(is_faithful);
```

**Why is `attributed_chunk_id` nullable?**
A null here is one of the most important signals in the whole system.
It means the LLM generated a claim with no grounding in the retrieved context —
pure hallucination from training data. Null attribution + unfaithful = the
clearest hallucination signal we produce.

**Why store `judge_reasoning`?**
The LLM judge explains *why* a claim was marked unfaithful, not just that it was.
"The chunk says 30 business days, the claim omits 'business'" is actionable.
A score of 0.3 alone is not. The reasoning is what makes the dashboard useful.

---

### `query_clusters`

One row per group of semantically similar queries.
Computed by a periodic background job, not on every request.

```sql
CREATE TABLE query_clusters (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  cluster_label       TEXT NOT NULL,          -- "questions about billing and refunds"
  centroid_embedding  vector(1536) NOT NULL,  -- average of all query embeddings in cluster
  avg_faithfulness    FLOAT NOT NULL,
  trace_count         INTEGER NOT NULL DEFAULT 0,
  unfaithful_count    INTEGER NOT NULL DEFAULT 0,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_clusters_project_id ON query_clusters(project_id);
```

**Why a table and not a view?**
Clustering is expensive — k-means over all query embeddings.
We compute it as a scheduled Celery beat job and store the results.
The dashboard reads pre-computed results, not live aggregations.

---

### `usage_records`

Tracks daily processing volume per project.
Used for rate limiting and abuse detection — not billing.

```sql
CREATE TABLE usage_records (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  date               DATE NOT NULL,
  traces_ingested    INTEGER NOT NULL DEFAULT 0,
  traces_processed   INTEGER NOT NULL DEFAULT 0,
  flagged            BOOLEAN NOT NULL DEFAULT FALSE,
  flag_reason        TEXT,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(project_id, date)
);
```

Note: In self-hosted mode this is per-project, not per-user.
In the cloud version, a `user_id` column is added and limits
are enforced at the user level.

---

## Table Relationships

```
projects
  ├── api_keys          (one project → many keys)
  ├── usage_records     (one project → one record per day)
  ├── chunks            (one project → many chunks)
  ├── query_clusters    (one project → many clusters)
  └── traces            (one project → many traces)
        └── claims      (one trace → many claims)
              └── chunks (each claim attributed to one chunk)
```

---

## The Key Diagnostic Query

Powers the "which documents are causing the most hallucinations?" view:

```sql
SELECT
  c.source_document,
  COUNT(*)                                                    AS total_claims,
  SUM(CASE WHEN cl.is_faithful = FALSE THEN 1 ELSE 0 END)    AS unfaithful_claims,
  ROUND(AVG(cl.faithfulness_score)::numeric, 2)              AS avg_faithfulness
FROM claims cl
JOIN chunks c ON cl.attributed_chunk_id = c.id
WHERE c.project_id = :project_id
  AND cl.created_at > NOW() - INTERVAL '7 days'
GROUP BY c.source_document
ORDER BY unfaithful_claims DESC
LIMIT 20;
```

---

## Cloud Migration Path

When moving to a multi-user cloud version, these additions are made via Alembic migrations:

```sql
-- 1. add users table
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE,
  hashed_password TEXT NOT NULL,
  verified        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. add user ownership to projects
ALTER TABLE projects ADD COLUMN user_id UUID REFERENCES users(id);

-- 3. add auth tables
CREATE TABLE email_verification_tokens (...);
CREATE TABLE password_reset_tokens (...);
CREATE TABLE refresh_tokens (...);

-- 4. update api_keys to be more granular
-- (already structured correctly — no changes needed)

-- 5. update usage_records to track per-user
ALTER TABLE usage_records ADD COLUMN user_id UUID REFERENCES users(id);
```

Existing self-hosted data survives the migration intact.
A seeded "local user" row gets assigned to all existing projects.

---

## Migrations

We use **Alembic** for all schema changes.

```
alembic/
  env.py
  versions/
    0001_initial_schema.py     ← self-hosted schema
    0002_add_users_auth.py     ← cloud migration (future)
    ...
```

Never alter the schema by hand in production.
Every change is a versioned, reviewable migration file.
