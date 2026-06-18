"""
Mini RAG app — ties retriever + generator + ContextLens SDK together.

This is the manual trace() pattern exactly as documented in SDK.md, used
exactly as a developer integrating ContextLens into an existing RAG app
would use it: retrieval and generation are written as if ContextLens didn't
exist, then the trace() wrapper is added around them.
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import contextlens
import generator as gen
import retriever as ret


def answer_query(query: str, k: int = 3) -> dict:
    """Answer a query and return response + retrieved chunks + trace_id."""
    with contextlens.trace(query=query) as trace:
        chunks = ret.retrieve(query, k=k)
        trace.log_chunks(chunks)
        response = gen.generate(query, chunks)
        trace.log_response(response)

    return {
        "query": query,
        "chunks": chunks,
        "response": response,
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How long do I have to request a refund?"
    result = answer_query(q)
    print(f"Query: {result['query']}\n")
    print("Retrieved chunks:")
    for i, c in enumerate(result["chunks"], 1):
        print(f"  [{i}] score={c['retriever_score']:.4f}  {c['source']}")
        print(f"      {c['content'][:100]}...")
    print(f"\nResponse:\n{result['response']}")
