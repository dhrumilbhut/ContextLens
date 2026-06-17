"""
Embeds a list of strings in a single batched API call.
Returns a list of float vectors in the same order as the input.
Ported from contextlens-core with AsyncOpenAI client.
"""

from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = await _get_client().embeddings.create(
        model=settings.CONTEXTLENS_EMBEDDING_MODEL,
        input=texts,
    )
    # API returns embeddings in the same order as input — no sorting needed
    return [item.embedding for item in response.data]
