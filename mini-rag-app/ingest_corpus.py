"""
One-time corpus ingestion: chunk documents, embed via OpenAI, cache to JSON.

Run once before using the RAG app:
    python mini-rag-app/ingest_corpus.py

Chunking strategy: paragraph-based (split on double-newlines). Each paragraph
that is at least 80 characters becomes its own chunk. Shorter paragraphs (e.g.
headings) are prepended to the following paragraph. This keeps semantically
coherent units together while avoiding heading-only chunks that have no
retrievable content.

Embeddings: text-embedding-3-small, consistent with the rest of this project.
Corpus is cached to mini-rag-app/corpus_embeddings.json so subsequent runs
don't re-embed. Delete the JSON file to force re-ingestion.
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load parent .env first (OPENAI_API_KEY lives there), then local .env
    # (CONTEXTLENS_API_KEY). Local values take precedence via override=False default.
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    print("openai package not installed. Run: pip install openai")
    sys.exit(1)

DOCUMENTS_DIR = Path(__file__).parent / "documents"
OUTPUT_FILE = Path(__file__).parent / "corpus_embeddings.json"
EMBEDDING_MODEL = "text-embedding-3-small"
MIN_CHUNK_CHARS = 80


def chunk_document(text: str, source: str) -> list[dict]:
    """Split a document into paragraph-based chunks."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    pending = ""

    for para in paragraphs:
        combined = (pending + " " + para).strip() if pending else para
        if len(para) < MIN_CHUNK_CHARS:
            # Short paragraph (likely a heading) — carry it forward
            pending = combined
        else:
            chunks.append(combined)
            pending = ""

    if pending:
        # Flush any trailing short paragraph
        if chunks:
            chunks[-1] = chunks[-1] + " " + pending
        else:
            chunks.append(pending)

    return [
        {"content": c, "source": source, "chunk_index": i}
        for i, c in enumerate(chunks)
    ]


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Retries once on rate limit."""
    try:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in resp.data]
    except Exception as e:
        print(f"  Embedding error: {e}. Retrying in 5s...")
        time.sleep(5)
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in resp.data]


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set. Add it to mini-rag-app/.env")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    doc_files = sorted(DOCUMENTS_DIR.glob("*.md"))
    if not doc_files:
        print(f"ERROR: No .md files found in {DOCUMENTS_DIR}")
        sys.exit(1)

    print(f"Found {len(doc_files)} documents. Chunking...")
    all_chunks = []
    for path in doc_files:
        text = path.read_text(encoding="utf-8")
        chunks = chunk_document(text, source=path.name)
        all_chunks.extend(chunks)
        print(f"  {path.name}: {len(chunks)} chunks")

    print(f"\nTotal chunks: {len(all_chunks)}")
    print(f"Embedding via {EMBEDDING_MODEL}...")

    texts = [c["content"] for c in all_chunks]
    # Embed in one batch (all chunks comfortably fit within token limits)
    embeddings = embed_texts(client, texts)

    for chunk, embedding in zip(all_chunks, embeddings):
        chunk["embedding"] = embedding

    OUTPUT_FILE.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"\nSaved {len(all_chunks)} chunks to {OUTPUT_FILE}")
    print("Corpus ready. Run app.py or run_queries.py to start querying.")


if __name__ == "__main__":
    main()
