# ContextLens Core — Build Log

---

## 2026-06-15 — Initial build

### What was built

Full pipeline from scratch in one session:

- `contextlens/embedder.py` — single batched OpenAI embeddings call for all claims + chunks together
- `contextlens/attributor.py` — cosine similarity with numpy, THRESHOLD=0.75, returns None on miss
- `contextlens/decomposer.py` — gpt-4o-mini with JSON mode, zero temperature
- `contextlens/judge.py` — gpt-4o-mini faithfulness judge, skips LLM call on retrieval failures
- `contextlens/pipeline.py` — orchestrates all steps, single batched embed call for efficiency
- `contextlens/formatter.py` — rich terminal output, green/yellow/red verdict colors
- `demo.py` — hardcoded customer support scenario with one faithful, one partial, one retrieval failure
- `main.py` — CLI with --demo and --input flags

### Key decisions

**Batch embeddings in one API call.** Claims and chunks are concatenated, embedded together, then split. This halves the number of API calls compared to embedding them separately. The order is preserved by the OpenAI API.

**Threshold at 0.75 for attribution.** This is the boundary between "the retriever found something related" and "the retriever found nothing relevant." Set conservatively — a 0.74 score on a 3-chunk corpus almost certainly means the claim has no source. Worth monitoring this on real data.

**Skip judge call on retrieval failures.** When attribution returns None, calling the judge would be meaningless — there is no source to compare against. The verdict is hardcoded to unfaithful + retrieval failure type. This saves one LLM call per retrieval failure and avoids confusing the model with a null input.

**Zero temperature on all LLM calls.** Both the decomposer and judge use temperature=0. These are classification tasks, not generation tasks. Determinism matters more than creativity.

**gpt-4o-mini for both decomposer and judge.** Fast and cheap. At roughly $0.15/1M input tokens, a full trace (3 claims, 3 chunks) costs well under $0.01. The judge prompt is structured enough that mini handles it well. If accuracy is insufficient on real data, swap to gpt-4o in judge.py.

### Demo scenario rationale

Three chunks: refund-policy.pdf (x2), terms-of-service.pdf (x1). LLM response has:
- Claim 1: "full refund within 30 days of purchase" — directly in chunk_1, should be faithful
- Claim 2: "7 days notice" — chunk_2 says "7 business days," dropping "business" is a subtle generation error
- Claim 3: "funds returned within 2 to 3 business days" — not in any chunk, clear retrieval failure

The partial claim was the hardest to craft. The difference needs to be real enough that the judge catches it but subtle enough that it looks like a realistic LLM error, not a toy example.

### First run results

**Cosine similarity scores — matched vs unmatched:**
- Claim 1 (faithful, refund-policy.pdf): 0.85
- Claim 2 (partial omission, terms-of-service.pdf): 0.85
- Claim 3 (hallucination, no source): 0.45

The gap between matched (0.85) and unmatched (0.45) is large enough that the 0.75 threshold works cleanly. No ambiguous borderline cases on this run.

**Judge missed the "business days" omission — this is the most interesting finding.**

Claim 2 said "7 days notice." The source says "7 business days." The judge returned FAITHFUL with score 0.90. The model's reasoning: "The claim accurately reflects the requirement for subscription cancellations to be submitted at least 7 business days before the next billing cycle." The judge actually inserted "business days" into its own reasoning even though the claim omitted it — it completed the claim from context rather than comparing word for word.

This is a real limitation of LLM-as-judge: models fill gaps from prior knowledge and tend toward charity. A stricter prompt or few-shot examples with explicit partial verdicts would likely fix this. Worth logging as a known failure mode. Implication: generation failures involving omissions (rather than contradictions) are systematically harder to catch than retrieval failures.

**Retrieval failure detection worked exactly as designed.** Claim 3 scored 0.45 against all three chunks — well below the 0.75 threshold — and was correctly labeled as a retrieval failure without any LLM call. The pipeline correctly separated it from the generation failure category.

**Decomposer output.** The LLM response had three sentences and the decomposer returned exactly three claims, each cleanly atomized and self-contained. No hallucinated extra claims, no merged claims.

**Output summary for this run:**
- Faithful: 2 (67%)
- Partial: 0 (0%) — the intended partial was missed by the judge (see above)
- Unfaithful: 1 (33%)
- Retrieval failures: 1
- Generation failures: 0 (the "7 days" omission was not caught)

**What to fix next:** The judge prompt needs sharper instruction for omissions. Possible approaches: (1) add explicit instruction to compare word-for-word on numerical values and qualifiers like "business," "working," "calendar"; (2) add a few-shot example showing a partial verdict on a "7 business days" -> "7 days" case; (3) ask the judge to first quote the relevant phrase from the source before rendering a verdict, forcing it to surface the exact wording.

---

## 2026-06-15 — Judge prompt iteration

### Problem

First run showed the judge calling Claim 2 FAITHFUL despite the claim saying "7 days" where the source says "7 business days." Root cause: LLMs reason about meaning, not text. The model knew from training that "7 business days" is the standard phrasing and inserted it into its own reasoning while scoring the claim as faithful. It was completing from prior knowledge rather than comparing literally.

### Fix applied

Two changes to the judge prompt in `contextlens/judge.py`:

1. **Quote-first reasoning.** The prompt now asks the model to copy the exact relevant phrase from the source chunk verbatim into a `source_quote` field before rendering a verdict. This forces the model to surface the literal wording and makes the comparison explicit rather than semantic.

2. **Explicit instruction on factual qualifiers.** Added: "Focus on factual precision: numbers, timeframes, units, and material qualifiers (e.g. 'business days'). Synonymous phrasing and interchangeable modal verbs (e.g. 'may' vs 'can') are acceptable and should not affect the verdict."

### Overcorrection and tuning

The first version of the fixed prompt was too strict — it flagged Claim 1 as PARTIAL because the source says "may request" and the claim says "can request." That level of pedantry is not useful. The fix is to tell the prompt that synonymous modal verbs are acceptable, so only material factual differences trigger a partial.

Final instruction added: "Synonymous phrasing and interchangeable modal verbs (e.g. 'may' vs 'can') are acceptable and should not affect the verdict."

This is a good example of prompt calibration being iterative. The first fix overcorrected, the second pass found the right line.

### Final run results

- Claim 1 (30-day refund): FAITHFUL 0.90 — correctly passes, "may" vs "can" no longer flagged
- Claim 2 (7 days notice): PARTIAL 0.70 — correctly caught, reason: "The claim drops the qualifier 'business' from '7 business days'"
- Claim 3 (2-3 business days): UNFAITHFUL 0.00 — retrieval failure, no LLM call made

**Final summary:** Faithful 1 (33%), Partial 1 (33%), Unfaithful 1 (33%). Retrieval failures: 1. Generation failures: 1. This is exactly the intended output — one of each failure type, clearly labeled and separated.

### Key takeaway for content

LLM-as-judge has a systematic blind spot for omissions vs contradictions. A model will reliably catch "30 days" changed to "14 days" (contradiction) but will often miss "7 business days" dropped to "7 days" (omission) because it fills the gap from training. The fix is to force quote-first reasoning — make the model copy the source text verbatim before judging. This single change was the difference between missing the bug entirely and catching it with the right label.

---
