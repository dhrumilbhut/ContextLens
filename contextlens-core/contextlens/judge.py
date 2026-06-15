"""
Faithfulness judge. Given a claim and its attributed source chunk, returns:
    verdict:   "faithful" | "partial" | "unfaithful"
    score:     float 0.0–1.0
    reason:    one sentence explaining the verdict

If no chunk was attributed (retrieval failure), the judge is skipped and the
claim is marked unfaithful with a fixed reason.
"""

import json
import openai

MODEL = "gpt-4o-mini"

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

_client = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI()
    return _client


def judge(claim: str, chunk: dict | None) -> dict:
    if chunk is None:
        return {
            "verdict": "unfaithful",
            "score": 0.0,
            "reason": "No source chunk found in retrieved context — retrieval failure.",
            "failure_type": "retrieval",
        }

    user_message = f"Claim: {claim}\n\nSource chunk:\n{chunk['text']}"
    response = _get_client().chat.completions.create(
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

    verdict = data.get("verdict", "unfaithful")
    score = float(data.get("score", 0.0))
    reason = data.get("reason", "")

    failure_type = None
    if verdict in ("partial", "unfaithful"):
        failure_type = "generation"

    return {
        "verdict": verdict,
        "score": score,
        "reason": reason,
        "failure_type": failure_type,
    }
