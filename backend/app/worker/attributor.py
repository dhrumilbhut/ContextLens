"""
Attributes a claim to its best-matching chunk using cosine similarity.
Pure numpy — no pgvector. pgvector is used for storage; attribution is computed here.

Three-band confidence model (as of 0006 migration):
  score >= 0.75           → 'high' confidence (well-attributed)
  0.65 <= score < 0.75   → 'low' confidence (probably right source, embedding distance uncertain)
  score < 0.65            → None (retrieval failure — no plausible source found)

Null attribution is a first-class signal, not an error.
"""

import numpy as np

ATTRIBUTION_THRESHOLD = 0.75        # high confidence — existing meaning unchanged
LOW_CONFIDENCE_THRESHOLD = 0.65     # new lower band


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def attribute_claim(
    claim_embedding: list[float],
    chunk_embeddings: list[list[float]],
) -> tuple[int | None, float | None, str | None]:
    """
    Returns (chunk_index, score, confidence).

    confidence is 'high', 'low', or None:
      'high' — score >= ATTRIBUTION_THRESHOLD (0.75)
      'low'  — score >= LOW_CONFIDENCE_THRESHOLD (0.65) and < ATTRIBUTION_THRESHOLD
      None   — score < LOW_CONFIDENCE_THRESHOLD; chunk_index and score are also None

    For low-confidence results, chunk_index IS populated (the best-matching chunk
    is returned) so the judge can evaluate faithfulness against a real source.
    The confidence label travels through to the claim record so the dashboard
    can surface it distinctly from high-confidence attributions.
    """
    if not chunk_embeddings:
        return None, None, None

    best_score = 0.0
    best_idx = 0

    for i, chunk_emb in enumerate(chunk_embeddings):
        score = _cosine_similarity(claim_embedding, chunk_emb)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score >= ATTRIBUTION_THRESHOLD:
        return best_idx, best_score, "high"

    if best_score >= LOW_CONFIDENCE_THRESHOLD:
        return best_idx, best_score, "low"

    return None, None, None
