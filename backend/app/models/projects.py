from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreateResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class ProjectListItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    trace_count: int
    avg_faithfulness: Optional[float] = None
    created_at: datetime


class ProjectListResponse(BaseModel):
    projects: list[ProjectListItem]


class ProblemDocument(BaseModel):
    source: str
    unfaithful_claims: int


class ProjectDetailResponse(BaseModel):
    id: str
    name: str
    trace_count: int
    avg_faithfulness_7d: Optional[float] = None
    unfaithful_claim_rate: Optional[float] = None
    top_problem_documents: list[ProblemDocument]


class UsageDayItem(BaseModel):
    date: str
    traces_processed: int


class UsageTodayItem(BaseModel):
    traces_ingested: int
    traces_processed: int
    processing_limit: int
    limit_reached: bool


class UsageResponse(BaseModel):
    today: UsageTodayItem
    last_7_days: list[UsageDayItem]


class DocumentProblemItem(BaseModel):
    source_document: str
    total_claims: int
    unfaithful_claims: int
    unfaithful_rate: float
    avg_faithfulness: float


class DocumentsProblemsResponse(BaseModel):
    documents: list[DocumentProblemItem]


class QueryClusterItem(BaseModel):
    id: str
    label: str
    trace_count: int
    avg_faithfulness: float
    unfaithful_rate: float


class ClustersResponse(BaseModel):
    clusters: list[QueryClusterItem]
