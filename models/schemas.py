"""
models/schemas.py  —  All Pydantic schemas used across the application.

Data flow: API responses → DrawingRecord → filtered context → LLM → ChatResponse
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


# ─────────────────────────────────────────────────────────────────
# MongoDB API Response Models (raw shapes from the 4 APIs)
# ─────────────────────────────────────────────────────────────────

class DrawingRecord(BaseModel):
    """Single record from API 1 — main drawing text data."""
    id: str = Field("", alias="_id")
    project_id: int = Field(0, alias="projectId")
    set_id: int = Field(0, alias="setId")
    set_name: str = Field("", alias="setName")
    trade_id: int = Field(0, alias="tradeId")
    set_trade: str = Field("", alias="setTrade")
    drawing_id: int = Field(0, alias="drawingId")
    drawing_name: str = Field("", alias="drawingName")
    drawing_title: str = Field("", alias="drawingTitle")
    page: int = 1
    text: str = ""
    csi_division: list[str] = Field(default_factory=list, alias="csi_division")
    trade: str = ""
    trades: list[str] = Field(default_factory=list)
    is_deleted: bool = Field(False, alias="isDeleted")

    class Config:
        populate_by_name = True


class DrawingDataResponse(BaseModel):
    """Wrapper from API 1."""
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class UniqueListResponse(BaseModel):
    """Wrapper for APIs 2, 3, 4 — all return {success, message, data:{list, count}}."""
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
# Intent Detection
# ─────────────────────────────────────────────────────────────────

class IntentResult(BaseModel):
    """Extracted intent from the user query."""
    trade: str                          # e.g. "Plumbing"
    csi_divisions: list[str]            # e.g. ["22 - Plumbing"]
    document_type: str                  # scope | exhibit | report | takeoff | specification | extract
    intent: str                         # generate | extract | summarize | list
    keywords: list[str]                 # supporting keyword matches
    confidence: float                   # 0.0 – 1.0 (from keyword matching)
    raw_query: str                      # original query text


# ─────────────────────────────────────────────────────────────────
# Token Tracking
# ─────────────────────────────────────────────────────────────────

class TokenUsage(BaseModel):
    """Token counts for a single LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0              # Estimated cost

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


class SessionTokenSummary(BaseModel):
    """Accumulated token usage for an entire session."""
    session_id: str
    total_input: int = 0
    total_output: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0


# ─────────────────────────────────────────────────────────────────
# Session / Memory
# ─────────────────────────────────────────────────────────────────

class SessionMessage(BaseModel):
    """A single turn in the conversation."""
    role: str                           # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Full conversation state for one session."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: int = 0
    messages: list[SessionMessage] = Field(default_factory=list)
    token_summary: SessionTokenSummary = Field(
        default_factory=lambda: SessionTokenSummary(session_id="")
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────
# Hallucination Guard
# ─────────────────────────────────────────────────────────────────

class HallucinationCheckResult(BaseModel):
    """Result of the hallucination validation step."""
    is_reliable: bool                   # True if output can be trusted
    confidence_score: float             # 0.0 – 1.0
    unsupported_claims: list[str]       # Potential hallucinations found
    clarification_questions: list[str]  # Follow-up Qs to ask user
    recommendation: str                 # "proceed" | "clarify" | "reject"


# ─────────────────────────────────────────────────────────────────
# Document Generation
# ─────────────────────────────────────────────────────────────────

class GeneratedDocument(BaseModel):
    """Metadata for a generated Word document."""
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    file_path: str
    download_url: str
    project_id: int
    trade: str
    document_type: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    size_bytes: int = 0


# ─────────────────────────────────────────────────────────────────
# API Request / Response (HTTP layer)
# ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming request to POST /api/chat."""
    project_id: int = Field(..., description="MongoDB project ID, e.g. 7276")
    query: str = Field(..., min_length=3, description="User's natural-language question")
    session_id: Optional[str] = Field(None, description="Pass existing session ID to continue conversation")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    generate_document: bool = Field(True, description="Whether to generate a .docx file")


class ChatResponse(BaseModel):
    """Response from POST /api/chat."""
    session_id: str
    project_name: str = ""              # "Granville Hotel (ID: 7298)" or fallback
    answer: str                         # LLM-generated answer (markdown)
    document: Optional[GeneratedDocument] = None
    intent: Optional[IntentResult] = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    groundedness_score: float = 0.0
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    # Contextual follow-up questions generated after each response.
    # Rendered as clickable pill chips in the UI (see scopegap-agent_2.html).
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="3-5 suggested follow-up questions based on the generated scope",
    )
    pipeline_ms: int = 0               # Total pipeline latency in ms
    cached: bool = False               # Was response served from cache?
    # Granular per-step token tracking for the entire pipeline
    token_log: Optional[dict[str, Any]] = Field(
        None,
        description="Per-step token counts: {steps: {step_name: {input_tokens, output_tokens, cost_usd, elapsed_ms}}, totals: {...}}",
    )


class ProjectContextResponse(BaseModel):
    """Response from GET /api/projects/{project_id}/context."""
    project_id: int
    trades: list[str]
    csi_divisions: list[str]
    total_text_items: int
    cached: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    redis: str = "unknown"
    openai: str = "unknown"
