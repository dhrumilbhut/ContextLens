"""
Decomposes an LLM response into a list of atomic, self-contained claim strings.
Ported from contextlens-core with AsyncOpenAI client.
"""

import json

from openai import AsyncOpenAI

from app.config import settings

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """\
You are a precise claim extractor. Your job is to break an AI-generated response into
atomic, self-contained factual claims. Each claim must:
- Express exactly one verifiable fact
- Be understandable without context from the surrounding text
- Be a complete sentence

Do not include hedges, filler, or meta-commentary. If the response contains no
verifiable factual claims, return an empty list.

Respond with a JSON object: {"claims": ["claim 1", "claim 2", ...]}
"""

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def decompose_claims(llm_response: str) -> list[str]:
    response = await _get_client().chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": llm_response},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return data.get("claims", [])
