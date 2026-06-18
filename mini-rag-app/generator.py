"""
LLM response generator. Given a query and retrieved chunks, calls gpt-4o-mini
and returns the generated response string.

The prompt is deliberately average — straightforward instruction to use the
provided context, no chain-of-thought prompting, no explicit hedging instruction.
This is what a real mid-tier RAG app would use, and it's what ContextLens
should be tested against.
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

try:
    from openai import OpenAI
except ImportError:
    print("openai package not installed.")
    sys.exit(1)

MODEL = "gpt-4o-mini"

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set.")
        _client = OpenAI(api_key=api_key)
    return _client


def generate(query: str, chunks: list[dict]) -> str:
    """Generate a response to query given the retrieved chunks."""
    client = _get_client()

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Source {i}: {chunk['source']}]\n{chunk['content']}")
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a helpful customer support assistant. "
        "Answer the user's question using only the information provided in the context below. "
        "If the context does not contain enough information to answer the question, "
        "say so clearly rather than guessing. "
        "Be concise and direct.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}"
    )

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What is the refund window?"
    from retriever import retrieve
    chunks = retrieve(q, k=3)
    print(f"Query: {q}")
    print(f"Retrieved {len(chunks)} chunks")
    response = generate(q, chunks)
    print(f"\nResponse:\n{response}")
