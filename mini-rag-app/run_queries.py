"""
Batch query runner. Runs 14 test queries through the mini RAG app, prints
results to console, and saves a structured log to queries_run.json.

Query categories:
  - Straightforward queries with clear, well-supported answers (Q1-Q4)
  - Ambiguous-overlap queries spanning two documents (Q5-Q8)
  - No-document-exists queries (topics not covered by any document) (Q9-Q11)
  - Multi-part queries asking about two different things at once (Q12-Q14)

Run:
    python mini-rag-app/run_queries.py
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
import app as rag_app

QUERIES = [
    # ── Straightforward ──────────────────────────────────────────────────────
    {
        "id": "Q01",
        "category": "straightforward",
        "query": "How long do I have to request a refund after purchasing?",
    },
    {
        "id": "Q02",
        "category": "straightforward",
        "query": "How do I dispute a charge on my account?",
    },
    {
        "id": "Q03",
        "category": "straightforward",
        "query": "What are the response time expectations for support on a paid plan?",
    },
    {
        "id": "Q04",
        "category": "straightforward",
        "query": "How long does standard domestic shipping take?",
    },
    # ── Ambiguous overlap ────────────────────────────────────────────────────
    # These queries intentionally span two documents. The retriever will
    # likely pull from both, and ContextLens attribution should identify
    # which chunk was actually used in the generated claim.
    {
        "id": "Q05",
        "category": "ambiguous-overlap",
        "query": "If I downgrade my plan, when does the change take effect and do I get a refund for the unused time?",
    },
    {
        "id": "Q06",
        "category": "ambiguous-overlap",
        "query": "What happens to my account and data after I cancel my subscription?",
    },
    {
        "id": "Q07",
        "category": "ambiguous-overlap",
        "query": "Can I get a refund if I cancel my annual plan early?",
    },
    {
        "id": "Q08",
        "category": "ambiguous-overlap",
        "query": "How much notice do I need to give before switching from annual to monthly billing?",
    },
    # ── No document covers this ──────────────────────────────────────────────
    # Topics deliberately absent from the corpus. The LLM should decline
    # or hedge. ContextLens should mark any specific claims as retrieval failures.
    {
        "id": "Q09",
        "category": "no-document",
        "query": "What programming languages does your API support?",
    },
    {
        "id": "Q10",
        "category": "no-document",
        "query": "Do you offer a student or nonprofit discount?",
    },
    {
        "id": "Q11",
        "category": "no-document",
        "query": "Can I export my data to a CSV file?",
    },
    # ── Multi-part ───────────────────────────────────────────────────────────
    # Two distinct questions in one. The decomposer should separate these
    # into independent claims attributed to different source chunks.
    {
        "id": "Q12",
        "category": "multi-part",
        "query": "What is the refund window for digital products, and how long does standard shipping take?",
    },
    {
        "id": "Q13",
        "category": "multi-part",
        "query": "How do I contact support if I have a billing dispute, and what data do you keep after I delete my account?",
    },
    {
        "id": "Q14",
        "category": "multi-part",
        "query": "What happens if I miss the 30-day notice window for annual cancellation, and can I still downgrade to a lower plan instead?",
    },
]


def run():
    results = []
    total = len(QUERIES)

    print(f"Running {total} queries through the mini RAG app...\n")
    print("=" * 70)

    for i, q_def in enumerate(QUERIES, 1):
        print(f"\n[{i}/{total}] {q_def['id']} ({q_def['category']})")
        print(f"Query: {q_def['query']}")
        print("-" * 60)

        start = time.perf_counter()
        try:
            result = rag_app.answer_query(q_def["query"])
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            print("Retrieved chunks:")
            for j, chunk in enumerate(result["chunks"], 1):
                print(f"  [{j}] score={chunk['retriever_score']:.4f}  {chunk['source']}")
                print(f"      {chunk['content'][:100].replace(chr(10), ' ')}...")

            print(f"\nResponse ({elapsed_ms}ms):")
            print(f"  {result['response'][:300].replace(chr(10), ' | ')}")
            if len(result["response"]) > 300:
                print("  [... truncated]")

            results.append({
                "id": q_def["id"],
                "category": q_def["category"],
                "query": q_def["query"],
                "chunks": [
                    {
                        "source": c["source"],
                        "chunk_index": c["chunk_index"],
                        "retriever_score": round(c["retriever_score"], 4),
                        "content_preview": c["content"][:120],
                    }
                    for c in result["chunks"]
                ],
                "response": result["response"],
                "elapsed_ms": elapsed_ms,
                "trace_id": None,  # fill in from dashboard after processing
                "status": "sent",
            })

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            print(f"  ERROR: {e}")
            results.append({
                "id": q_def["id"],
                "category": q_def["category"],
                "query": q_def["query"],
                "error": str(e),
                "elapsed_ms": elapsed_ms,
                "status": "error",
            })

        # Brief pause between queries to avoid rate-limiting the embedding API
        if i < total:
            time.sleep(0.5)

    output_file = Path(__file__).parent / "queries_run.json"
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    sent = sum(1 for r in results if r["status"] == "sent")
    errors = sum(1 for r in results if r["status"] == "error")

    print("\n" + "=" * 70)
    print(f"Done. {sent}/{total} queries sent successfully, {errors} errors.")
    print(f"Log saved to {output_file}")
    print("\nWait ~30s for the pipeline to process all traces, then check the")
    print("dashboard for the 'Mini RAG Test App' project.")


if __name__ == "__main__":
    run()
