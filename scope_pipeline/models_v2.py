"""scope_pipeline/models_v2.py — Phase 12 UI-integration data models.

Extends (does not replace) scope_pipeline/models.py with models needed for
the UI layer: per-trade versioned run history, project-scoped sessions,
user-drawn drawing highlights, a lightweight highlight index, and incoming
webhook events.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from scope_pipeline.models import DocumentSet, ScopeGapResult, SessionMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _run_id() -> str:
    return f"run_{uuid4().hex[:10]}"


def _hl_id() -> str:
    return f"hl_{uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# TradeRunRecord — single pipeline run record for one trade
# ---------------------------------------------------------------------------

class TradeRunRecord(BaseModel):
    """Record of a single pipeline run for a specific trade."""

    run_id: str = Field(default_factory=_run_id)
    job_id: Optional[str] = None
    status: str = "pending"          # pending | running | completed | failed
    attempts: int = 0
    completeness_pct: float = 0.0
    items_count: int = 0
    ambiguities_count: int = 0
    gotchas_count: int = 0
    token_usage: int = 0
    cost_usd: float = 0.0
    documents: Optional[DocumentSet] = None
    result: Optional[ScopeGapResult] = None
    started_at: datetime = Field(default_factory=_now_utc)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# TradeResultContainer — versioned run history for one trade
# ---------------------------------------------------------------------------

class TradeResultContainer(BaseModel):
    """Holds all pipeline runs for a single trade, keeping only the latest N."""

    trade: str
    current_version: int = 0
    versions: list[TradeRunRecord] = Field(default_factory=list)
    latest_result: Optional[ScopeGapResult] = None
    max_versions: int = 5

    def add_run(self, record: TradeRunRecord) -> "TradeResultContainer":
        """Return a new container with the run appended and old versions trimmed.

        Immutability: never mutates self — always returns a new instance.
        """
        new_versions = list(self.versions) + [record]
        # Trim to most-recent max_versions entries
        if len(new_versions) > self.max_versions:
            new_versions = new_versions[-self.max_versions:]

        new_result = record.result if record.result is not None else self.latest_result

        return self.model_copy(update={
            "versions": new_versions,
            "current_version": self.current_version + 1,
            "latest_result": new_result,
        })


# ---------------------------------------------------------------------------
# ProjectSession — per-project session holding all trade results
# ---------------------------------------------------------------------------

class ProjectSession(BaseModel):
    """Persistent, project-scoped session aggregating results for all trades."""

    project_id: int
    project_name: str = ""
    set_ids: Optional[list[Union[int, str]]] = None

    # Keyed by trade name (lowercased)
    trade_results: dict[str, TradeResultContainer] = Field(default_factory=dict)

    # Shared state across trades
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict)
    gotcha_acknowledgments: list[str] = Field(default_factory=list)
    ignored_items: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    @property
    def session_key(self) -> str:
        """Return a stable cache key for this session.

        If set_ids are provided the key encodes them in sorted order so that
        any ordering of the same set IDs maps to the same key.
        """
        if self.set_ids:
            sorted_ids = "_".join(str(s) for s in sorted(self.set_ids, key=str))
            return f"proj_{self.project_id}_sets_{sorted_ids}"
        return f"proj_{self.project_id}"


# ---------------------------------------------------------------------------
# Highlight — user-drawn annotation on a drawing page
# ---------------------------------------------------------------------------

class Highlight(BaseModel):
    """User-drawn rectangular annotation on a specific drawing page."""

    id: str = Field(default_factory=_hl_id)
    drawing_name: str
    page: int = 1

    # Bounding box in normalised [0,1] coordinates relative to page dimensions
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    color: str = "#FFEB3B"
    opacity: float = 0.3
    label: str = ""
    trade: Optional[str] = None
    critical: bool = False
    comment: str = ""

    # Linked scope items
    scope_item_id: Optional[str] = None
    scope_item_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)


# ---------------------------------------------------------------------------
# HighlightIndex — lightweight per-project index of all highlights
# ---------------------------------------------------------------------------

class HighlightIndex(BaseModel):
    """Lightweight index of highlights grouped by drawing name.

    drawings maps drawing_name -> list[Highlight].
    """

    project_id: int
    user_id: Optional[str] = None
    # drawing_name -> list of highlights on that drawing
    drawings: dict[str, list[Highlight]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# WebhookEvent — incoming event from the iFieldSmart platform
# ---------------------------------------------------------------------------

class WebhookEvent(BaseModel):
    """Incoming webhook payload from the iFieldSmart platform."""

    event: str                          # e.g. "drawings.updated", "project.created"
    project_id: int
    project_name: str = ""
    set_id: Optional[Union[int, str]] = None
    changed_trades: list[str] = Field(default_factory=list)
    drawing_count: int = 0
    timestamp: datetime = Field(default_factory=_now_utc)
