# Key Decisions

This document records the major product and architecture decisions made for ContextLens,
the reasoning behind each, and what was explicitly ruled out. This is useful context
for anyone (including Claude Code) working on this codebase.

---

## Decision 1: Self-Hosted First, Not Cloud SaaS

**What we decided:**
Build ContextLens as a self-hosted tool that runs via Docker Compose on the
developer's own machine. No central cloud service. No user accounts. No hosting costs.

**Why:**

*The pipeline is the impressive part — not the auth system.*
The attribution pipeline (claim decomposition, pgvector similarity, LLM-as-judge)
is the technical depth that matters. A cloud SaaS would require spending 30–40% of
build time on JWT tokens, email verification, Stripe integration, and hosting
infrastructure — none of which demonstrates RAG expertise.

*Data privacy objection is eliminated.*
Developers building RAG systems on sensitive data (healthcare, legal, fintech)
cannot send production queries to a third-party cloud service. Self-hosted removes
this objection entirely. The data never leaves their infrastructure.

*Zero ongoing costs.*
The developer pays their own OpenAI bill. We incur zero LLM cost, zero hosting cost,
zero operational burden.

*Right audience.*
The target user is a backend/applied AI engineer. They have Docker installed.
They are comfortable with `docker-compose up`. A localhost-first tool is a natural fit.

**What we ruled out:**
- Building cloud SaaS first and adding self-hosted later (reversed priority)
- Skipping Docker and asking developers to install dependencies manually
- Building a "lite" version without Docker for maximum simplicity
  (rejected because environment inconsistency across Mac/Linux/Windows would
  create more support burden than Docker solves)

**Future implication:**
The cloud version is deliberately designed as an additive layer, not a rewrite.
See `CLOUD_FUTURE.md`.

---

## Decision 2: No User Auth in Self-Hosted Version

**What we decided:**
No signup, no login, no JWT, no sessions. The dashboard at `localhost:3000`
is accessible without authentication. The ingest API uses a single shared
local key from `.env`.

**Why:**

*Single user.*
There is exactly one user of a self-hosted instance — the developer running it.
An auth system would protect against no real threat while adding a week of build time.

*Localhost is authorization.*
If someone can access `localhost:3000`, they already have access to the machine.
A login screen in that context is security theater.

*Build time is finite.*
Spending a week on bcrypt, JWT, refresh tokens, email verification, and password
reset flows means one fewer week on the attribution pipeline, dashboard quality,
or developer experience. The pipeline is what matters.

**The local API key on the ingest route:**
We do use a single shared key for the ingest route. This is not security —
it's consistency. The SDK is written to always send an Authorization header.
Keeping that pattern means the cloud version's ingest route works the same way,
just with a different backend lookup. Zero code change to the SDK between
self-hosted and cloud.

**What we ruled out:**
- Optional auth (add login if you want it) — too much complexity for marginal benefit
- Token-based dashboard auth without accounts — pointless on localhost
- OAuth-only (Google login) — still requires user tables and session management

---

## Decision 3: pgvector Instead of a Dedicated Vector Database

**What we decided:**
Use PostgreSQL + pgvector for all data, including vector storage and similarity search.
No Pinecone, Qdrant, Weaviate, or other dedicated vector database.

**Why:**

*One service instead of two.*
Adding a dedicated vector DB means running another Docker container, managing
another connection pool, duplicating chunk data between two stores, and learning
another query interface. pgvector gives us vector similarity search inside the
database we're already running.

*Sufficient at our scale.*
pgvector with an IVFFlat index handles millions of vectors efficiently.
Our use case (chunks from one developer's knowledge base) is well within
pgvector's capabilities. Dedicated vector DBs become worthwhile at 100M+ vectors
or when you need specialized features (metadata filtering, multi-tenancy at DB level).
We don't need either.

*Simpler backup and restore.*
One `pg_dump` backs up everything — relational data and vectors together.
With a separate vector DB, you need to coordinate backups across two systems.

**What we ruled out:**
- Qdrant (good product, but another service to run and operate)
- Pinecone (managed cloud, not self-hostable, SaaS dependency)
- Weaviate (heavy, complex, overkill for our scale)
- ChromaDB (SQLite-backed, good for prototypes but not production-grade)

---

## Decision 4: Celery + Redis for Async Processing

**What we decided:**
Use Celery with Redis as the broker for the attribution pipeline.
Processing is fully async — the ingest API returns immediately, the worker
processes in the background.

**Why:**

*The pipeline cannot run synchronously.*
Claim decomposition + faithfulness scoring takes 5–10 seconds (two LLM API calls).
If we processed inline in the ingest route, the SDK would block for that long,
making the developer's RAG app noticeably slower. That violates the core SDK
contract: zero performance impact.

*Celery is the right tool for this job.*
Python-native, mature, handles retries with exponential backoff, supports
scheduled jobs (for the clustering task), works with Redis out of the box.

*Redis is already in the stack.*
We use Redis for rate limiting. Adding Celery broker support costs nothing —
it's configuration, not another service.

**What we ruled out:**
- Postgres as the job queue (using a jobs table with SELECT FOR UPDATE SKIP LOCKED)
  — works but slower and more complex than Redis for this use case
- asyncio background tasks in FastAPI — no retry logic, no persistence across restarts
- RabbitMQ — more powerful routing but another service; we don't need the extra features
- Dramatiq — good alternative to Celery but less ecosystem support

---

## Decision 5: Claim-Level Attribution, Not Response-Level

**What we decided:**
Decompose every LLM response into atomic claims, attribute and score each claim
individually — not the response as a whole.

**Why:**

*The retrieval vs generation split requires claim-level data.*
This is the most important reason. A wrong answer can mean the retriever failed (right document was never fetched) or generation failed (right document was there and the AI ignored it). These need completely different fixes. Response-level scoring blurs them into one number. Claim-level attribution makes the distinction explicit: a claim either has a source chunk or it doesn't. If it has one, faithfulness scoring tells you whether the AI accurately represented it. You always know which problem you're dealing with.

*Response-level scores are not actionable.*
"Faithfulness: 0.6" tells you something is wrong. It doesn't tell you which claim is wrong, which chunk it came from, or which of the two root causes you're dealing with. A developer cannot act on a score alone — they still have to manually investigate.

*Claim-level attribution is surgical.*
"Claim 3 has no source chunk — this is a retrieval failure" tells you exactly what is wrong and exactly what to fix. The developer doesn't have to guess.

**What we ruled out:**
- Sentence-level scoring without claim decomposition — sentences are too ambiguous ("The answer is yes" is a sentence but not an attributable claim)
- Paragraph-level attribution — too coarse, a paragraph can contain both faithful and unfaithful claims
- Response-level only — fast to compute but conflates the two root causes, making it not actionable

---

## Decision 6: LLM-as-Judge for Faithfulness, Not NLI Models

**What we decided:**
Use an LLM (gpt-4o-mini) as the faithfulness judge, not a fine-tuned
Natural Language Inference (NLI) model.

**Why:**

*LLMs understand nuance that NLI models miss.*
NLI models are trained to detect entailment at a surface level.
An LLM-as-judge can catch subtle misfacts: "30 days" vs "30 business days",
implications vs explicit statements, numbers that are close but wrong.
These nuances matter for faithfulness.

*LLMs explain their reasoning.*
An NLI model outputs a probability. An LLM outputs a verdict AND an explanation:
"The chunk says 30 business days, the claim omits 'business'."
The explanation is what makes the dashboard actionable — not just a score.

*Simpler to deploy.*
Running an NLI model requires a GPU or a model hosting service. An OpenAI API call
requires an API key the developer already has. In a self-hosted tool that should
be simple to run, adding a GPU-dependent model is the wrong trade-off.

**Known limitation — can the judge itself hallucinate?**

Yes. This is a real and honest concern that comes up frequently and deserves a direct answer.

The judge can be wrong. However, the task it's performing is fundamentally simpler than generating an answer. It's not being asked to know things or reason from scratch — it's being asked "does this sentence match what this paragraph says." Constrained comparison tasks have significantly lower hallucination rates than open-ended generation.

Two additional mitigations:

First, the failure mode is deliberately conservative. The judge prompt errs toward false negatives (missing a real problem) rather than false positives (flagging something that's fine). A bug the tool misses is less damaging than a tool developers stop trusting because it keeps raising false alarms.

Second, every judgment is auditable. The `judge_reasoning` field stores the judge's plain-English explanation alongside every verdict. Developers can spot-check any flagged claim and verify it themselves. Errors are visible and correctable, not silent.

The goal is not a flawless oracle. It is something dramatically better than the alternative, which is manually reading through hundreds of conversation logs — which is what developers currently do.

**What we ruled out:**
- Fine-tuned NLI models (simpler-qa, true-nli) — less nuanced, no reasoning output
- Cross-encoder models — same issues as NLI, GPU dependency
- Rule-based fact checking — too brittle for natural language variation
- gpt-4o for the judge — more accurate but ~10x more expensive; gpt-4o-mini is
  sufficient for binary faithfulness verdicts

---

## Decision 7: IVFFlat Index over HNSW for pgvector

**What we decided:**
Use IVFFlat as the pgvector index type for chunk embeddings.

**Why:**

*IVFFlat uses significantly less memory.*
HNSW builds a graph structure that can use 10–100x more memory than IVFFlat
at scale. For a self-hosted tool running on a developer's laptop, memory matters.

*IVFFlat is sufficient for our query pattern.*
We run similarity search against a bounded set of chunks (one project's knowledge base,
typically hundreds to tens of thousands of chunks). At this scale, IVFFlat query
latency is well within acceptable bounds (milliseconds).

*Easier to rebuild.*
When new chunks are added, IVFFlat indexes can be rebuilt more efficiently than HNSW.

**Migration path to HNSW:**
If a user has a very large knowledge base and similarity search latency becomes
a bottleneck, migrating is a one-line index replacement:
```sql
DROP INDEX idx_chunks_embedding;
CREATE INDEX idx_chunks_embedding ON chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

**What we ruled out:**
- HNSW as default (faster queries but higher memory, overkill for typical self-hosted scale)
- No index (exact search) — fine for very small datasets but doesn't scale

---

## Decision 8: Three-Band Attribution Confidence Model

**What we decided:**
Attribution is not binary. When a claim's cosine similarity to its best-matching chunk falls in the 0.65–0.74 range, we assign it a real chunk, run it through the faithfulness judge, and store it with `attribution_confidence = 'low'`. Scores at or above 0.75 are `'high'`. Scores below 0.65 remain retrieval failures with null attribution. The dashboard surfaces low-confidence claims with an amber "Low confidence match" badge rather than treating them identically to either clear matches or missing sources.

**Why:**

*The 0.75 threshold was calibrated on synthetic near-verbatim data, not real LLM output.*
The original threshold was set using claim texts that closely paraphrased single source sentences. Real LLM responses are different: the model reads a multi-sentence paragraph and generates paraphrased sub-claims that cover one point from that paragraph. When you embed such a claim and compare it against the full-paragraph chunk embedding, the claim's vector is pulled away from the centroid by all the sentences in the paragraph it does not cover. The result is that correctly-attributed claims score in the 0.65–0.75 range rather than 0.85+. Q12 is the cleanest example: the shipping claim ("Standard shipping takes 5–7 business days for domestic orders within the continental United States") scored 0.7336 against its source chunk in Phase D — the same claim text, the same chunk, a real attribution, and wrong classification as a retrieval failure. Q13's billing email claim scored 0.7242 under the same conditions. Both were correctly attributable; both were being discarded before the faithfulness judge ran.

*Conflating no-source with imperfect-match produces the wrong signal.*
A claim with no retrieved source is a retrieval failure — the fix is to improve search, chunking, or embedding strategy. A claim with a source at 0.70 cosine similarity is not a retrieval failure — the source was found; the uncertainty is in the attribution precision, not in whether the retriever did its job. Collapsing both into a single "retrieval failure" bucket tells the developer to fix their search when the problem may be the prompt or the chunk granularity. The confidence band makes the distinction explicit without requiring a judgment call from the developer.

*The fix had to be additive, not a threshold change.*
Lowering the threshold globally from 0.75 to 0.65 would have affected every claim in the system — including claims that genuinely score in the 0.65–0.74 range because there is no good source. The band preserves the semantics of the existing thresholds at both endpoints: high-confidence behavior is unchanged, and null attribution below 0.65 is still the correct signal for genuine retrieval failures. The new band adds a third state without disrupting the two that already exist.

*Three rounds of work were needed, and the validation history is honest about this.*
Phase D added the low-confidence band and validated it against the Q06 trace — but the validation compared Phase D's naturally-regenerated 4-claim response against Phase C's original 5-claim trace, not the same response text. The Phase D build log declared the fix validated; the Phase D audit session (a separate session with no new feature code) ran the exact Phase C response text through the Phase D pipeline and found that the original Q06 sub-claims — "automatically downgrade to the free tier" (0.6491 in the pipeline batch) and "If the free tier is not available, access will be suspended" (0.6446) — were still below 0.65. The low-confidence band does not help when sub-claim fragmentation pushes individual fragments below the threshold; it only helps when the claim is a complete paraphrase of a single source point. Q12 and Q13 were genuine Phase D fixes. Q06's "downgrade or suspend" case required Phase E's decomposer COMBINE rules, which merged the two fragments into one claim scoring 0.7114. Q14's enumeration fragments required Phase F's additional COMBINE rules before attribution could reach the judge at all. The confidence band and the decomposer fixes are complementary — neither is sufficient alone for the full class of failures the build surfaced.

**Known limitation — chunk granularity dilution and generation completeness:**

Two categories of claim remain correctly unattributed after all fixes and cannot be resolved at the decomposer or threshold level.

The first is chunk granularity dilution. Q06's data retention claim — "Your data will be retained for 90 days after the end of the paid period, after which it is subject to deletion" — is a single combined claim (correctly merged in Phase E) that scores 0.5831 against its source chunk. The source chunk covers three distinct policy topics: access retention, free-tier downgrade, and data retention. The chunk embedding is distributed across all three topics; a claim that covers only one of them cannot sustain cosine similarity above 0.65 against that centroid. This is not a decomposer problem and not a threshold problem. The fix would be sentence-level chunk splitting at ingest time so that each embedded chunk covers exactly one policy point. That is a retrieval architecture change, not a pipeline change, and it is deferred.

The second is generation completeness. Q07's claim "After 14 days, annual plans are non-refundable" scores 0.6099 and remains a retrieval failure in the dashboard. The source chunk says "After 14 days, annual plans are non-refundable but the subscription remains active for the full 12-month period." The LLM generated a true but incomplete claim — it dropped the second half of the source sentence. The resulting claim embedding is pulled away from the source chunk embedding by the dropped content. No decomposer rule can reintroduce text the LLM never generated. The correct fix is upstream: improve the LLM prompt to preserve qualifiers. ContextLens correctly surfaces this as an unattributed claim, which gives the developer the right signal — something about this claim does not match the retrieved context — even though the root cause is LLM truncation rather than retrieval failure.

Both limitations are documented in the dashboard's "How to interpret results" copy and in the README's "Current Limitations" section.

**What we ruled out:**
- Lowering the global attribution threshold from 0.75 to 0.64 or 0.65 — this would classify claims that genuinely have no good source as attributed, producing false positives in the faithfulness judge and noise in the "retrieval failure" signal. The Q06 claim edge case (0.6491 in the pipeline batch, 0.0009 below the 0.65 floor) was examined and ruled out as justification for a global threshold shift. One claim at the boundary is not evidence that 0.65 is the wrong floor.
- Sentence-level chunk splitting at ingest time as the first response to Phase C failures — this would have been the right long-term fix for chunk granularity dilution, but it requires changes to the ingestion architecture and affects every user's existing chunk data. The confidence band was the correct first fix: additive, non-breaking, and immediately useful for the class of failures it does address (complete paraphrases of single-point sources). Ingest-time sentence splitting remains the correct next step if chunk granularity dilution proves to be the dominant failure mode in practice.
- Accepting Phase D's initial validation without a controlled audit — the Phase D build log declared Q06 fixed based on a comparison that used different LLM response text in the "before" and "after" cases. The correct response to the discrepancy (5 claims in Phase C vs 4 in Phase D, with the Phase D log describing the remaining NULLs as "correct" without explaining what happened to the Phase C sub-claims) was to stop and audit before proceeding to Phase E. The audit session confirmed which fixes were genuine (Q12, Q13) and which required additional decomposer work (Q06, Q07), which correctly directed Phase E and F's scope.
