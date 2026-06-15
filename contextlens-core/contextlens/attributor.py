"""
Attributes each claim to its best-matching chunk using cosine similarity.

A claim with no chunk scoring above THRESHOLD is a retrieval failure — the right
document was never fetched. This is a first-class signal, not an error.
"""

import numpy as np

THRESHOLD = 0.75


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a)
    vb = np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def attribute(
    claim_embeddings: list[list[float]],
    chunk_embeddings: list[list[float]],
    chunks: list[dict],
) -> list[dict]:
    """
    Returns one attribution dict per claim:
        {
            "chunk": dict | None,   # the best matching chunk, or None
            "score": float,         # best cosine score (0.0 if no match)
        }
    """
    results = []
    for claim_emb in claim_embeddings:
        best_score = 0.0
        best_chunk = None
        for chunk_emb, chunk in zip(chunk_embeddings, chunks):
            score = _cosine_similarity(claim_emb, chunk_emb)
            if score > best_score:
                best_score = score
                best_chunk = chunk
        if best_score < THRESHOLD:
            results.append({"chunk": None, "score": best_score})
        else:
            results.append({"chunk": best_chunk, "score": best_score})
    return results
