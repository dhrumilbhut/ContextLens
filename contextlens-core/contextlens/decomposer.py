"""
Decomposes an LLM response into a list of atomic, self-contained claim strings.
Each claim must be independently verifiable against a source document.
"""

import json
import openai

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

_client = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI()
    return _client


def decompose(llm_response: str) -> list[str]:
    response = _get_client().chat.completions.create(
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
