"""
Orchestrates the full attribution pipeline:
    LLM response -> claims -> embeddings -> attribution -> faithfulness judgement
"""

from contextlens.decomposer import decompose
from contextlens.embedder import embed
from contextlens.attributor import attribute
from contextlens.judge import judge


def run_pipeline(query: str, chunks: list[dict], llm_response: str) -> list[dict]:
    """
    Returns one result dict per claim:
        {
            "claim":            str,
            "attribution":      {"chunk": dict | None, "score": float},
            "verdict":          "faithful" | "partial" | "unfaithful",
            "faithfulness_score": float,
            "reason":           str,
            "failure_type":     "retrieval" | "generation" | None,
        }
    """
    print("Decomposing response into claims...")
    claims = decompose(llm_response)
    if not claims:
        return []

    print(f"Embedding {len(claims)} claims and {len(chunks)} chunks...")
    chunk_texts = [c["text"] for c in chunks]
    all_texts = claims + chunk_texts
    all_embeddings = embed(all_texts)
    claim_embeddings = all_embeddings[: len(claims)]
    chunk_embeddings = all_embeddings[len(claims) :]

    print("Attributing claims to source chunks...")
    attributions = attribute(claim_embeddings, chunk_embeddings, chunks)

    print("Judging faithfulness...")
    results = []
    for claim, attribution in zip(claims, attributions):
        judgement = judge(claim, attribution["chunk"])
        results.append(
            {
                "claim": claim,
                "attribution": attribution,
                "verdict": judgement["verdict"],
                "faithfulness_score": judgement["score"],
                "reason": judgement["reason"],
                "failure_type": judgement["failure_type"],
            }
        )

    return results
