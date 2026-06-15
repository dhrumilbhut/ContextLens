# Dashboard

The Next.js dashboard — its pages, views, and structure.

---

## Tech Stack

- **Framework:** Next.js 14 (App Router)
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **Charts:** Recharts
- **HTTP client:** fetch (native) with a thin wrapper

---

## Two Audiences, Two View Categories

The dashboard serves two distinct audiences. This is intentional and should be reflected in how views are organised and labelled.

**Engineering views** — require understanding of the pipeline to act on:
- Trace detail (`/traces/[traceId]`) — per-claim attribution, which chunk, why it failed
- Problem documents (`/documents`) — which source files need fixing

**Business / ops views** — readable without any technical knowledge:
- Project overview (`/[projectId]`) — faithfulness trend over time, headline stats
- Query clusters (`/clusters`) — which *topics* the AI struggles with, expressed in plain English

An ops manager or customer success lead can open the cluster view and immediately see "billing questions are failing at 34% this week" without understanding what a chunk or an embedding is. They can use that to anticipate support tickets, prioritise document updates, or escalate to engineering.

This dual-audience design is a deliberate product decision — it widens who gets value from the tool without adding complexity to the engineering views.

---

**Self-hosted: no login required.**

The dashboard at `localhost:3000` is accessible without authentication.
All API calls go to `localhost:8000`. Localhost access is authorization.

No login page. No signup page. No session management. No JWT handling in the frontend.
The dashboard just opens and works.

When the cloud version is added, auth pages and a JWT-based session context
get added. See `CLOUD_FUTURE.md`.

---

## Page Structure

```
app/
  page.tsx                  ← redirect to /dashboard

  dashboard/
    page.tsx                ← project list (home)

  projects/
    new/page.tsx            ← create project form
    [projectId]/
      page.tsx              ← project overview (stats + charts)
      traces/
        page.tsx            ← trace list with filters
        [traceId]/page.tsx  ← single trace detail ← THE MAIN VIEW
      clusters/page.tsx     ← query cluster analysis
      documents/page.tsx    ← problematic documents ranked list
      usage/page.tsx        ← daily processing stats
      settings/
        page.tsx            ← project settings (rename, delete)
        api-keys/page.tsx   ← API key management
```

---

## Core Views

### View 1: Trace Detail (`/projects/[id]/traces/[traceId]`)

**The most important page in the product. This is the "aha moment."**

```
┌─────────────────────────────────────────────────────────┐
│  Query                                                   │
│  "What is the refund policy?"                            │
├─────────────────────────────────────────────────────────┤
│  Response                                                │
│  "Your refund window is 30 days from purchase.           │
│   Cancellation requires 7 days notice.                   │
│   Refunds are processed within 5 business days."         │
├─────────────────────────────────────────────────────────┤
│  Claims (3)                                              │
│                                                          │
│  ✓  "Refund window is 30 days from purchase."            │
│     Source: refund-policy.pdf · chunk 1                  │
│     Attribution: 0.91  ·  Faithfulness: 0.95 (faithful)  │
│                                                          │
│  ⚠  "Cancellation requires 7 days notice."              │
│     Source: terms-of-service.pdf · chunk 4               │
│     Attribution: 0.79  ·  Faithfulness: 0.55 (partial)   │
│     "Chunk says 7 business days, claim omits 'business'" │
│                                                          │
│  ✗  "Refunds processed within 5 business days."         │
│     Source: none found                                   │
│     Attribution: —  ·  Faithfulness: 0.0 (unfaithful)   │
│     "No source chunk found in retrieved context"         │
└─────────────────────────────────────────────────────────┘
```

**Color coding:**
- Green (✓) — `faithfulness_verdict = 'faithful'`, score > 0.8
- Yellow (⚠) — `faithfulness_verdict = 'partial'`, score 0.4–0.8
- Red (✗) — `faithfulness_verdict = 'unfaithful'`, score < 0.4

**Clicking a claim** expands it to show the full attributed chunk content
side by side with the claim text — so you can see exactly what matched
and where the discrepancy is.

---

### View 2: Project Overview (`/projects/[projectId]`)

```
┌────────────────────────────────────────────────────────┐
│  Customer Support Bot                                   │
├────────────┬────────────┬────────────┬─────────────────┤
│  1,847     │  0.73      │  18%       │  3              │
│  traces    │  avg faith │  unfaith   │  problem docs   │
│  (7 days)  │  (7 days)  │  rate      │                 │
├────────────────────────────────────────────────────────┤
│  Faithfulness over time (30 days)                      │
│                                                        │
│  1.0 ┤                                                 │
│  0.8 ┤    ╭──╮  ╭──────                               │
│  0.6 ┤────╯  ╰──╯                                     │
│  0.4 ┤                                                 │
├────────────────────────────────────────────────────────┤
│  Recent traces (last 10, with mini status indicators)  │
└────────────────────────────────────────────────────────┘
```

---

### View 3: Query Clusters (`/projects/[projectId]/clusters`)

```
┌────────────────────────────────────────────────────────┐
│  Query Clusters                                         │
│  Groups of semantically similar queries                 │
├────────────────────────────────────────────────────────┤
│  ● questions about billing and refunds          ← worst │
│    234 queries · avg faithfulness: 0.58 · 34% bad      │
│    [view traces →]                                     │
│                                                        │
│  ● shipping and delivery questions                     │
│    189 queries · avg faithfulness: 0.81 · 9% bad       │
│    [view traces →]                                     │
│                                                        │
│  ● account and password issues                         │
│    156 queries · avg faithfulness: 0.91 · 4% bad       │
│    [view traces →]                                     │
└────────────────────────────────────────────────────────┘
```

Sorted by worst average faithfulness first — focus here first.

**This view requires no technical knowledge.** An ops manager or customer success lead can read "billing questions are failing at 34% this week" and act on it — escalate to engineering, prepare support team, or prioritise document updates. They don't need to understand what attribution or embeddings are. This is the business-facing signal; the trace detail view is the engineering-facing debugging surface.

---

### View 4: Problem Documents (`/projects/[projectId]/documents`)

```
┌────────────────────────────────────────────────────────┐
│  Problem Documents (last 7 days)                        │
│  Source documents causing the most hallucinations       │
├────────────────────────────────────────────────────────┤
│  old-policy-2021.pdf                                    │
│  47 unfaithful claims · 53% unfaithful rate            │
│  Diagnosis: likely stale document                      │
│                                                        │
│  shipping-faq.pdf                                       │
│  23 unfaithful claims · 31% unfaithful rate            │
│  Diagnosis: check chunking — tables may be split badly │
└────────────────────────────────────────────────────────┘
```

---

### View 5: API Key Management (`/projects/[projectId]/settings/api-keys`)

```
┌────────────────────────────────────────────────────────┐
│  API Keys                              [+ Create Key]  │
├────────────────────────────────────────────────────────┤
│  Local Dev Key                                         │
│  cl_proj_abc1...  ·  Last used: 2 minutes ago          │
│  Created: May 1, 2026                    [Revoke]      │
└────────────────────────────────────────────────────────┘
```

When a key is created, a modal shows the raw key once:

```
┌────────────────────────────────────────────────────────┐
│  ⚠ Copy your API key — it won't be shown again        │
│                                                        │
│  cl_proj_abc123xyz...                   [Copy] [Done]  │
└────────────────────────────────────────────────────────┘
```

---

### View 6: First-Run Onboarding (empty dashboard)

When a user opens the dashboard for the first time with no projects:

```
┌────────────────────────────────────────────────────────┐
│  Welcome to ContextLens                                 │
│                                                        │
│  Step 1  Create your first project                     │
│          [Create Project →]                            │
│                                                        │
│  Step 2  Install the SDK                               │
│          pip install contextlens                       │
│                                                        │
│  Step 3  Add your API key to .env                      │
│          CONTEXTLENS_API_KEY=cl_proj_...               │
│          CONTEXTLENS_API_URL=http://localhost:8000     │
│                                                        │
│  Step 4  Add 2 lines to your RAG code                  │
│          [code snippet with copy button]               │
│                                                        │
│  Step 5  Send your first trace                         │
│          Run your RAG app and ask it a question.       │
│          Your first trace will appear here.            │
└────────────────────────────────────────────────────────┘
```

---

## API Client

A thin TypeScript wrapper over fetch that handles base URL and errors:

```typescript
// lib/api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Unknown error' }));
    throw new ApiError(response.status, error.error || 'Request failed');
  }

  return response.json();
}

// typed convenience methods
export const api = {
  projects: {
    list: () => apiRequest<ProjectsResponse>('/projects'),
    get: (id: string) => apiRequest<Project>(`/projects/${id}`),
    create: (data: CreateProjectRequest) =>
      apiRequest<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
  },
  traces: {
    list: (projectId: string, params?: TraceListParams) =>
      apiRequest<TracesResponse>(`/projects/${projectId}/traces?${new URLSearchParams(params)}`),
    get: (projectId: string, traceId: string) =>
      apiRequest<TraceDetail>(`/projects/${projectId}/traces/${traceId}`),
  },
  clusters: {
    list: (projectId: string) =>
      apiRequest<ClustersResponse>(`/projects/${projectId}/clusters`),
  },
  documents: {
    problems: (projectId: string) =>
      apiRequest<DocumentsResponse>(`/projects/${projectId}/documents/problems`),
  },
};
```

No auth headers in self-hosted mode — the API client is simple.
When cloud auth is added, the JWT Bearer token gets injected here.

---

## Key Component: ClaimCard

The core UI building block — renders one claim with its attribution and score:

```typescript
// components/claim-card.tsx

interface ClaimCardProps {
  claim: Claim;
  expanded?: boolean;
}

function ClaimCard({ claim, expanded = false }: ClaimCardProps) {
  const verdict = claim.faithfulness_verdict;
  const color = {
    faithful: 'green',
    partial: 'yellow',
    unfaithful: 'red',
  }[verdict];

  return (
    <div className={`border-l-4 border-${color}-500 pl-4 py-2`}>
      <p className="font-medium">{claim.claim_text}</p>

      {claim.attribution ? (
        <p className="text-sm text-gray-500">
          Source: {claim.attribution.source_document} ·
          Attribution: {claim.attribution_score.toFixed(2)}
        </p>
      ) : (
        <p className="text-sm text-red-500">No source chunk found</p>
      )}

      <p className="text-sm">
        Faithfulness: {claim.faithfulness_score.toFixed(2)} ({verdict})
      </p>

      {expanded && claim.judge_reasoning && (
        <p className="text-sm text-gray-600 mt-1 italic">
          "{claim.judge_reasoning}"
        </p>
      )}

      {expanded && claim.attribution && (
        <div className="mt-2 bg-gray-50 p-3 rounded text-sm">
          <p className="font-medium text-gray-700">Source chunk:</p>
          <p className="text-gray-600">{claim.attribution.chunk_content}</p>
        </div>
      )}
    </div>
  );
}
```
