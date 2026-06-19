"""
Decomposes an LLM response into a list of atomic, self-contained claim objects.
Ported from contextlens-core with AsyncOpenAI client.

Each claim object has:
  claim_text: str
  is_refusal: bool

is_refusal=True signals that the LLM explicitly stated the provided context
does not contain relevant information. These claims skip attribution and judge
scoring entirely — they are stored with faithfulness_verdict='refusal'.
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

IMPORTANT — compound sentence splitting rules:
Split claims only when they express genuinely INDEPENDENT facts that could be
separately verified against different parts of a source document. Do NOT split a
single sentence's internal compound or conditional structure when those clauses
describe one unified policy or outcome.

COMBINE into one claim:
- Conditional "if A then X, or if not A then Y" structures — these describe one
  policy with a branching outcome and must stay as one claim
- "X, after which Y" or "X, and then Y" structures where Y is the direct consequence
  of X (e.g. a retention period followed by deletion)
- Flat enumerations where "and", "but", or commas join multiple consequences or
  conditions that all describe what happens when the SAME single event occurs or
  action is taken. This includes both additive "and" lists AND concessive "but"
  structures where "but" introduces conditions or timing constraints rather than a
  genuine contradiction (e.g. "you can downgrade, but [timing], and [requirement]"
  — all three describe one downgrade event). Keep all same-trigger consequences as
  one claim, regardless of how many items: 2, 3, or more. The test: does the
  sentence describe one action or event and its full set of effects/conditions?
  If yes, produce ONE claim covering all of them.

SPLIT into separate claims:
- Sentences about genuinely different topics (e.g. refund policy AND shipping time)
  that could be verified independently against different source sections
- Adjacent sentences where each expresses a distinct, standalone fact
- Items joined by "and" that describe independent facts about DIFFERENT topics or
  triggers (e.g. "refunds take 5 business days, and shipping takes 3 days" — these
  are independent facts, not consequences of one shared trigger)

EXAMPLES of correct and incorrect splitting:

Example 1 — WRONG (over-split) vs RIGHT (compound conditional):
Response sentence: "Your account will automatically downgrade to the free tier, if
  available, or access will be suspended."
WRONG — do not produce two claims:
  "Your account will automatically downgrade to the free tier, if available."
  "If the free tier is not available, access will be suspended."
RIGHT — produce one claim preserving the full conditional:
  "Your account will automatically downgrade to the free tier if available, or access
  will be suspended if it is not."

Example 2 — WRONG (over-split) vs RIGHT (consequence chain):
Response sentence: "Your data will be retained for 90 days after the end of the paid
  period, after which it is subject to deletion."
WRONG — do not produce two claims:
  "Your data will be retained for 90 days after the end of the paid period."
  "After 90 days, your data is subject to deletion."
RIGHT — produce one claim that includes both the retention period and the consequence:
  "Your data will be retained for 90 days after the end of the paid period, after
  which it is subject to deletion."

Example 3 — RIGHT (correct split across genuinely independent facts):
Response: "Digital products are non-refundable once downloaded. Standard shipping
  takes 5–7 business days for domestic orders."
RIGHT — produce two separate claims because these are unrelated facts from different
  source sections:
  "Digital products are non-refundable once downloaded or the license key has been
  revealed."
  "Standard shipping takes 5–7 business days for domestic orders within the
  continental United States."

Example 4 — WRONG (over-split) vs RIGHT (two-item enumeration of same-trigger consequences):
Response sentence: "If you miss the 30-day notice window for annual cancellation,
  your subscription will renew for another 12 months, and refund eligibility will
  follow the standard annual refund policy."
WRONG — do not produce two claims (the trigger is one event — missing the window):
  "If you miss the 30-day notice window for annual cancellation, your subscription
  will renew for another 12 months."
  "Refund eligibility will follow the standard annual refund policy."
RIGHT — produce one claim combining all consequences of the same missed-window event:
  "If you miss the 30-day notice window for annual cancellation, your subscription
  will renew for another 12 months and refund eligibility will follow the standard
  annual refund policy."

Example 5 — WRONG (over-split) vs RIGHT (three-item enumeration of same-trigger consequences):
Response sentence: "When you upgrade your plan, the change takes effect immediately,
  you are charged a prorated amount for the remainder of your current billing cycle,
  and the next full billing cycle is charged at the new plan rate."
WRONG — do not produce three claims (the trigger is one event — upgrading the plan):
  "When you upgrade your plan, the change takes effect immediately."
  "You are charged a prorated amount for the remainder of your current billing cycle."
  "The next full billing cycle is charged at the new plan rate."
RIGHT — produce one claim combining all three consequences of upgrading:
  "When you upgrade your plan, the change takes effect immediately, you are charged a
  prorated amount for the remainder of your current billing cycle, and the next full
  billing cycle is charged at the new plan rate."

Example 6 — WRONG (over-split) vs RIGHT (concessive "but" introducing same-action conditions):
Response sentence: "You can still downgrade to a lower plan, but the downgrade will
  take effect at the start of the next billing period, and you must reduce your usage
  if it exceeds the limits of the lower plan."
WRONG — do not produce three claims (all items describe one downgrade action and its
  conditions; "but" here is concessive — it introduces conditions, not a contradiction):
  "You can still downgrade to a lower plan."
  "The downgrade will take effect at the start of the next billing period."
  "You must reduce your usage if it exceeds the limits of the lower plan."
RIGHT — produce one claim covering the downgrade action and all its conditions:
  "You can still downgrade to a lower plan, but the downgrade will take effect at the
  start of the next billing period and you must reduce your usage if it exceeds the
  limits of the lower plan."

IMPORTANT — refusal detection:
If the response explicitly states that the provided context does not contain information
about the topic (e.g. "the context does not contain information about X",
"I don't have information on this in the provided documents",
"the provided context does not mention Y"), treat this as a refusal, not a factual claim.
For a refusal response, return exactly one claim object with:
  - claim_text: a concise statement of what was declined, e.g. "No information about
    student discounts was found in the provided context."
  - is_refusal: true

For normal factual claims, set is_refusal: false.

Respond with a JSON object:
{"claims": [{"claim_text": "...", "is_refusal": false}, ...]}
"""

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def decompose_claims(llm_response: str) -> list[dict]:
    """Returns a list of claim dicts: [{"claim_text": str, "is_refusal": bool}, ...]"""
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
    raw_claims = data.get("claims", [])

    result = []
    for item in raw_claims:
        if isinstance(item, str):
            # Backwards-compatible: old prompt format returned plain strings
            result.append({"claim_text": item, "is_refusal": False})
        elif isinstance(item, dict):
            result.append({
                "claim_text": item.get("claim_text", ""),
                "is_refusal": bool(item.get("is_refusal", False)),
            })
    return result
