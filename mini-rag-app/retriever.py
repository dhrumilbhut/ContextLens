"""
Embedding-based retriever over the cached corpus.

Loads corpus_embeddings.json on first call (lazy, cached in module-level variable).
Retrieval: embed the query, compute cosine similarity against all chunk embeddings,
return top-k chunks with their similarity scores.
"""

import json
import math
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    print("openai package not installed.")
    sys.exit(1)

CORPUS_FILE = Path(__file__).parent / "corpus_embeddings.json"
EMBEDDING_MODEL = "text-embedding-3-small"

_corpus: list[dict] | None = None
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")
        _client = OpenAI(api_key=api_key)
    return _client


def _load_corpus() -> list[dict]:
    global _corpus
    if _corpus is None:
        if not CORPUS_FILE.exists():
            raise RuntimeError(
                f"Corpus not found at {CORPUS_FILE}. "
                "Run ingest_corpus.py first."
            )
        _corpus = json.loads(CORPUS_FILE.read_text(encoding="utf-8"))
    return _corpus


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    denom = _norm(a) * _norm(b)
    if denom == 0:
        return 0.0
    return _dot(a, b) / denom


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return top-k chunks most similar to query, each with a retriever_score."""
    client = _get_client()
    corpus = _load_corpus()

    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    query_embedding = resp.data[0].embedding

    scored = [
        {
            "content": chunk["content"],
            "source": chunk["source"],
            "chunk_index": chunk["chunk_index"],
            "retriever_score": cosine_similarity(query_embedding, chunk["embedding"]),
        }
        for chunk in corpus
    ]
    scored.sort(key=lambda c: c["retriever_score"], reverse=True)
    return scored[:k]


if __name__ == "__main__":
    # Quick standalone test
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How do I cancel my subscription?"
    print(f"Query: {q}\n")
    results = retrieve(q, k=3)
    for i, r in enumerate(results, 1):
        print(f"  [{i}] score={r['retriever_score']:.4f}  source={r['source']}")
        print(f"      {r['content'][:120]}...")
        print()
