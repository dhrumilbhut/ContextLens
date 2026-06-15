# ContextLens Core

A minimal Python script that debugs RAG hallucinations by answering one question most tools don't ask: **did the retriever fail, or did the AI misrepresent what it found?**

These two failures look identical in production output but need completely different fixes.

## The Two Failure Types

| Type | Meaning | Fix |
|---|---|---|
| Retrieval failure | The right document was never fetched | Improve your search, chunking, or embeddings |
| Generation failure | The document was there — the AI misrepresented it | Improve your prompt or model |

ContextLens decomposes every LLM response into atomic claims, attributes each claim back to its source chunk, and judges whether the AI accurately represented that chunk. The output makes the distinction explicit on every claim.

## Run It

```bash
git clone <repo>
cd contextlens-core
pip install -r requirements.txt
cp .env.example .env   # add your OpenAI API key
python demo.py
```

## Use With Your Own Pipeline

```bash
python main.py --input trace.json
```

Input format:

```json
{
  "query": "What is your refund policy?",
  "llm_response": "...",
  "chunks": [
    {"id": "chunk_1", "source": "refund-policy.pdf", "text": "..."}
  ]
}
```

## Stack

Python 3.11+, OpenAI SDK (`gpt-4o-mini` + `text-embedding-3-small`), `numpy`, `rich`. No database, no Docker, no API server.
