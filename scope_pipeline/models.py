"""scope_pipeline/models.py — Pydantic data models for the 7-agent scope gap extraction pipeline.

All models used by pipeline agents, API layer, and session management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prefixed_id(prefix: str) -> str:
    """Generate a short prefixed ID, e.g. 'itm_a3f7b2c1'."""
    return f"{prefix}{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Pipeline Input
# ---------------------------------------------------------------------------

class ScopeGapRequest(BaseModel):
    """Input parameters for a scope gap extraction run."""

    project_id: int
    trade: str
    set_ids: Optional[list[Union[int, str]]] = None
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent 1 — Extraction
# ---------------------------------------------------------------------------

class ScopeItem(BaseModel):
    """Single scope item extracted from drawing notes (Agent 1 output)."""

    id: str = Field(default_factory=lambda: _prefixed_id("itm_"))
    text: str
    drawing_name: str
    drawing_title: Optional[str] = None
    page: int = 1
    source_snippet: str = ""
    confidence: float = 0.0
    csi_hint: Optional[str] = None
    source_record_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent 2 — Classification
# ---------------------------------------------------------------------------

class ClassifiedItem(ScopeItem):
    """Scope item with trade/CSI classification (Agent 2 output)."""

    trade: str
    csi_code: str
    csi_division: str
    classification_confidence: float
    classification_reason: str


# ---------------------------------------------------------------------------
# Agent 3 — Ambiguity Detection
# ---------------------------------------------------------------------------

class AmbiguityItem(BaseModel):
    """Trade-overlap ambiguity detected between scope items (Agent 3 output)."""

    id: str = Field(default_factory=lambda: _prefixed_id("amb_"))
    scope_text: str
    competing_trades: list[str]
    severity: str
    recommendation: str
    source_items: list[str]
    drawing_refs: list[str]


# ---------------------------------------------------------------------------
# Agent 4 — Gotcha Detection
# ---------------------------------------------------------------------------

class GotchaItem(BaseModel):
    """Hidden risk or commonly-missed scope item (Agent 4 output)."""

    id: str = Field(default_factory=lambda: _prefixed_id("gtc_"))
    risk_type: str
    description: str
    severity: str
    affected_trades: list[str]
    recommendation: str
    drawing_refs: list[str]


# ---------------------------------------------------------------------------
# Agent 5 — Completeness Check
# ---------------------------------------------------------------------------

class CompletenessReport(BaseModel):
    """Coverage and hallucination report (Agent 5 output)."""

    drawing_coverage_pct: float
    csi_coverage_pct: float
    hallucination_count: int
    overall_pct: float
    missing_drawings: list[str]
    missing_csi_codes: list[str]
    hallucinated_items: list[str]
    is_complete: bool
    attempt: int


# ---------------------------------------------------------------------------
# Agent 6 — Quality Assurance
# ---------------------------------------------------------------------------

class QualityCorrection(BaseModel):
    """Single correction made by the QA agent."""

    item_id: str
    field: str
    old_value: str
    new_value: str
    reason: str


class QualityReport(BaseModel):
    """Quality assurance summary (Agent 6 output)."""

    accuracy_score: float
    corrections: list[QualityCorrection]
    validated_items: list[str]
    removed_items: list[str]
    summary: str


# ---------------------------------------------------------------------------
# Document Output
# ---------------------------------------------------------------------------

class DocumentSet(BaseModel):
    """Paths to generated output documents."""

    word_path: Optional[str] = None
    pdf_path: Optional[str] = None
    csv_path: Optional[str] = None
    json_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Pipeline Statistics
# ---------------------------------------------------------------------------

class PipelineStats(BaseModel):
    """Timing, token, and cost metrics for a pipeline run."""

    total_ms: int
    attempts: int
    tokens_used: int
    estimated_cost_usd: float
    per_agent_timing: dict[str, int]
    records_processed: int
    items_extracted: int


# ---------------------------------------------------------------------------
# Full Pipeline Result
# ---------------------------------------------------------------------------

class ScopeGapResult(BaseModel):
    """Complete output of a scope gap extraction pipeline run."""

    project_id: int
    project_name: str
    trade: str
    items: list[ClassifiedItem]
    ambiguities: list[AmbiguityItem]
    gotchas: list[GotchaItem]
    completeness: CompletenessReport
    quality: QualityReport
    documents: DocumentSet
    pipeline_stats: PipelineStats


# ---------------------------------------------------------------------------
# Session & Conversation
# ---------------------------------------------------------------------------

class SessionMessage(BaseModel):
    """Single message in a scope-gap conversation session."""

    role: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: Optional[dict[str, Any]] = None


class PipelineRun(BaseModel):
    """Record of a single pipeline execution within a session."""

    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    job_id: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "pending"
    attempts: int = 0
    completeness_pct: float = 0.0
    items_count: int = 0
    ambiguities_count: int = 0
    gotchas_count: int = 0
    token_usage: int = 0
    cost_usd: float = 0.0
    documents: Optional[DocumentSet] = None


class ScopeGapSession(BaseModel):
    """Persistent session tracking scope gap conversations and pipeline runs."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    user_id: Optional[str] = None
    project_id: int
    trade: str
    set_ids: Optional[list[Union[int, str]]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    runs: list[PipelineRun] = Field(default_factory=list)
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict)
    gotcha_acknowledgments: list[str] = Field(default_factory=list)
    ignored_items: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)
    latest_result: Optional[ScopeGapResult] = None


# ---------------------------------------------------------------------------
# Agent Infrastructure
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """Generic result wrapper returned by any pipeline agent."""

    agent: str
    data: Any
    elapsed_ms: int
    tokens_used: int
    attempt: int


class AgentError(Exception):
    """Raised when a pipeline agent fails."""

    def __init__(self, agent_name: str, message: str) -> None:
        self.agent_name = agent_name
        self.message = message
        super().__init__(f"[{agent_name}] {message}")


class MergedResults(BaseModel):
    """Intermediate aggregation of outputs from multiple agents."""

    items: list[ScopeItem] = Field(default_factory=list)
    classified_items: list[ClassifiedItem] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    gotchas: list[GotchaItem] = Field(default_factory=list)


class JobStatus(BaseModel):
    """Status of an asynchronous pipeline job."""

    job_id: str
    status: str = "pending"
    progress: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
