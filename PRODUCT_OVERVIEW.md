# ContextLens — Product Overview

> *I'm building this product and would love your honest feedback on the idea before I go further. No technical background needed to review this — just read and tell me what you think.*

---

## What Is ContextLens?

ContextLens is a developer tool that tells you exactly why your AI chatbot gave a wrong answer — and more importantly, **whether to fix your search or fix your AI's instructions**, because those are completely different problems that need completely different solutions.

Think of it as a **root cause analyser for AI mistakes** — not just "something went wrong" but "here's the exact sentence that was wrong, here's the document it should have come from, and here's whether the document was ever found."

---

## The Problem

AI assistants that answer questions from documents are everywhere right now — customer support bots, internal company knowledge bases, product Q&A tools, legal research tools. These are called **RAG systems** (the AI retrieves relevant documents, then generates an answer based on them).

They work well most of the time. But sometimes they give wrong answers. And here's the part that frustrates developers:

**Two wrong answers can look completely identical from the outside, but need completely different fixes.**

Wrong answer type 1: The AI never found the right document. It was answering from its general training — making things up because it had nothing relevant to work from. The fix is to improve the search.

Wrong answer type 2: The AI found exactly the right document, then ignored it or subtly misrepresented it. The fix is to change how you instruct the AI.

Current tools give developers a single score — "faithfulness: 0.6" — that mixes both problems together. A developer looking at that score has no idea which problem they have, so they guess. They might spend a week improving their search when the real problem was the AI's instructions. Or vice versa.

**The result:**
- Days of debugging something that should take minutes
- Changes made to the wrong part of the system
- No systematic way to know if things are actually improving

---

## The Solution

ContextLens plugs into an existing AI assistant and watches every answer it gives. When the AI produces a response, ContextLens automatically:

**1. Breaks the answer into individual statements**

Instead of looking at the whole answer, it looks at each individual claim separately.

*Example — AI says:*
> *"Your refund window is 30 days. Cancellation requires 7 days notice. Refunds are processed within 5 business days."*

ContextLens treats these as three separate statements to investigate.

**2. Traces each statement back to its source**

For each statement, it finds the exact document chunk the AI was looking at when it said that. Like a citation check — did this claim actually come from the documents?

**3. Scores whether the source actually supports the statement**

Even if a document was found, did the AI accurately represent what it said? Or did it subtly change the meaning?

*Example:*
- Document says: *"Refunds processed within 30 **business** days"*
- AI said: *"Refunds processed within 30 days"*
- ContextLens flags this — the word "business" was dropped, changing the meaning

**4. Shows you the full picture in a dashboard**

A simple visual interface shows you exactly which statements are accurate, which are subtly wrong, and which have no source at all — meaning the AI completely made them up.

---

## What the Developer Sees

Instead of a confusing number, the developer sees something like this:

```
Query: "What is the refund policy?"

✓  "Refund window is 30 days from purchase."
   Source: refund-policy.pdf   Accurate ✓

⚠  "Cancellation requires 7 days notice."
   Source: terms-of-service.pdf   Partially accurate ⚠
   Reason: "Document says 7 business days, not 7 days"

✗  "Refunds processed within 5 business days."
   Source: none found
   Reason: "The AI made this up — this wasn't in any retrieved document"
```

Now the developer knows exactly what to fix:
- The third statement is a hallucination — the document doesn't say this at all
- The second statement has a subtle error — "business days" was lost
- Only the first statement is fully accurate

**This turns a multi-day debugging session into a 5-minute fix.**

---

## The Bigger Pattern: Three Types of Problems

ContextLens helps identify which category a problem falls into — and each one has a different fix:

| What ContextLens Shows | What It Means | What to Fix |
|---|---|---|
| AI made a claim with no source document | The AI couldn't find the relevant information | Add the missing document or improve search |
| Source found, but AI misrepresented it | The AI ignored what the document actually said | Adjust how you instruct the AI |
| Source found and accurate, but wrong document | Old or incorrect document is being used | Remove or update outdated documents |

---

## Who Is This For?

**Primary users: developers and engineers** building AI assistants where a wrong answer has a real cost.

The clearest use case is **customer-facing support bots** — where a wrong answer about pricing, refunds, or policy directly causes a support ticket, a refund request, or a churned customer. The stakes are high enough that teams actively want to find and fix wrong answers before customers do.

This includes:
- Startups building AI-powered customer support
- Companies building internal knowledge assistants where wrong answers waste employee time
- Teams building document Q&A products (legal, medical, finance)
- Any developer who has shipped an AI assistant and wants to stop debugging it manually

**Secondary users: ops and customer success teams.**

The debugging workflow is built for engineers — they're the ones who go fix things. But the dashboard views showing "billing questions are failing at 34% this week" or "these 47 queries all get wrong answers about cancellation policy" don't require any technical knowledge to read or act on.

Ops and customer success teams can use these views to:
- Anticipate which customer complaints are coming before they arrive
- Prioritise which documents need updating
- Track whether improvements are actually working after the engineering team makes changes

Two audiences. One product. Neither view requires you to understand how the other one works.

---

## How It Works (Non-Technical)

The developer installs ContextLens on their own computer — it runs entirely on their machine, like local software. No data is sent anywhere. They connect their AI assistant to it with a simple setup (about 5 minutes), and from that point on ContextLens silently watches every conversation in the background.

The developer opens a dashboard in their browser at any time to see what's happening — which answers were accurate, which had problems, and what the patterns are across many conversations.

**Key point: it doesn't change how the AI works.** It just watches and reports. Like a dashcam — it doesn't affect the drive, it just records what happened so you can review it.

---

## Features

### Core Features
- **Per-statement attribution** — see exactly which document each AI claim came from
- **Accuracy scoring** — know whether each statement accurately reflects its source
- **"Made it up" detection** — instantly spot when the AI invented information with no source
- **Explanation for every flag** — not just a score, but a plain-English reason why something was flagged

### Pattern Detection
- **Query grouping** — automatically groups similar questions together (e.g., "all billing-related questions") so you can see which topics your AI struggles with most
- **Problem document ranking** — shows which documents in your knowledge base are causing the most wrong answers
- **Trends over time** — see if your AI is getting better or worse after you make changes

### Developer Experience
- **2-line setup** — connect any existing AI assistant with two lines of code
- **Works with popular frameworks** — compatible with LangChain and LlamaIndex (the two most popular AI development frameworks)
- **Runs locally** — all data stays on your own machine, nothing sent to external servers
- **Simple dashboard** — a clean browser interface, no complex setup

---

## What Makes This Different

**The split that matters most, and that no current tool makes explicit.**

When an AI gives a wrong answer, there are two possible root causes:

- **The right document was never fetched.** Fix your search.
- **The right document was there and the AI ignored or misrepresented it.** Fix your prompt.

These look identical from the outside. Current tools (RAGAS, LangSmith, Braintrust) give you a faithfulness score that conflates both. A developer looking at "72% faithfulness" cannot tell whether to fix their search or their instructions — so they guess.

ContextLens separates them explicitly on every flagged claim: either a source chunk was found or it wasn't. If it was, faithfulness scoring tells you whether the AI accurately represented it. You always know which problem you're dealing with before you touch anything.

**Existing tools measure. ContextLens diagnoses.**

Metrics tell you something is wrong. ContextLens tells you what is wrong, where it came from, and which of the two root causes you're looking at. Every flag comes with a source, a reason, and a category — so you can fix the right thing the first time.

---

## The Business Model (Future)

The initial version is **free and open source** — developers can download and run it themselves.

The longer-term plan is a hosted cloud version where teams can use it as a service without managing their own installation. Pricing would be based on usage (how many AI conversations are monitored per month), with a free tier for small teams and paid plans for larger usage.

---

## What Stage Is This At?

This is currently in the planning and early development phase. The core idea, architecture, and feature set are fully designed. Development is about to begin.

**Timeline:** First working version in approximately 8–10 days.

---

## What I'm Looking For From You

I'd genuinely love your honest reaction to this. Specifically:

1. **Does the problem feel real to you?** Have you encountered AI tools that give wrong answers and couldn't tell why?

2. **Is the solution clear?** After reading this, do you understand what ContextLens actually does — or does something still feel fuzzy?

3. **Who do you think would pay for this?** Does it feel like something a company would spend money on, or does it feel like a "nice to have"?

4. **What feels missing?** Is there something obvious this should do that I haven't mentioned?

5. **What's your gut reaction?** First impression, no filter.

No technical knowledge required to give feedback — your honest reaction as someone reading this for the first time is exactly what I need.

---

*Thanks for reading. Any feedback, no matter how small, is genuinely helpful at this stage.*
