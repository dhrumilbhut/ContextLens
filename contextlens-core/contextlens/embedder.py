"""
Embeds a list of strings in a single batched API call.
Returns a list of float vectors in the same order as the input.
"""

import openai

MODEL = "text-embedding-3-small"

_client = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI()
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = _get_client().embeddings.create(model=MODEL, input=texts)
    # API returns embeddings in the same order as input
    return [item.embedding for item in response.data]
