from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChunkInput(BaseModel):
    content: str
    source: str
    chunk_index: int
    retriever_score: Optional[float] = None


class IngestRequest(BaseModel):
    query: str
    chunks: list[ChunkInput]
    response: str
    latency_ms: Optional[int] = None


class IngestResponse(BaseModel):
    trace_id: str
    status: str


class AttributionDetail(BaseModel):
    chunk_id: str
    chunk_content: str
    source_document: str
    chunk_index: int
    attribution_score: float
    confidence: Optional[str] = None  # 'high' | 'low' | None


class ClaimDetail(BaseModel):
    id: str
    claim_text: str
    claim_index: int
    attribution: Optional[AttributionDetail] = None
    faithfulness_verdict: str  # 'faithful' | 'partial' | 'unfaithful' | 'refusal'
    faithfulness_score: Optional[float] = None  # None for refusal claims
    is_faithful: Optional[bool] = None           # None for refusal claims
    judge_reasoning: str


class TraceDetailResponse(BaseModel):
    id: str
    query_text: str
    llm_response: str
    status: str
    latency_ms: Optional[int] = None
    created_at: datetime
    claims: list[ClaimDetail]


class TraceListItem(BaseModel):
    id: str
    query_text: str
    status: str
    claim_count: int
    faithful_claim_count: int
    avg_faithfulness: Optional[float] = None
    created_at: datetime


class TraceListResponse(BaseModel):
    traces: list[TraceListItem]
    total: int
