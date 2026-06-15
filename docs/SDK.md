# SDK

This document explains how the Python SDK works — its design, integration patterns, and internals.

---

## Design Goals

1. **Non-intrusive** — developers add 2 lines to existing code, nothing more
2. **Zero performance impact** — never blocks the RAG app's response path
3. **Fails silently** — if ContextLens is down, the RAG app continues unaffected
4. **Framework integrations** — zero lines needed for LangChain and LlamaIndex users

---

## Installation

```bash
pip install contextlens
```

---

## Configuration

The SDK reads configuration from environment variables:

```bash
# required
CONTEXTLENS_API_KEY=cl_proj_abc123xyz

# optional
CONTEXTLENS_API_URL=https://api.contextlens.dev  # default
CONTEXTLENS_ENABLED=true                          # set to false to disable in test envs
CONTEXTLENS_TIMEOUT=5                             # seconds to wait for ingest API
```

---

## Integration Patterns

### Pattern 1: Manual (works with any RAG framework)

```python
import contextlens

with contextlens.trace(query=user_query) as trace:
    # your existing retrieval code — unchanged
    chunks = your_retriever.fetch(user_query)
    trace.log_chunks(chunks)

    # your existing generation code — unchanged
    response = your_llm.generate(chunks, user_query)
    trace.log_response(response)

# response is returned to user here
# SDK sends trace data in background — does NOT block this line
```

### Pattern 2: LangChain (zero extra lines)

```python
from contextlens.integrations.langchain import ContextLensCallbackHandler

# add callback handler — that's it
llm = ChatOpenAI(
    model="gpt-4o",
    callbacks=[ContextLensCallbackHandler()]
)

# all chain executions are automatically traced
chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
result = chain.invoke({"query": user_query})
```

### Pattern 3: LlamaIndex (zero extra lines)

```python
from contextlens.integrations.llamaindex import ContextLensEventHandler
import llama_index.core

llama_index.core.global_handler = ContextLensEventHandler()

# all query engine calls are automatically traced
query_engine = index.as_query_engine()
response = query_engine.query(user_query)
```

---

## The `trace.log_chunks()` Format

The SDK accepts chunks in multiple formats to be compatible with different retriever outputs:

```python
# format 1: list of strings (simplest)
trace.log_chunks(["chunk content 1", "chunk content 2"])

# format 2: list of dicts (recommended — includes metadata)
trace.log_chunks([
    {
        "content": "Refunds are processed within 30 business days.",
        "source": "refund-policy.pdf",
        "chunk_index": 3,
        "score": 0.89   # similarity score from your retriever
    },
    ...
])

# format 3: LangChain Document objects (auto-detected)
trace.log_chunks(langchain_documents)

# format 4: LlamaIndex NodeWithScore objects (auto-detected)
trace.log_chunks(llamaindex_nodes)
```

The SDK normalizes all formats into the internal schema before sending to the API.

---

## How Fire-and-Forget Works

The most important design decision: **the SDK never blocks the RAG app.**

```python
import asyncio
import threading
import httpx

class TraceContext:
    def __init__(self, query: str):
        self.query = query
        self.chunks = []
        self.response = None

    def log_chunks(self, chunks):
        self.chunks = normalize_chunks(chunks)

    def log_response(self, response: str):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # context manager exits = RAG app is done
        # send trace in a background thread — never blocks
        if self.response and not exc_type:  # don't send on exception
            threading.Thread(
                target=self._send_trace,
                daemon=True  # thread dies if main process dies — doesn't hang shutdown
            ).start()
        return False  # don't suppress exceptions

    def _send_trace(self):
        try:
            payload = {
                "query": self.query,
                "chunks": self.chunks,
                "response": self.response
            }
            with httpx.Client(timeout=5.0) as client:
                client.post(
                    f"{API_URL}/ingest",
                    json=payload,
                    headers={"Authorization": f"Bearer {API_KEY}"}
                )
        except Exception:
            # ALWAYS silent — never raise, never crash the RAG app
            logger.debug("ContextLens: failed to send trace")
```

**Key decisions:**
- `daemon=True` — if the main process shuts down, this thread doesn't keep it alive
- `timeout=5.0` — if the ingest API doesn't respond in 5 seconds, we give up. The RAG app's response has already been returned to the user.
- Bare `except Exception` — we catch everything and do nothing. The RAG app must never crash because of us.

---

## What Gets Sent to the API

```json
POST /ingest
Authorization: Bearer cl_proj_abc123xyz
Content-Type: application/json

{
  "query": "What is the refund policy?",
  "chunks": [
    {
      "content": "Refunds are processed within 30 business days of the return being received.",
      "source": "refund-policy.pdf",
      "chunk_index": 3,
      "retriever_score": 0.89
    },
    {
      "content": "To initiate a return, contact support within 30 days of purchase.",
      "source": "refund-policy.pdf",
      "chunk_index": 1,
      "retriever_score": 0.82
    }
  ],
  "response": "Your refund window is 30 days from purchase. Refunds are typically processed within 30 business days.",
  "latency_ms": 1243
}
```

---

## Disabling in Test Environments

```bash
# in your test environment
CONTEXTLENS_ENABLED=false
```

When disabled, the SDK is a complete no-op — the context manager still works but nothing is sent. No need to mock the SDK in tests.

---

## SDK Internal Structure

```
contextlens/
  __init__.py          — public API: trace(), configure()
  client.py            — HTTP client, fire-and-forget sender
  context.py           — TraceContext class (the context manager)
  normalizers.py       — normalize chunks from different formats
  config.py            — reads env vars, validation
  integrations/
    __init__.py
    langchain.py       — LangChain callback handler
    llamaindex.py      — LlamaIndex event handler
  exceptions.py        — ContextLensError (never raised to user — only logged)
```
