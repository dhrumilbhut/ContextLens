"""
Faithfulness judge. Given a claim and its attributed source chunk, returns a verdict.

Uses the v2 prompt (quote-first reasoning) from the build-log entry 2026-06-15.
This version correctly catches omissions like "7 days" vs "7 business days"
by forcing the model to quote the source text verbatim before comparing.

Ported from contextlens-core with AsyncOpenAI client.
"""

import json

from openai import AsyncOpenAI

from app.config import settings

MODEL = "gpt-4o-mini"

# v2 prompt: forces quote-first reasoning to prevent the model from filling gaps
# from its own training knowledge. The source_quote field anchors the comparison
# to the literal source text before the verdict is rendered.
SYSTEM_PROMPT = """\
You are a strict faithfulness judge for RAG systems. You will be given a factual claim
and the source chunk it was attributed to.

Step 1 — Quote: find the single most relevant phrase or sentence in the source chunk
that the claim is based on. Copy it verbatim into the "source_quote" field.

Step 2 — Compare: compare the claim word-for-word against that quote. Look specifically for:
- Dropped qualifiers (e.g. source says "7 business days", claim says "7 days" — partial)
- Changed quantities or timeframes (e.g. "30 days" becomes "14 days" — unfaithful)
- Softened modal verbs only when they change legal meaning (e.g. "must" becomes "may" — partial, but "may" vs "can" is acceptable)
- Added details not present in the source — unfaithful

Do NOT use your background knowledge to fill gaps. Judge only against what the source
chunk literally says. Focus on factual precision: numbers, timeframes, units, and
material qualifiers (e.g. "business days"). Synonymous phrasing and interchangeable
modal verbs (e.g. "may" vs "can") are acceptable and should not affect the verdict.

Verdicts:
- faithful: the claim matches the source quote with no material omissions or changes
- partial: the claim is mostly supported but drops, softens, or slightly alters a key detail
- unfaithful: the claim contradicts the source or introduces information not in it

Respond with a JSON object:
{
  "source_quote": "exact quote from the source chunk",
  "verdict": "faithful" | "partial" | "unfaithful",
  "score": 0.0 to 1.0,
  "reason": "one sentence naming the specific word or detail that differs"
}

Score guide: faithful >= 0.85, partial 0.4–0.84, unfaithful <= 0.39
"""

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def score_faithfulness(claim_text: str, chunk_content: str) -> dict:
    """
    Returns dict with keys: verdict, score, reasoning, source_quote.
    Raises on JSON parse failure — let Celery retry handle it.
    """
    user_message = f"Claim: {claim_text}\n\nSource chunk:\n{chunk_content}"

    response = await _get_client().chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    return {
        "verdict": data.get("verdict", "unfaithful"),
        "score": float(data.get("score", 0.0)),
        "reasoning": data.get("reason", ""),
        "source_quote": data.get("source_quote", ""),
    }
