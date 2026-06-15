# Attribution Pipeline

This document explains exactly how ContextLens processes a raw trace into attributed, scored claims — step by step, with the reasoning behind every decision.

---

## Overview

The attribution pipeline is the core intelligence of ContextLens. It runs asynchronously in the Celery worker after a trace is ingested.

```
Raw trace (query + chunks + response)
  ↓
Step 1: Decompose response into atomic claims
  ↓
Step 2: Embed each claim
  ↓
Step 3: Attribute each claim to a source chunk (pgvector)
  ↓
Step 4: Score faithfulness per claim (LLM-as-judge)
  ↓
Processed trace (claims with attribution + faithfulness scores)
```

---

## Step 1: Claim Decomposition

### What It Does

Takes the LLM's response text and breaks it into individual factual statements.

**Input:**
```
"Your refund window is 30 days from the date of purchase.
Cancellation requires 7 days advance notice.
All refunds are processed within 5 business days."
```

**Output:**
```json
[
  "The refund window is 30 days from the date of purchase.",
  "Cancellation requires 7 days advance notice.",
  "Refunds are processed within 5 business days."
]
```

### Why Decompose?

A single LLM response contains multiple independent claims. If we scored faithfulness at the response level, we'd get one blended score that hides which specific claim is wrong. Claim-level decomposition lets us say "claim 3 is unfaithful" rather than "this response is 67% faithful."

### The LLM Call

```python
DECOMPOSE_PROMPT = """
You are a precise fact extractor. Given a text response, extract every
distinct factual claim it makes. Each claim must be:
- A single, self-contained sentence
- Expressing exactly one fact
- Faithful to what the text actually said (do not paraphrase or interpret)

Return a JSON array of claim strings. Nothing else.

Text to decompose:
{response_text}
"""

async def decompose_claims(response_text: str) -> list[str]:
    result = await llm_client.complete(
        model="gpt-4o-mini",          # cheap, fast, sufficient for extraction
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": DECOMPOSE_PROMPT.format(response_text=response_text)
        }]
    )
    data = json.loads(result.content)
    return data["claims"]  # list of strings
```

### Edge Cases

- **Very short responses ("Yes" / "No"):** These produce zero or one claim. That's fine — a one-word answer has nothing to attribute.
- **Responses with no factual claims (e.g., "I don't know"):** Returns empty list. Trace is marked as processed with zero claims.
- **LLM returns malformed JSON:** Caught by try/except, worker retries.

---

## Step 2: Claim Embedding

### What It Does

Converts each claim string into a vector (embedding) so we can compare it against chunk embeddings using cosine similarity.

```python
async def embed_claims(claims: list[str]) -> list[list[float]]:
    # batch embed all claims in one API call (cheaper than individual calls)
    result = await openai_client.embeddings.create(
        model="text-embedding-3-small",  # 1536 dimensions, cheap, fast
        input=claims
    )
    return [item.embedding for item in result.data]
```

### Why text-embedding-3-small?

- 1536 dimensions — same as what most RAG systems use for chunk embeddings
- This is important: claim embeddings and chunk embeddings must use the **same model**. Comparing embeddings from different models gives meaningless similarity scores.
- If the user's RAG system uses a different embedding model, we need to know. Future: let users configure their embedding model in project settings.

### Embedding Model Consistency — Critical

The chunks stored in our `chunks` table were embedded using the embedding model from the developer's RAG pipeline. For attribution to work correctly, we must embed claims using the **exact same model**. Comparing embeddings from different models produces meaningless cosine similarity scores — attribution will appear to fail randomly.

**Default:** `text-embedding-3-small` (configured via `CONTEXTLENS_EMBEDDING_MODEL` in `.env`).

**If the developer's RAG system uses a different embedding model** (e.g. `text-embedding-ada-002`, a local model via Ollama, Cohere embeddings), they must set `CONTEXTLENS_EMBEDDING_MODEL` to match before sending any traces. Changing the model mid-project requires re-embedding all stored chunks — there is no automatic migration.

The embedding model is read from `.env` at worker startup. It is used for both chunk embedding (on ingest) and claim embedding (during attribution).

---

## Step 3: Attribution (Finding the Source Chunk)

### What It Does

For each claim, finds the retrieved chunk that is most semantically similar to it. This is the "source" of the claim.

### The pgvector Query

```python
async def attribute_claim(
    claim_embedding: list[float],
    project_id: str,
    trace_id: str
) -> tuple[str | None, float | None]:
    """
    Returns (chunk_id, attribution_score) or (None, None) if no good match.
    """
    result = await db.fetchrow("""
        SELECT
            c.id,
            1 - (c.embedding <=> $1) AS similarity_score
        FROM chunks c
        JOIN traces t ON t.project_id = c.project_id
        WHERE t.id = $2
          AND c.project_id = $3
        ORDER BY c.embedding <=> $1
        LIMIT 1
    """, claim_embedding, trace_id, project_id)

    if not result:
        return None, None

    chunk_id = result["id"]
    score = result["similarity_score"]

    # if best match is below threshold, treat as unattributed
    if score < ATTRIBUTION_THRESHOLD:  # 0.75
        return None, score

    return chunk_id, score
```

### The Attribution Threshold

If the best matching chunk has a similarity score below **0.75**, we treat the claim as having no attributed source. This means:

- The claim has no semantic match in the retrieved context
- The LLM almost certainly generated this claim from its training data, not from the documents
- This is a **hallucination signal** — one of the most important outputs of the pipeline

The 0.75 threshold is configurable per project. Teams with domain-specific language (medical, legal) may need to tune this.

### What Attribution Score Means

```
1.0  — claim is almost verbatim from the chunk
0.9  — claim is a close paraphrase of chunk content
0.75 — claim is topically related to the chunk (our threshold)
0.5  — claim is vaguely related but probably not sourced from chunk
0.0  — claim has nothing to do with the chunk
```

---

## Step 4: Faithfulness Scoring (LLM-as-Judge)

### What It Does

Given a claim and its attributed chunk, asks an LLM: "Does this chunk actually support this claim?"

This is different from attribution score. Cosine similarity measures *topical similarity*. Faithfulness scoring measures *logical support*.

**Example where they diverge:**

- Chunk: "Refunds are processed within 30 *business* days."
- Claim: "Refunds are processed within 30 days."
- Attribution score: 0.95 (very similar — both about refund processing time)
- Faithfulness score: 0.3 (the claim drops "business" — a legally meaningful difference)

Attribution finds the right chunk. Faithfulness catches the subtle mismatch.

### The LLM Call

```python
FAITHFULNESS_PROMPT = """
You are a precise fact-checker. Given a source chunk and a claim, determine
whether the source chunk fully supports the claim.

Evaluate strictly:
- "faithful": the chunk explicitly states or clearly implies the claim
- "partial": the chunk partially supports the claim but there are gaps or nuances
- "unfaithful": the chunk does not support the claim, contradicts it, or the
  claim adds information not present in the chunk

Source chunk:
{chunk_content}

Claim to evaluate:
{claim_text}

Return a JSON object with exactly these fields:
{{
  "verdict": "faithful" | "partial" | "unfaithful",
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<one sentence explaining your verdict>"
}}
"""

async def score_faithfulness(
    claim_text: str,
    chunk_content: str
) -> dict:
    result = await llm_client.complete(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": FAITHFULNESS_PROMPT.format(
                chunk_content=chunk_content,
                claim_text=claim_text
            )
        }]
    )
    return json.loads(result.content)
    # returns: { "verdict": "unfaithful", "score": 0.1, "reasoning": "..." }
```

### Judge Reliability — Honest Assessment

A reasonable concern: if the judge is an LLM, can it also hallucinate?

Yes, it can. This is a real limitation and worth being direct about.

However, the task the judge is doing is fundamentally simpler than generating an answer:

**Generation (hard):** Given a question and some documents, produce an answer from scratch. The model must synthesize, reason, and generate — with many ways to go wrong.

**Judging (simpler):** Given a claim and a specific paragraph, does this paragraph support this claim? This is a constrained comparison task. The model doesn't need to know anything — it just needs to read two texts and assess alignment.

Constrained comparison tasks have significantly lower hallucination rates than open-ended generation. The judge isn't being asked to know things; it's being asked to notice whether two texts agree.

**Additionally — the failure mode is acceptable:**

The judge makes two types of errors:
- **False negative (missed detection):** Claims something faithful when it's not. The developer misses a bug.
- **False positive (false alarm):** Flags something as unfaithful when it's actually fine. The developer investigates a non-issue.

False negatives are annoying. False positives erode trust. The judge prompt is deliberately conservative — it only flags clearly unfaithful claims, erring toward false negatives over false positives. A bug the tool misses is less damaging than a tool developers stop trusting.

**And — every judgment is auditable:**

Unlike a black-box score, every verdict comes with `judge_reasoning` — a plain-English explanation stored in the database. Developers can spot-check the judge's reasoning on any flagged claim and verify it themselves. Errors are visible, not silent.

The goal is not a flawless oracle. It's something dramatically better than manually reading hundreds of conversation logs — which is what developers do today.

---

If a claim has no attributed chunk (attribution returned None), we skip the faithfulness call entirely and mark the claim as:

```json
{
  "attributed_chunk_id": null,
  "attribution_score": null,
  "faithfulness_verdict": "unfaithful",
  "faithfulness_score": 0.0,
  "is_faithful": false,
  "judge_reasoning": "No source chunk found — claim has no grounding in retrieved context."
}
```

No LLM call needed. No chunk = no faithfulness possible.

---

## The Two Root Causes (What the Pipeline Detects)

This is the core insight that makes ContextLens different from existing tools.
Two wrong answers can look identical from the outside but require completely different fixes.
The pipeline makes this distinction explicit on every claim.

### Failure Mode 1: Retrieval Failure

```
attribution_score: null or < 0.75
faithfulness_score: 0.0
```

**What happened:** The right document was never fetched. The LLM generated a claim with no grounding in the retrieved context at all — it came from training data, not your documents.

**Root causes:**
- The relevant document is missing from the knowledge base
- Semantic mismatch between query phrasing and document language — the retriever simply couldn't find it
- Chunking split the relevant content across two chunks, neither of which alone scored high enough

**Fix:** This is a search problem. Check if the document exists, try a different embedding model, add HyDE (hypothetical document embeddings), or fix chunking boundaries. Do not change your prompt — the retriever is what failed.

---

### Failure Mode 2: Generation Hallucination

```
attribution_score: > 0.85   (retriever found the right chunk)
faithfulness_score: < 0.4   (AI ignored or contradicted it)
```

**What happened:** The right document was retrieved. The LLM ignored it, contradicted it, or subtly misrepresented it — generating a claim from its training data instead of the provided context.

**Root cause:** LLM over-relying on training data instead of provided context. System prompt too permissive.

**Fix:** This is a prompt problem. Tighten the system prompt: "Only make claims explicitly stated in the provided context. Do not use outside knowledge." Swapping embedding models or adding documents will not help — the retriever did its job. The generation step failed.

---

### Failure Mode 3: Routing Problem (Stale Document)

```
attribution_score: > 0.85   (retriever found a chunk)
faithfulness_score: > 0.8   (AI accurately reflected it)
attributed_chunk: from "policy-2021.pdf" instead of "policy-2024.pdf"
```

**What happened:** The LLM accurately reflected a chunk, but the chunk was from a stale or incorrect document. The retriever ranked an outdated document above the current one.

**Root cause:** Outdated documents in the knowledge base competing with current documents. Retriever ranking doesn't account for recency.

**Fix:** Remove or re-tag stale documents. Add recency weighting to retriever. The scores all look good at the trace level — this failure only becomes visible in the cluster view, where a whole topic consistently returns low-quality answers from the same old document.

---

### Why This Split Matters

Most observability tools give you one score per response. That score conflates all three failure modes. A developer looking at "faithfulness: 0.6" cannot tell whether to fix their search, their prompt, or their documents — so they guess.

ContextLens always tells you which category you're in before you touch anything:

```
null attribution          → don't touch the prompt. Fix the retriever.
high attribution + low faith  → don't touch the retriever. Fix the prompt.
high attribution + high faith + wrong doc → don't touch either. Fix document hygiene.
```

---

## Full Worker Code (Pseudocode)

```python
@celery.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
async def process_trace(self, trace_id: str):
    try:
        # 1. fetch raw trace
        trace = await db.get_trace(trace_id)
        if not trace:
            return  # trace was deleted, skip

        # 2. update status
        await db.update_trace_status(trace_id, "processing")

        # 3. decompose claims
        claims_text = await decompose_claims(trace.llm_response)
        if not claims_text:
            await db.update_trace_status(trace_id, "processed")
            return  # no claims to process

        # 4. embed claims (batch)
        claim_embeddings = await embed_claims(claims_text)

        # 5. process each claim
        for index, (claim_text, claim_embedding) in enumerate(
            zip(claims_text, claim_embeddings)
        ):
            # attribute
            chunk_id, attribution_score = await attribute_claim(
                claim_embedding, trace.project_id, trace_id
            )

            # score faithfulness
            if chunk_id:
                chunk = await db.get_chunk(chunk_id)
                faith_result = await score_faithfulness(claim_text, chunk.content)
            else:
                faith_result = {
                    "verdict": "unfaithful",
                    "score": 0.0,
                    "reasoning": "No source chunk found in retrieved context."
                }

            # store claim
            await db.create_claim(
                trace_id=trace_id,
                claim_text=claim_text,
                claim_index=index,
                attributed_chunk_id=chunk_id,
                attribution_score=attribution_score,
                faithfulness_verdict=faith_result["verdict"],
                faithfulness_score=faith_result["score"],
                is_faithful=faith_result["verdict"] == "faithful",
                judge_reasoning=faith_result["reasoning"]
            )

        # 6. mark done
        await db.update_trace_status(trace_id, "processed")

    except Exception as exc:
        # retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=60 * (2 ** self.request.retries)
        )
```

---

## LLM Cost Per Trace

Approximate costs using GPT-4o-mini:

```
Claim decomposition:   ~400 tokens in, ~150 tokens out  → ~$0.0001
Claim embedding:       ~50 tokens per claim × 3 claims  → ~$0.000015
Faithfulness scoring:  ~300 tokens in, ~60 tokens out per claim × 3 → ~$0.0003

Total per trace: ~$0.0005 (half a cent)
```

At 1,000 traces/day: ~$0.50/day
At 10,000 traces/day: ~$5.00/day

These costs are why usage metering matters — without limits, a single abusive user could generate significant LLM costs.

---

## The Clustering Pipeline (Celery Beat Job)

Query clustering groups semantically similar queries together so the developer can see which *topics* their AI struggles with, not just which individual queries failed.

### Schedule

Configured via `.env`:

```bash
CLUSTERING_INTERVAL_SECONDS=21600   # run every 6 hours (default)
CLUSTERING_MIN_TRACES=20            # skip if fewer than this many traces exist
CLUSTERING_K=8                      # number of clusters per project
```

Celery beat schedule definition:

```python
# app/worker/celery_app.py

from celery.schedules import crontab
import os

app.conf.beat_schedule = {
    "cluster-queries-every-6-hours": {
        "task": "app.worker.tasks.cluster_queries_all_projects",
        "schedule": int(os.getenv("CLUSTERING_INTERVAL_SECONDS", 21600)),
    }
}
```

### Algorithm

```python
@celery.task
async def cluster_queries_all_projects():
    projects = await db.get_all_projects()
    for project in projects:
        await cluster_queries_for_project(project.id)


async def cluster_queries_for_project(project_id: str):
    # 1. fetch all query embeddings for this project
    rows = await db.fetchall("""
        SELECT id, query_embedding
        FROM traces
        WHERE project_id = $1
          AND query_embedding IS NOT NULL
          AND status = 'processed'
    """, project_id)

    if len(rows) < settings.CLUSTERING_MIN_TRACES:
        return  # not enough data yet

    # 2. run k-means
    import numpy as np
    from sklearn.cluster import KMeans

    embeddings = np.array([r["query_embedding"] for r in rows])
    k = min(settings.CLUSTERING_K, len(rows))  # can't have more clusters than points

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    # 3. group trace IDs by cluster label
    clusters: dict[int, list[str]] = {}
    for i, row in enumerate(rows):
        clusters.setdefault(labels[i], []).append(row["id"])

    # 4. for each cluster: compute stats + ask LLM to label it
    for cluster_idx, trace_ids in clusters.items():
        centroid = kmeans.cluster_centers_[cluster_idx].tolist()

        # get sample queries to show the LLM (up to 10)
        sample_queries = await db.fetchall("""
            SELECT query_text FROM traces
            WHERE id = ANY($1)
            ORDER BY created_at DESC
            LIMIT 10
        """, trace_ids)

        # compute faithfulness stats for this cluster
        stats = await db.fetchrow("""
            SELECT
                COUNT(DISTINCT t.id) AS trace_count,
                AVG(cl.faithfulness_score) AS avg_faithfulness,
                SUM(CASE WHEN cl.is_faithful = FALSE THEN 1 ELSE 0 END) AS unfaithful_count
            FROM traces t
            JOIN claims cl ON cl.trace_id = t.id
            WHERE t.id = ANY($1)
        """, trace_ids)

        # ask LLM to label this cluster
        label = await label_cluster([q["query_text"] for q in sample_queries])

        # upsert into query_clusters
        await db.execute("""
            INSERT INTO query_clusters
              (project_id, cluster_label, centroid_embedding, avg_faithfulness,
               trace_count, unfaithful_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (project_id, cluster_label)
            DO UPDATE SET
              centroid_embedding = EXCLUDED.centroid_embedding,
              avg_faithfulness   = EXCLUDED.avg_faithfulness,
              trace_count        = EXCLUDED.trace_count,
              unfaithful_count   = EXCLUDED.unfaithful_count,
              updated_at         = NOW()
        """, project_id, label, centroid,
             stats["avg_faithfulness"], stats["trace_count"], stats["unfaithful_count"])
```

### Cluster Labeling LLM Call

```python
CLUSTER_LABEL_PROMPT = """
You are given a list of user queries sent to an AI assistant.
These queries were grouped together because they are semantically similar.

Write a short label (3-6 words) that describes what topic these queries share.
The label should be lowercase and descriptive, like:
  "questions about billing and refunds"
  "shipping and delivery questions"
  "account login and password issues"

Queries:
{queries}

Return only the label string. Nothing else.
"""

async def label_cluster(sample_queries: list[str]) -> str:
    queries_text = "\n".join(f"- {q}" for q in sample_queries)
    result = await llm_client.complete(
        model=settings.DECOMPOSE_MODEL,
        messages=[{
            "role": "user",
            "content": CLUSTER_LABEL_PROMPT.format(queries=queries_text)
        }]
    )
    return result.content.strip().strip('"')
```

### Stale Cluster Handling

Clusters are fully recomputed on every run — old rows for a project are deleted and replaced. K-means always produces a fresh partition of all current traces.

```python
# before upserting new clusters, delete old ones for this project
await db.execute(
    "DELETE FROM query_clusters WHERE project_id = $1", project_id
)
# then insert the new clusters computed above
```

### Note on `query_clusters` Unique Constraint

The upsert above uses `(project_id, cluster_label)` as the conflict target. Add this unique constraint to the schema:

```sql
ALTER TABLE query_clusters ADD CONSTRAINT uq_cluster_project_label
  UNIQUE (project_id, cluster_label);
```
