// Types match the exact snake_case field names returned by the backend API.
// Do not camelCase — consistency with the backend avoids a translation layer.

// ── Trace types ──────────────────────────────────────────────────────────────

export interface AttributionDetail {
  chunk_id: string;
  chunk_content: string;
  source_document: string;
  chunk_index: number;
  attribution_score: number;
}

export interface ClaimDetail {
  id: string;
  claim_text: string;
  claim_index: number;
  attribution: AttributionDetail | null;
  faithfulness_verdict: "faithful" | "partial" | "unfaithful";
  faithfulness_score: number;
  is_faithful: boolean;
  judge_reasoning: string;
}

export interface TraceDetailResponse {
  id: string;
  query_text: string;
  llm_response: string;
  status: "pending" | "processing" | "processed" | "failed";
  latency_ms: number | null;
  created_at: string;
  claims: ClaimDetail[];
}

export interface TraceListItem {
  id: string;
  query_text: string;
  status: string;
  claim_count: number;
  faithful_claim_count: number;
  avg_faithfulness: number | null;
  created_at: string;
}

export interface TraceListResponse {
  traces: TraceListItem[];
  total: number;
}

export function getFailureType(
  claim: ClaimDetail
): "retrieval" | "generation" | null {
  if (claim.is_faithful) return null;
  if (claim.attribution === null) return "retrieval";
  return "generation";
}

// ── Project types ─────────────────────────────────────────────────────────────

export interface ProjectListItem {
  id: string;
  name: string;
  description: string | null;
  trace_count: number;
  avg_faithfulness: number | null;
  created_at: string;
}

export interface ProjectListResponse {
  projects: ProjectListItem[];
}

export interface ProblemDocument {
  source: string;
  unfaithful_claims: number;
}

export interface ProjectDetailResponse {
  id: string;
  name: string;
  trace_count: number;
  avg_faithfulness_7d: number | null;
  unfaithful_claim_rate: number | null;
  top_problem_documents: ProblemDocument[];
}

export interface ProjectCreateResponse {
  id: string;
  name: string;
  created_at: string;
}

export interface ApiKeyListItem {
  id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyListResponse {
  api_keys: ApiKeyListItem[];
}

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
}

// ── Documents types ───────────────────────────────────────────────────────────

export interface DocumentProblemItem {
  source_document: string;
  total_claims: number;
  unfaithful_claims: number;
  unfaithful_rate: number;
  avg_faithfulness: number;
}

export interface DocumentsProblemsResponse {
  documents: DocumentProblemItem[];
}

// ── Cluster types ─────────────────────────────────────────────────────────────

export interface QueryClusterItem {
  id: string;
  label: string;
  trace_count: number;
  avg_faithfulness: number;
  unfaithful_rate: number;
}

export interface ClustersResponse {
  clusters: QueryClusterItem[];
}

// ── Usage types ───────────────────────────────────────────────────────────────

export interface UsageTodayItem {
  traces_ingested: number;
  traces_processed: number;
  processing_limit: number;
  limit_reached: boolean;
}

export interface UsageDayItem {
  date: string;
  traces_processed: number;
}

export interface UsageResponse {
  today: UsageTodayItem;
  last_7_days: UsageDayItem[];
}
