"""
Attributes a claim to its best-matching chunk using cosine similarity.
Pure numpy — no pgvector. pgvector is used for storage; attribution is computed here.
Ported from contextlens-core.

A claim with no chunk scoring above ATTRIBUTION_THRESHOLD is a retrieval failure.
This is a first-class signal, not an error.
"""

import numpy as np

ATTRIBUTION_THRESHOLD = 0.75


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def attribute_claim(
    claim_embedding: list[float],
    chunk_embeddings: list[list[float]],
) -> tuple[int | None, float | None]:
    """
    Returns (chunk_index, score) where chunk_index is the index into the chunks list.
    Returns (None, None) if no chunk scores above ATTRIBUTION_THRESHOLD.
    """
    if not chunk_embeddings:
        return None, None

    best_score = 0.0
    best_idx = 0

    for i, chunk_emb in enumerate(chunk_embeddings):
        score = _cosine_similarity(claim_embedding, chunk_emb)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score < ATTRIBUTION_THRESHOLD:
        return None, None

    return best_idx, best_score
