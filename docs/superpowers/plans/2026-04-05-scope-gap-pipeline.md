# Scope Gap Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 7-agent scope gap extraction pipeline with backpropagation loop, hybrid blocking/background execution, 3-layer session persistence, SSE streaming, and 4-format document generation inside the existing construction-intelligence-agent.

**Architecture:** New `scope_pipeline/` module alongside existing code. Pipeline of Specialists: Extraction → parallel fan-out (Classification + Ambiguity + Gotcha) → Completeness check (pure Python) → Quality review → Document generation. Backpropagation loop up to 3 attempts for completeness. Hybrid routing: <2000 records blocking+SSE, >=2000 background job.

**Tech Stack:** Python 3.11+, FastAPI, OpenAI (gpt-4.1+), asyncio, pydantic, python-docx, reportlab, Redis, S3 (boto3), SSE (sse-starlette), pytest

**Design Spec:** `docs/superpowers/specs/2026-04-05-scope-gap-pipeline-design.md`

---

## File Map

### New Files (scope_pipeline/)

| File | Responsibility |
|------|---------------|
| `scope_pipeline/__init__.py` | Package init |
| `scope_pipeline/models.py` | All Pydantic models: ScopeItem, ClassifiedItem, AmbiguityItem, GotchaItem, CompletenessReport, QualityReport, ScopeGapResult, PipelineStats, DocumentSet, ScopeGapSession, PipelineRun, SessionMessage |
| `scope_pipeline/config.py` | Pipeline-specific settings (thresholds, model, token limits) |
| `scope_pipeline/agents/__init__.py` | Agents package init |
| `scope_pipeline/agents/base_agent.py` | Abstract BaseAgent: retry, timing, progress emission, token tracking |
| `scope_pipeline/agents/extraction_agent.py` | Agent 1: raw text → ScopeItem[] |
| `scope_pipeline/agents/classification_agent.py` | Agent 2: ScopeItem[] → ClassifiedItem[] |
| `scope_pipeline/agents/ambiguity_agent.py` | Agent 3: ScopeItem[] → AmbiguityItem[] |
| `scope_pipeline/agents/gotcha_agent.py` | Agent 4: ScopeItem[] → GotchaItem[] |
| `scope_pipeline/agents/completeness_agent.py` | Agent 5: pure Python → CompletenessReport |
| `scope_pipeline/agents/quality_agent.py` | Agent 6: merged → QualityReport |
| `scope_pipeline/services/__init__.py` | Services package init |
| `scope_pipeline/services/document_agent.py` | Agent 7: Word/PDF/CSV/JSON generation |
| `scope_pipeline/services/job_manager.py` | Background job tracking + semaphore |
| `scope_pipeline/services/session_manager.py` | 3-layer session persistence (L1/L2/L3) |
| `scope_pipeline/services/chat_handler.py` | Follow-up Q&A about scope reports |
| `scope_pipeline/services/progress_emitter.py` | SSE event generation |
| `scope_pipeline/orchestrator.py` | Master pipeline controller with backpropagation |
| `scope_pipeline/routers/__init__.py` | Router package init |
| `scope_pipeline/routers/scope_gap.py` | All API endpoints |

### New Test Files

| File | Tests |
|------|-------|
| `tests/scope_pipeline/__init__.py` | Test package init |
| `tests/scope_pipeline/test_models.py` | Model validation, serialization |
| `tests/scope_pipeline/test_base_agent.py` | Retry, timing, error handling |
| `tests/scope_pipeline/test_extraction_agent.py` | Extraction with mocked LLM |
| `tests/scope_pipeline/test_classification_agent.py` | Classification with mocked LLM |
| `tests/scope_pipeline/test_ambiguity_agent.py` | Ambiguity detection with mocked LLM |
| `tests/scope_pipeline/test_gotcha_agent.py` | Gotcha scanning with mocked LLM |
| `tests/scope_pipeline/test_completeness_agent.py` | Coverage calculation, hallucination detection |
| `tests/scope_pipeline/test_quality_agent.py` | Quality review with mocked LLM |
| `tests/scope_pipeline/test_document_agent.py` | 4-format generation |
| `tests/scope_pipeline/test_orchestrator.py` | Full pipeline with mocked agents |
| `tests/scope_pipeline/test_job_manager.py` | Job lifecycle, semaphore, cancellation |
| `tests/scope_pipeline/test_session_manager.py` | 3-layer persistence, decisions |
| `tests/scope_pipeline/test_router.py` | API endpoints, hybrid routing |

### Modified Files (existing)

| File | Change |
|------|--------|
| `config.py` | Add ~20 lines: scope gap env vars |
| `main.py` | Add ~15 lines: import router, init pipeline + job_manager in lifespan |
| `requirements.txt` | Add 2 lines: `reportlab>=4.0`, `sse-starlette>=1.6.0` |

---

## Task Overview (22 Tasks)

| # | Task | Parallel Group | Depends On |
|---|------|---------------|------------|
| 1 | Foundation: package structure + config + dependencies | A | - |
| 2 | Data models (models.py) | A | - |
| 3 | Progress emitter (SSE events) | A | - |
| 4 | Base agent class | B | 2, 3 |
| 5 | Completeness agent (pure Python) | C | 2 |
| 6 | Extraction agent | C | 4 |
| 7 | Classification agent | C | 4 |
| 8 | Ambiguity agent | C | 4 |
| 9 | Gotcha agent | C | 4 |
| 10 | Quality agent | D | 4, 5 |
| 11 | Document agent (Word) | D | 2 |
| 12 | Document agent (PDF + CSV + JSON) | D | 11 |
| 13 | Session manager (3-layer) | E | 2 |
| 14 | Chat handler (follow-up Q&A) | E | 13 |
| 15 | Job manager | F | 3 |
| 16 | Orchestrator (pipeline controller) | G | 5-10, 12, 13 |
| 17 | Router (API endpoints) | H | 15, 16, 14 |
| 18 | Integration (main.py + config.py) | I | 17 |
| 19 | Integration test (full pipeline) | J | 18 |
| 20 | Security hardening | K | 18 |
| 21 | CLAUDE.md update | L | 18 |
| 22 | Final verification | L | 19, 20, 21 |

**Parallel groups:** Tasks in group C (agents 5-9) can all run in parallel. Tasks in group D (10-12) can run in parallel. Tasks in group E (13-14) can run in parallel with D.

---

## Task 1: Foundation — Package Structure + Config + Dependencies

**Files:**
- Create: `scope_pipeline/__init__.py`
- Create: `scope_pipeline/agents/__init__.py`
- Create: `scope_pipeline/services/__init__.py`
- Create: `scope_pipeline/routers/__init__.py`
- Create: `scope_pipeline/config.py`
- Create: `tests/scope_pipeline/__init__.py`
- Modify: `config.py` (lines 82-92, add after S3 section)
- Modify: `requirements.txt` (append 2 lines)

- [ ] **Step 1: Create package directories and __init__.py files**

```python
# scope_pipeline/__init__.py
"""Multi-agent scope gap extraction pipeline."""

# scope_pipeline/agents/__init__.py
"""Pipeline agent implementations."""

# scope_pipeline/services/__init__.py
"""Pipeline services: documents, jobs, sessions."""

# scope_pipeline/routers/__init__.py
"""Pipeline API routers."""

# tests/scope_pipeline/__init__.py
"""Scope pipeline tests."""
```

- [ ] **Step 2: Create scope_pipeline/config.py**

```python
"""
scope_pipeline/config.py — Pipeline-specific settings.

Reads from the main Settings class and provides pipeline-specific defaults.
"""

from dataclasses import dataclass
from config import get_settings


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration."""
    # Model
    model: str
    extraction_max_tokens: int
    classification_max_tokens: int
    quality_max_tokens: int
    
    # Pipeline behavior
    max_attempts: int
    completeness_threshold: float
    record_threshold: int
    max_concurrent_jobs: int
    
    # Inherited from main settings
    openai_api_key: str
    max_context_tokens: int
    storage_backend: str
    s3_bucket_name: str
    s3_region: str
    s3_agent_prefix: str
    docs_dir: str


def get_pipeline_config() -> PipelineConfig:
    """Build pipeline config from environment + main settings."""
    import os
    s = get_settings()
    return PipelineConfig(
        model=os.getenv("SCOPE_GAP_MODEL", "gpt-4.1"),
        extraction_max_tokens=int(os.getenv("SCOPE_GAP_EXTRACTION_MAX_TOKENS", "8000")),
        classification_max_tokens=int(os.getenv("SCOPE_GAP_CLASSIFICATION_MAX_TOKENS", "4000")),
        quality_max_tokens=int(os.getenv("SCOPE_GAP_QUALITY_MAX_TOKENS", "4000")),
        max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "3")),
        completeness_threshold=float(os.getenv("SCOPE_GAP_COMPLETENESS_THRESHOLD", "95.0")),
        record_threshold=int(os.getenv("SCOPE_GAP_RECORD_THRESHOLD", "2000")),
        max_concurrent_jobs=int(os.getenv("SCOPE_GAP_MAX_CONCURRENT_JOBS", "3")),
        openai_api_key=s.openai_api_key,
        max_context_tokens=s.max_context_tokens,
        storage_backend=s.storage_backend,
        s3_bucket_name=s.s3_bucket_name,
        s3_region=s.s3_region,
        s3_agent_prefix=s.s3_agent_prefix,
        docs_dir=s.docs_dir,
    )
```

- [ ] **Step 3: Add scope gap env vars to config.py**

In `config.py`, add after the S3 section (line 88):

```python
    # ── Scope Gap Pipeline (Phase 11) ────────────────────
    scope_gap_model: str = "gpt-4.1"
    scope_gap_max_concurrent_jobs: int = 3
    scope_gap_completeness_threshold: float = 95.0
    scope_gap_max_attempts: int = 3
    scope_gap_record_threshold: int = 2000
    scope_gap_extraction_max_tokens: int = 8000
    scope_gap_classification_max_tokens: int = 4000
    scope_gap_quality_max_tokens: int = 4000
```

- [ ] **Step 4: Add dependencies to requirements.txt**

Append to `requirements.txt`:

```
reportlab>=4.0
sse-starlette>=1.6.0
```

- [ ] **Step 5: Install dependencies**

Run: `pip install reportlab>=4.0 sse-starlette>=1.6.0`
Expected: successful installation

- [ ] **Step 6: Verify imports**

Run: `python -c "from scope_pipeline.config import get_pipeline_config; c = get_pipeline_config(); print(f'Model: {c.model}, Threshold: {c.completeness_threshold}')" `
Expected: `Model: gpt-4.1, Threshold: 95.0`

- [ ] **Step 7: Commit**

```bash
git add scope_pipeline/ tests/scope_pipeline/ config.py requirements.txt
git commit -m "feat(scope-gap): foundation — package structure, config, dependencies"
```

---

## Task 2: Data Models

**Files:**
- Create: `scope_pipeline/models.py`
- Create: `tests/scope_pipeline/test_models.py`

- [ ] **Step 1: Write test_models.py**

```python
"""tests/scope_pipeline/test_models.py — Model validation tests."""

import pytest
from datetime import datetime


def test_scope_item_creation():
    from scope_pipeline.models import ScopeItem
    item = ScopeItem(
        text="Install 200A panel board",
        drawing_name="E-103",
        page=3,
        source_snippet="200A panel board, 42-circuit",
        confidence=0.95,
    )
    assert item.id  # auto-generated
    assert item.text == "Install 200A panel board"
    assert item.drawing_name == "E-103"
    assert item.page == 3
    assert item.confidence == 0.95


def test_classified_item_extends_scope_item():
    from scope_pipeline.models import ClassifiedItem
    item = ClassifiedItem(
        text="Install panel",
        drawing_name="E-103",
        page=1,
        source_snippet="panel board",
        confidence=0.9,
        trade="Electrical",
        csi_code="26 24 16",
        csi_division="26 - Electrical",
        classification_confidence=0.88,
        classification_reason="Panel boards fall under Division 26",
    )
    assert item.trade == "Electrical"
    assert item.csi_code == "26 24 16"


def test_ambiguity_item():
    from scope_pipeline.models import AmbiguityItem
    amb = AmbiguityItem(
        scope_text="Flashing at roof penetrations",
        competing_trades=["Roofing", "Sheet Metal"],
        severity="high",
        recommendation="Assign to Roofing",
        source_items=["item_1"],
        drawing_refs=["A-201"],
    )
    assert amb.id
    assert amb.severity == "high"
    assert len(amb.competing_trades) == 2


def test_gotcha_item():
    from scope_pipeline.models import GotchaItem
    g = GotchaItem(
        risk_type="hidden_cost",
        description="Temporary power not scoped",
        severity="high",
        affected_trades=["Electrical"],
        recommendation="Add to Electrical",
        drawing_refs=["E-101"],
    )
    assert g.risk_type == "hidden_cost"


def test_completeness_report_is_complete():
    from scope_pipeline.models import CompletenessReport
    r = CompletenessReport(
        drawing_coverage_pct=98.0,
        csi_coverage_pct=100.0,
        hallucination_count=0,
        overall_pct=98.4,
        missing_drawings=[],
        missing_csi_codes=[],
        hallucinated_items=[],
        is_complete=True,
        attempt=1,
    )
    assert r.is_complete is True
    assert r.overall_pct == 98.4


def test_completeness_report_not_complete():
    from scope_pipeline.models import CompletenessReport
    r = CompletenessReport(
        drawing_coverage_pct=80.0,
        csi_coverage_pct=70.0,
        hallucination_count=3,
        overall_pct=72.0,
        missing_drawings=["E-104", "E-107"],
        missing_csi_codes=["26 05 00"],
        hallucinated_items=["itm_bad1", "itm_bad2", "itm_bad3"],
        is_complete=False,
        attempt=1,
    )
    assert r.is_complete is False
    assert len(r.missing_drawings) == 2


def test_scope_gap_request():
    from scope_pipeline.models import ScopeGapRequest
    req = ScopeGapRequest(project_id=7298, trade="Electrical")
    assert req.project_id == 7298
    assert req.set_ids is None

    req2 = ScopeGapRequest(project_id=7298, trade="Electrical", set_ids=[4730])
    assert req2.set_ids == [4730]


def test_pipeline_stats():
    from scope_pipeline.models import PipelineStats
    stats = PipelineStats(
        total_ms=267000,
        attempts=2,
        tokens_used=142000,
        estimated_cost_usd=0.23,
        per_agent_timing={"extraction": 62000, "classification": 18000},
        records_processed=11360,
        items_extracted=847,
    )
    assert stats.total_ms == 267000
    assert stats.per_agent_timing["extraction"] == 62000


def test_scope_gap_session():
    from scope_pipeline.models import ScopeGapSession
    session = ScopeGapSession(
        project_id=7298,
        trade="Electrical",
    )
    assert session.id
    assert session.runs == []
    assert session.ambiguity_resolutions == {}
    assert session.messages == []


def test_session_message():
    from scope_pipeline.models import SessionMessage
    msg = SessionMessage(role="user", content="Why was fire stopping flagged?")
    assert msg.role == "user"
    assert msg.timestamp


def test_scope_gap_result_serialization():
    from scope_pipeline.models import (
        ScopeGapResult, ClassifiedItem, CompletenessReport,
        QualityReport, PipelineStats, DocumentSet,
    )
    result = ScopeGapResult(
        project_id=7298,
        project_name="Granville Hotel",
        trade="Electrical",
        items=[],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100.0, csi_coverage_pct=100.0,
            hallucination_count=0, overall_pct=100.0,
            missing_drawings=[], missing_csi_codes=[],
            hallucinated_items=[], is_complete=True, attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=0.97, corrections=[], validated_items=[],
            removed_items=[], summary="97% accuracy",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=200000, attempts=1, tokens_used=100000,
            estimated_cost_usd=0.15, per_agent_timing={},
            records_processed=5000, items_extracted=400,
        ),
    )
    data = result.model_dump()
    assert data["project_id"] == 7298
    assert data["completeness"]["is_complete"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models.py -v`
Expected: FAIL (cannot import scope_pipeline.models)

- [ ] **Step 3: Write models.py**

```python
"""
scope_pipeline/models.py — All Pydantic models for the scope gap pipeline.

Data flow:
  ScopeGapRequest → Orchestrator → Agent chain → ScopeGapResult
  ScopeGapSession tracks runs, user decisions, and conversation history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _uid() -> str:
    return uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Request ───────────────────────────────────────────────────

class ScopeGapRequest(BaseModel):
    project_id: int
    trade: str
    set_ids: Optional[list[int]] = None
    session_id: Optional[str] = None


# ── Agent 1: Extraction ──────────────────────────────────────

class ScopeItem(BaseModel):
    id: str = Field(default_factory=lambda: f"itm_{_uid()}")
    text: str
    drawing_name: str
    drawing_title: Optional[str] = None
    page: int = 1
    source_snippet: str = ""
    confidence: float = 0.0
    csi_hint: Optional[str] = None
    source_record_id: Optional[str] = None


# ── Agent 2: Classification ──────────────────────────────────

class ClassifiedItem(ScopeItem):
    trade: str = ""
    csi_code: str = ""
    csi_division: str = ""
    classification_confidence: float = 0.0
    classification_reason: str = ""


# ── Agent 3: Ambiguity ───────────────────────────────────────

class AmbiguityItem(BaseModel):
    id: str = Field(default_factory=lambda: f"amb_{_uid()}")
    scope_text: str
    competing_trades: list[str] = Field(default_factory=list)
    severity: str = "medium"
    recommendation: str = ""
    source_items: list[str] = Field(default_factory=list)
    drawing_refs: list[str] = Field(default_factory=list)


# ── Agent 4: Gotcha ──────────────────────────────────────────

class GotchaItem(BaseModel):
    id: str = Field(default_factory=lambda: f"gtc_{_uid()}")
    risk_type: str  # hidden_cost | coordination | missing_scope | spec_conflict
    description: str
    severity: str = "medium"
    affected_trades: list[str] = Field(default_factory=list)
    recommendation: str = ""
    drawing_refs: list[str] = Field(default_factory=list)


# ── Agent 5: Completeness ────────────────────────────────────

class CompletenessReport(BaseModel):
    drawing_coverage_pct: float
    csi_coverage_pct: float
    hallucination_count: int
    overall_pct: float
    missing_drawings: list[str] = Field(default_factory=list)
    missing_csi_codes: list[str] = Field(default_factory=list)
    hallucinated_items: list[str] = Field(default_factory=list)
    is_complete: bool = False
    attempt: int = 1


# ── Agent 6: Quality ─────────────────────────────────────────

class QualityCorrection(BaseModel):
    item_id: str
    field: str
    old_value: str
    new_value: str
    reason: str


class QualityReport(BaseModel):
    accuracy_score: float = 0.0
    corrections: list[QualityCorrection] = Field(default_factory=list)
    validated_items: list[ClassifiedItem] = Field(default_factory=list)
    removed_items: list[str] = Field(default_factory=list)
    summary: str = ""


# ── Agent 7: Document ────────────────────────────────────────

class DocumentSet(BaseModel):
    word_path: Optional[str] = None
    pdf_path: Optional[str] = None
    csv_path: Optional[str] = None
    json_path: Optional[str] = None


# ── Pipeline Stats ───────────────────────────────────────────

class PipelineStats(BaseModel):
    total_ms: int = 0
    attempts: int = 1
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    per_agent_timing: dict[str, int] = Field(default_factory=dict)
    records_processed: int = 0
    items_extracted: int = 0


# ── Pipeline Result ──────────────────────────────────────────

class ScopeGapResult(BaseModel):
    project_id: int
    project_name: str = ""
    trade: str = ""
    items: list[ClassifiedItem] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    gotchas: list[GotchaItem] = Field(default_factory=list)
    completeness: CompletenessReport
    quality: QualityReport
    documents: DocumentSet = Field(default_factory=DocumentSet)
    pipeline_stats: PipelineStats = Field(default_factory=PipelineStats)


# ── Session Models ───────────────────────────────────────────

class SessionMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=_now)
    context: Optional[str] = None


class PipelineRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{_uid()}")
    job_id: Optional[str] = None
    started_at: datetime = Field(default_factory=_now)
    completed_at: Optional[datetime] = None
    status: str = "running"  # running | completed | partial | failed
    attempts: int = 0
    completeness_pct: float = 0.0
    items_count: int = 0
    ambiguities_count: int = 0
    gotchas_count: int = 0
    token_usage: int = 0
    cost_usd: float = 0.0
    documents: Optional[DocumentSet] = None


class ScopeGapSession(BaseModel):
    id: str = Field(default_factory=lambda: f"sg_session_{_uid()}")
    user_id: Optional[str] = None
    project_id: int = 0
    trade: str = ""
    set_ids: Optional[list[int]] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    runs: list[PipelineRun] = Field(default_factory=list)
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict)
    gotcha_acknowledgments: list[str] = Field(default_factory=list)
    ignored_items: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)
    latest_result: Optional[ScopeGapResult] = None


# ── Agent Internals ──────────────────────────────────────────

class AgentResult(BaseModel):
    agent: str
    data: BaseModel | list | dict  # type varies per agent
    elapsed_ms: int = 0
    tokens_used: int = 0
    attempt: int = 1

    class Config:
        arbitrary_types_allowed = True


class AgentError(Exception):
    def __init__(self, agent_name: str, message: str):
        self.agent_name = agent_name
        super().__init__(f"Agent '{agent_name}' failed: {message}")


# ── Merged Results (internal) ────────────────────────────────

class MergedResults(BaseModel):
    items: list[ScopeItem] = Field(default_factory=list)
    classified_items: list[ClassifiedItem] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    gotchas: list[GotchaItem] = Field(default_factory=list)


# ── Job Models ───────────────────────────────────────────────

class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | running | completed | partial | failed | cancelled
    progress: Optional[dict] = None
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models.py -v`
Expected: ALL PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/models.py tests/scope_pipeline/test_models.py
git commit -m "feat(scope-gap): data models — all pipeline Pydantic schemas"
```

---

## Task 3: Progress Emitter

**Files:**
- Create: `scope_pipeline/services/progress_emitter.py`
- Create: `tests/scope_pipeline/test_progress_emitter.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_progress_emitter.py"""

import pytest
import asyncio
import json


@pytest.mark.asyncio
async def test_emitter_sends_and_receives():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()
    
    emitter.emit("agent_start", {"agent": "extraction", "message": "Starting..."})
    emitter.emit("agent_complete", {"agent": "extraction", "elapsed_ms": 62000})
    emitter.emit("pipeline_complete", {"total_ms": 267000})
    
    events = []
    async for event in emitter.stream():
        events.append(event)
    
    assert len(events) == 3
    assert events[0]["type"] == "agent_start"
    assert events[0]["data"]["agent"] == "extraction"
    assert events[2]["type"] == "pipeline_complete"


@pytest.mark.asyncio
async def test_emitter_stream_stops_on_terminal_event():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()
    
    emitter.emit("agent_start", {"agent": "extraction"})
    emitter.emit("pipeline_complete", {"total_ms": 100})
    emitter.emit("agent_start", {"agent": "should_not_appear"})
    
    events = []
    async for event in emitter.stream():
        events.append(event)
    
    # Stream stops after pipeline_complete
    assert len(events) == 2


def test_emitter_to_sse_format():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()
    
    sse = emitter.format_sse("agent_start", {"agent": "extraction"})
    assert "event: agent_start" in sse
    assert '"agent": "extraction"' in sse
```

- [ ] **Step 2: Run tests (expect fail)**

Run: `python -m pytest tests/scope_pipeline/test_progress_emitter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement progress_emitter.py**

```python
"""
scope_pipeline/services/progress_emitter.py — SSE event generation.

Agents call emitter.emit(event_type, data) during execution.
The router streams events to the client via SSE.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


_TERMINAL_EVENTS = frozenset({
    "pipeline_complete", "pipeline_failed", "pipeline_partial",
})


class ProgressEmitter:
    """Thread-safe event emitter backed by asyncio.Queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Push an event. Safe to call from any coroutine."""
        if self._closed:
            return
        event = {"type": event_type, "data": data}
        self._queue.put_nowait(event)
        if event_type in _TERMINAL_EVENTS:
            self._closed = True

    async def stream(self):
        """Async generator yielding events. Stops on terminal events."""
        while True:
            try:
                event = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                if self._closed:
                    return
                await asyncio.sleep(0.05)
                continue
            yield event
            if event["type"] in _TERMINAL_EVENTS:
                return

    @staticmethod
    def format_sse(event_type: str, data: dict[str, Any]) -> str:
        """Format a single event as an SSE string."""
        payload = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {payload}\n\n"
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `python -m pytest tests/scope_pipeline/test_progress_emitter.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/services/progress_emitter.py tests/scope_pipeline/test_progress_emitter.py
git commit -m "feat(scope-gap): progress emitter — SSE event streaming"
```

---

## Task 4: Base Agent Class

**Files:**
- Create: `scope_pipeline/agents/base_agent.py`
- Create: `tests/scope_pipeline/test_base_agent.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_base_agent.py"""

import pytest
import asyncio
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_base_agent_returns_result_with_timing():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    class FakeAgent(BaseAgent):
        name = "fake"
        requires_llm = False
        
        async def _execute(self, input_data, context):
            return {"items": [1, 2, 3]}
    
    emitter = ProgressEmitter()
    agent = FakeAgent()
    result = await agent.run({"test": True}, emitter)
    
    assert result.agent == "fake"
    assert result.data == {"items": [1, 2, 3]}
    assert result.elapsed_ms >= 0
    assert result.attempt == 1


@pytest.mark.asyncio
async def test_base_agent_retries_on_failure():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    from scope_pipeline.models import AgentError
    
    call_count = 0
    
    class FailOnceAgent(BaseAgent):
        name = "flaky"
        requires_llm = True
        max_retries = 2
        
        async def _execute(self, input_data, context):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("LLM timeout")
            return {"ok": True}
    
    emitter = ProgressEmitter()
    agent = FailOnceAgent()
    result = await agent.run({}, emitter)
    
    assert result.data == {"ok": True}
    assert result.attempt == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_base_agent_raises_after_max_retries():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    from scope_pipeline.models import AgentError
    
    class AlwaysFailAgent(BaseAgent):
        name = "broken"
        requires_llm = True
        max_retries = 1
        
        async def _execute(self, input_data, context):
            raise RuntimeError("Permanent failure")
    
    emitter = ProgressEmitter()
    agent = AlwaysFailAgent()
    
    with pytest.raises(AgentError, match="broken"):
        await agent.run({}, emitter)
```

- [ ] **Step 2: Run tests (expect fail)**

Run: `python -m pytest tests/scope_pipeline/test_base_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement base_agent.py**

```python
"""
scope_pipeline/agents/base_agent.py — Abstract base for all pipeline agents.

Provides:
  - Automatic timing measurement
  - Per-agent retry with backoff
  - SSE progress emission
  - Token tracking placeholder
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from scope_pipeline.models import AgentError, AgentResult
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for pipeline agents."""

    name: str = "base"
    requires_llm: bool = True
    max_retries: int = 2

    async def run(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> AgentResult:
        """Execute agent with timing, retry, and progress emission."""
        emitter.emit("agent_start", {
            "agent": self.name,
            "message": f"Starting {self.name} agent...",
        })
        start = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result_data = await self._execute(input_data, emitter, **kwargs)
                elapsed = int((time.monotonic() - start) * 1000)

                emitter.emit("agent_complete", {
                    "agent": self.name,
                    "elapsed_ms": elapsed,
                    "attempt": attempt,
                })
                logger.info(
                    "Agent %s completed in %dms (attempt %d)",
                    self.name, elapsed, attempt,
                )
                return AgentResult(
                    agent=self.name,
                    data=result_data,
                    elapsed_ms=elapsed,
                    tokens_used=0,
                    attempt=attempt,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Agent %s attempt %d failed: %s",
                    self.name, attempt, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(min(attempt, 3))

        # All retries exhausted
        emitter.emit("agent_failed", {
            "agent": self.name,
            "error": str(last_error),
        })
        raise AgentError(self.name, str(last_error))

    @abstractmethod
    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> Any:
        """Implement in subclass. Return the agent's result data."""
        ...
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `python -m pytest tests/scope_pipeline/test_base_agent.py -v`
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/agents/base_agent.py tests/scope_pipeline/test_base_agent.py
git commit -m "feat(scope-gap): base agent — retry, timing, progress emission"
```

---

## Task 5: Completeness Agent (Pure Python)

**Files:**
- Create: `scope_pipeline/agents/completeness_agent.py`
- Create: `tests/scope_pipeline/test_completeness_agent.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_completeness_agent.py"""

import pytest


@pytest.mark.asyncio
async def test_100_percent_coverage():
    from scope_pipeline.agents.completeness_agent import CompletenessAgent
    from scope_pipeline.models import ScopeItem, ClassifiedItem, MergedResults
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    agent = CompletenessAgent()
    emitter = ProgressEmitter()
    
    merged = MergedResults(
        items=[
            ScopeItem(text="item1", drawing_name="E-103", page=1, source_snippet="x"),
            ScopeItem(text="item2", drawing_name="E-104", page=1, source_snippet="y"),
        ],
        classified_items=[
            ClassifiedItem(
                text="item1", drawing_name="E-103", page=1, source_snippet="x",
                trade="Electrical", csi_code="26 24 16", csi_division="26 - Electrical",
                classification_confidence=0.9, classification_reason="test",
            ),
            ClassifiedItem(
                text="item2", drawing_name="E-104", page=1, source_snippet="y",
                trade="Electrical", csi_code="26 05 00", csi_division="26 - Electrical",
                classification_confidence=0.9, classification_reason="test",
            ),
        ],
    )
    
    source_drawings = {"E-103", "E-104"}
    source_csi = {"26 24 16", "26 05 00"}
    
    result = await agent.run(
        merged, emitter,
        source_drawings=source_drawings,
        source_csi=source_csi,
        attempt=1,
        threshold=95.0,
    )
    
    report = result.data
    assert report.drawing_coverage_pct == 100.0
    assert report.csi_coverage_pct == 100.0
    assert report.hallucination_count == 0
    assert report.is_complete is True


@pytest.mark.asyncio
async def test_missing_drawings():
    from scope_pipeline.agents.completeness_agent import CompletenessAgent
    from scope_pipeline.models import ScopeItem, ClassifiedItem, MergedResults
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    agent = CompletenessAgent()
    emitter = ProgressEmitter()
    
    merged = MergedResults(
        items=[
            ScopeItem(text="item1", drawing_name="E-103", page=1, source_snippet="x"),
        ],
        classified_items=[
            ClassifiedItem(
                text="item1", drawing_name="E-103", page=1, source_snippet="x",
                trade="Electrical", csi_code="26 24 16", csi_division="26 - Electrical",
                classification_confidence=0.9, classification_reason="test",
            ),
        ],
    )
    
    source_drawings = {"E-103", "E-104", "E-105"}
    source_csi = {"26 24 16"}
    
    result = await agent.run(
        merged, emitter,
        source_drawings=source_drawings,
        source_csi=source_csi,
        attempt=1,
        threshold=95.0,
    )
    
    report = result.data
    assert report.drawing_coverage_pct == pytest.approx(33.3, abs=0.1)
    assert report.is_complete is False
    assert "E-104" in report.missing_drawings
    assert "E-105" in report.missing_drawings


@pytest.mark.asyncio
async def test_hallucination_detection():
    from scope_pipeline.agents.completeness_agent import CompletenessAgent
    from scope_pipeline.models import ScopeItem, ClassifiedItem, MergedResults
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    agent = CompletenessAgent()
    emitter = ProgressEmitter()
    
    hallucinated = ScopeItem(
        id="itm_bad", text="fake item", drawing_name="E-999",
        page=1, source_snippet="does not exist",
    )
    real = ScopeItem(
        text="real item", drawing_name="E-103",
        page=1, source_snippet="real text",
    )
    
    merged = MergedResults(
        items=[real, hallucinated],
        classified_items=[
            ClassifiedItem(
                text="real item", drawing_name="E-103", page=1, source_snippet="real text",
                trade="Electrical", csi_code="26 24 16", csi_division="26 - Electrical",
                classification_confidence=0.9, classification_reason="test",
            ),
        ],
    )
    
    result = await agent.run(
        merged, emitter,
        source_drawings={"E-103"},
        source_csi={"26 24 16"},
        attempt=1,
        threshold=95.0,
    )
    
    report = result.data
    assert report.hallucination_count == 1
    assert "itm_bad" in report.hallucinated_items
```

- [ ] **Step 2: Run tests (expect fail)**

Run: `python -m pytest tests/scope_pipeline/test_completeness_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement completeness_agent.py**

```python
"""
scope_pipeline/agents/completeness_agent.py — Pure Python completeness validation.

NO LLM calls. Measures:
  - Drawing coverage: extracted vs source drawings
  - CSI coverage: extracted vs source CSI codes
  - Hallucination: items referencing non-existent drawings

Weighted formula: (drawing * 0.5) + (csi * 0.3) + (no_hallucination * 0.2)
"""

from __future__ import annotations

from typing import Any

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import CompletenessReport, MergedResults
from scope_pipeline.services.progress_emitter import ProgressEmitter


class CompletenessAgent(BaseAgent):
    name = "completeness"
    requires_llm = False
    max_retries = 1  # no LLM, no point retrying

    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> CompletenessReport:
        merged: MergedResults = input_data
        source_drawings: set[str] = kwargs.get("source_drawings", set())
        source_csi: set[str] = kwargs.get("source_csi", set())
        attempt: int = kwargs.get("attempt", 1)
        threshold: float = kwargs.get("threshold", 95.0)

        # Drawing coverage
        extracted_drawings = {item.drawing_name for item in merged.items}
        missing_drawings = sorted(source_drawings - extracted_drawings)
        drawing_pct = (
            len(extracted_drawings) / len(source_drawings) * 100
            if source_drawings else 100.0
        )

        # CSI coverage
        extracted_csi = {
            item.csi_code
            for item in merged.classified_items
            if item.csi_code
        }
        missing_csi = sorted(source_csi - extracted_csi)
        csi_pct = (
            len(extracted_csi) / len(source_csi) * 100
            if source_csi else 100.0
        )

        # Hallucination detection
        hallucinated = [
            item for item in merged.items
            if source_drawings and item.drawing_name not in source_drawings
        ]

        total_items = max(len(merged.items), 1)
        no_hallucination_pct = (1 - len(hallucinated) / total_items) * 100

        overall = (
            drawing_pct * 0.5
            + csi_pct * 0.3
            + no_hallucination_pct * 0.2
        )

        report = CompletenessReport(
            drawing_coverage_pct=round(drawing_pct, 1),
            csi_coverage_pct=round(csi_pct, 1),
            hallucination_count=len(hallucinated),
            overall_pct=round(overall, 1),
            missing_drawings=missing_drawings,
            missing_csi_codes=missing_csi,
            hallucinated_items=[h.id for h in hallucinated],
            is_complete=overall >= threshold,
            attempt=attempt,
        )

        emitter.emit("completeness", {
            "attempt": attempt,
            "overall_pct": report.overall_pct,
            "drawing_coverage_pct": report.drawing_coverage_pct,
            "csi_coverage_pct": report.csi_coverage_pct,
            "missing_drawings": report.missing_drawings,
            "hallucination_count": report.hallucination_count,
            "is_complete": report.is_complete,
        })

        return report
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `python -m pytest tests/scope_pipeline/test_completeness_agent.py -v`
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/agents/completeness_agent.py tests/scope_pipeline/test_completeness_agent.py
git commit -m "feat(scope-gap): completeness agent — pure Python coverage validation"
```

---

## Tasks 6-9: LLM Agents (Extraction, Classification, Ambiguity, Gotcha)

> **These 4 tasks can run in PARALLEL** — they are independent. Each follows the same pattern: test with mocked OpenAI → implement with system prompt → verify.
>
> Due to the size of this plan, Tasks 6-9 follow an identical structure. I will write Task 6 (Extraction) in full detail as the reference implementation. Tasks 7-9 follow the same pattern with their specific prompts and output models.

### Task 6: Extraction Agent

**Files:**
- Create: `scope_pipeline/agents/extraction_agent.py`
- Create: `tests/scope_pipeline/test_extraction_agent.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_extraction_agent.py"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock


MOCK_LLM_RESPONSE = json.dumps([
    {
        "text": "Install 200A panel board, 42-circuit",
        "drawing_name": "E-103",
        "page": 3,
        "source_snippet": "200A panel board, 42-circuit, surface mounted",
        "confidence": 0.95,
        "csi_hint": "26 24 16"
    },
    {
        "text": "Furnish VRF-CU-C02 electrical connection",
        "drawing_name": "E-103",
        "page": 3,
        "source_snippet": "VRF-CU-C02, 5-ton outdoor unit, provide 208V",
        "confidence": 0.88,
        "csi_hint": "26 05 19"
    },
])


def _make_mock_openai_response(content: str):
    """Build a mock that looks like openai ChatCompletion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 5000
    mock_resp.usage.completion_tokens = 500
    return mock_resp


@pytest.mark.asyncio
async def test_extraction_agent_parses_llm_json():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()
    
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_LLM_RESPONSE)
    )
    agent._client = mock_client
    
    input_data = {
        "drawing_records": [
            {"drawing_name": "E-103", "drawing_title": "Power Plan", "text": "200A panel board, 42-circuit, surface mounted. VRF-CU-C02, 5-ton outdoor unit, provide 208V."},
        ],
        "trade": "Electrical",
        "drawing_list": ["E-103"],
    }
    
    result = await agent.run(input_data, emitter)
    items = result.data
    
    assert len(items) == 2
    assert items[0].text == "Install 200A panel board, 42-circuit"
    assert items[0].drawing_name == "E-103"
    assert items[0].source_snippet == "200A panel board, 42-circuit, surface mounted"
    assert items[0].confidence == 0.95


@pytest.mark.asyncio
async def test_extraction_agent_handles_markdown_fenced_json():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()
    
    fenced = f"```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(fenced)
    )
    agent._client = mock_client
    
    result = await agent.run(
        {"drawing_records": [], "trade": "Electrical", "drawing_list": []},
        emitter,
    )
    assert len(result.data) == 2
```

- [ ] **Step 2: Run tests (expect fail)**

Run: `python -m pytest tests/scope_pipeline/test_extraction_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Implement extraction_agent.py**

```python
"""
scope_pipeline/agents/extraction_agent.py — Agent 1: Extract scope items from drawing text.

Input: dict with drawing_records (list of {drawing_name, drawing_title, text}),
       trade (str), drawing_list (list[str])
Output: list[ScopeItem]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a construction scope extraction expert with 30+ years experience.

TASK: Extract ALL actionable scope items from the drawing notes below for the trade: {trade}.

RULES:
1. Every item MUST include the exact drawing_name it came from (from the drawing header).
2. Every item MUST include a source_snippet: 5-15 words copied VERBATIM from the source text.
3. Every item MUST include the page number from the drawing header.
4. Do NOT invent items not present in the source text.
5. Do NOT merge items from different drawings into one item.
6. If a CSI MasterFormat code is obvious from the text, include it as csi_hint (format: XX XX XX).
7. Extract EVERY specific, actionable requirement — materials, equipment, installations, connections.

AUTHORITATIVE DRAWING LIST (only these drawings exist):
{drawing_list}

Any drawing_name NOT in this list is a hallucination — do NOT reference it.

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"text":"scope description","drawing_name":"E-103","page":3,"source_snippet":"verbatim 5-15 words","confidence":0.95,"csi_hint":"26 24 16"}}]"""


class ExtractionAgent(BaseAgent):
    name = "extraction"
    requires_llm = True
    max_retries = 2

    def __init__(self, api_key: str, model: str, max_tokens: int = 8000):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> list[ScopeItem]:
        records = input_data.get("drawing_records", [])
        trade = input_data.get("trade", "")
        drawing_list = input_data.get("drawing_list", [])

        # Build context grouped by drawing
        context_blocks = []
        for rec in records:
            name = rec.get("drawing_name", "Unknown")
            title = rec.get("drawing_title", "")
            text = rec.get("text", "")
            header = f"=== DRAWING: {name}"
            if title:
                header += f" ({title})"
            header += " ==="
            context_blocks.append(f"{header}\n{text}")

        context = "\n\n".join(context_blocks)

        system = SYSTEM_PROMPT.format(
            trade=trade,
            drawing_list=", ".join(drawing_list),
        )

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Extracting scope from {len(records)} drawing records for {trade}...",
        })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Extract all {trade} scope items:\n\n{context}"},
            ],
            max_tokens=self._max_tokens,
            temperature=0.3,
        )

        raw = response.choices[0].message.content or ""
        items = self._parse_response(raw)

        logger.info(
            "Extraction agent: %d items from %d records (trade=%s)",
            len(items), len(records), trade,
        )
        return items

    def _parse_response(self, raw: str) -> list[ScopeItem]:
        """Parse LLM JSON response with fallback for markdown fences."""
        cleaned = raw.strip()
        # Strip markdown fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: extract array via regex
            match = re.search(r"\[[\s\S]*\]", cleaned)
            if match:
                parsed = json.loads(match.group(0))
            else:
                logger.error("Failed to parse extraction response: %s", cleaned[:200])
                return []

        if not isinstance(parsed, list):
            return []

        items = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            items.append(ScopeItem(
                text=entry.get("text", ""),
                drawing_name=entry.get("drawing_name", "Unknown"),
                drawing_title=entry.get("drawing_title"),
                page=entry.get("page", 1),
                source_snippet=entry.get("source_snippet", ""),
                confidence=float(entry.get("confidence", 0.5)),
                csi_hint=entry.get("csi_hint"),
            ))
        return items
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `python -m pytest tests/scope_pipeline/test_extraction_agent.py -v`
Expected: ALL PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/agents/extraction_agent.py tests/scope_pipeline/test_extraction_agent.py
git commit -m "feat(scope-gap): extraction agent — structured scope extraction from drawings"
```

---

### Task 7: Classification Agent

**Files:**
- Create: `scope_pipeline/agents/classification_agent.py`
- Create: `tests/scope_pipeline/test_classification_agent.py`

> Follows identical pattern to Task 6. System prompt asks LLM to assign trade + CSI code to each ScopeItem. Output: list[ClassifiedItem]. Test mocks OpenAI response with trade assignments.

- [ ] **Step 1: Write test (same mock pattern as Task 6, expects ClassifiedItem output with trade/csi_code fields)**
- [ ] **Step 2: Run test (expect fail)**
- [ ] **Step 3: Implement classification_agent.py with SYSTEM_PROMPT for CSI MasterFormat classification**
- [ ] **Step 4: Run test (expect pass)**
- [ ] **Step 5: Commit**: `git commit -m "feat(scope-gap): classification agent — trade + CSI assignment"`

---

### Task 8: Ambiguity Agent

**Files:**
- Create: `scope_pipeline/agents/ambiguity_agent.py`
- Create: `tests/scope_pipeline/test_ambiguity_agent.py`

> System prompt focuses on detecting trade overlaps (flashing, fire stopping, backing, etc.). Output: list[AmbiguityItem]. Test mocks response with competing trades.

- [ ] **Step 1-5: Same TDD pattern. Commit**: `git commit -m "feat(scope-gap): ambiguity agent — trade overlap detection"`

---

### Task 9: Gotcha Agent

**Files:**
- Create: `scope_pipeline/agents/gotcha_agent.py`
- Create: `tests/scope_pipeline/test_gotcha_agent.py`

> System prompt for hidden costs, coordination issues, missing scope, spec conflicts. Output: list[GotchaItem]. Test mocks response with risk items.

- [ ] **Step 1-5: Same TDD pattern. Commit**: `git commit -m "feat(scope-gap): gotcha agent — hidden risk detection"`

---

## Task 10: Quality Agent

**Files:**
- Create: `scope_pipeline/agents/quality_agent.py`
- Create: `tests/scope_pipeline/test_quality_agent.py`

> System prompt reviews all merged results. Detects duplicates, misclassifications, vague items, hallucinated items from completeness report. Output: QualityReport with corrections + validated_items. Test: mock LLM returns corrections list, verify items updated.

- [ ] **Step 1-5: Same TDD pattern. Commit**: `git commit -m "feat(scope-gap): quality agent — final accuracy review"`

---

## Task 11: Document Agent (Word)

**Files:**
- Create: `scope_pipeline/services/document_agent.py`
- Create: `tests/scope_pipeline/test_document_agent.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_document_agent.py"""

import pytest
import os
from pathlib import Path


@pytest.mark.asyncio
async def test_generate_word_document():
    from scope_pipeline.services.document_agent import DocumentAgent
    from scope_pipeline.models import (
        ClassifiedItem, AmbiguityItem, GotchaItem,
        CompletenessReport, QualityReport, PipelineStats,
    )
    
    agent = DocumentAgent(docs_dir="./test_generated_docs")
    
    items = [
        ClassifiedItem(
            text="Install 200A panel board",
            drawing_name="E-103", drawing_title="Power Plan Level 2",
            page=3, source_snippet="200A panel board, 42-circuit",
            confidence=0.95, trade="Electrical",
            csi_code="26 24 16", csi_division="26 - Electrical",
            classification_confidence=0.9, classification_reason="test",
        ),
    ]
    ambiguities = [
        AmbiguityItem(
            scope_text="Flashing", competing_trades=["Roofing", "Sheet Metal"],
            severity="high", recommendation="Assign to Roofing",
        ),
    ]
    gotchas = [
        GotchaItem(
            risk_type="hidden_cost", description="Temporary power not scoped",
            severity="high", affected_trades=["Electrical"],
            recommendation="Add to Electrical",
        ),
    ]
    completeness = CompletenessReport(
        drawing_coverage_pct=100.0, csi_coverage_pct=100.0,
        hallucination_count=0, overall_pct=100.0,
        missing_drawings=[], missing_csi_codes=[],
        hallucinated_items=[], is_complete=True, attempt=1,
    )
    quality = QualityReport(
        accuracy_score=0.97, corrections=[], validated_items=items,
        removed_items=[], summary="97% accuracy",
    )
    stats = PipelineStats(
        total_ms=200000, attempts=1, tokens_used=100000,
        estimated_cost_usd=0.15, per_agent_timing={},
        records_processed=5000, items_extracted=1,
    )
    
    word_path = await agent.generate_word(
        items=items, ambiguities=ambiguities, gotchas=gotchas,
        completeness=completeness, quality=quality,
        project_id=7298, project_name="Granville Hotel",
        trade="Electrical", stats=stats,
    )
    
    assert word_path is not None
    assert Path(word_path).exists()
    assert word_path.endswith(".docx")
    
    # Cleanup
    os.remove(word_path)
    os.rmdir("./test_generated_docs")
```

- [ ] **Step 2: Run test (expect fail)**

Run: `python -m pytest tests/scope_pipeline/test_document_agent.py::test_generate_word_document -v`
Expected: FAIL

- [ ] **Step 3: Implement document_agent.py (Word generation)**

```python
"""
scope_pipeline/services/document_agent.py — Multi-format document generation.

Generates Word (.docx), PDF (.pdf), CSV (.csv), and JSON (.json) from pipeline results.
All 4 formats run in parallel via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from scope_pipeline.models import (
    ClassifiedItem, AmbiguityItem, GotchaItem,
    CompletenessReport, QualityReport, DocumentSet, PipelineStats,
)

logger = logging.getLogger(__name__)

# Brand colors (matching existing exhibit docs)
DARK_BLUE = RGBColor(0x1E, 0x3A, 0x5F)
MID_BLUE = RGBColor(0x2E, 0x75, 0xB6)
LIGHT_GREY = RGBColor(0xF2, 0xF2, 0xF2)


class DocumentAgent:
    """Generates scope gap reports in 4 formats."""

    def __init__(self, docs_dir: str = "./generated_docs"):
        self._docs_dir = Path(docs_dir)

    async def generate_all(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> DocumentSet:
        """Generate all 4 formats in parallel."""
        word_task = asyncio.to_thread(
            self.generate_word_sync, items, ambiguities, gotchas,
            completeness, quality, project_id, project_name, trade, stats,
        )
        pdf_task = asyncio.to_thread(
            self.generate_pdf_sync, items, ambiguities, gotchas,
            completeness, quality, project_id, project_name, trade, stats,
        )
        csv_task = asyncio.to_thread(
            self.generate_csv_sync, items, project_id, project_name, trade,
        )
        json_task = asyncio.to_thread(
            self.generate_json_sync, items, ambiguities, gotchas,
            completeness, quality, project_id, project_name, trade, stats,
        )

        word_path, pdf_path, csv_path, json_path = await asyncio.gather(
            word_task, pdf_task, csv_task, json_task,
        )

        return DocumentSet(
            word_path=word_path,
            pdf_path=pdf_path,
            csv_path=csv_path,
            json_path=json_path,
        )

    async def generate_word(self, **kwargs) -> str:
        """Async wrapper for Word generation."""
        return await asyncio.to_thread(self.generate_word_sync, **kwargs)

    def generate_word_sync(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        """Generate Word document synchronously."""
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        slug = project_name.replace(" ", "") if project_name else f"Project{project_id}"
        filename = f"scope_gap_{trade.lower()}_{slug}_{project_id}_{uuid4().hex[:8]}.docx"
        filepath = self._docs_dir / filename

        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        # Title
        title = doc.add_heading("SCOPE GAP REPORT", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.color.rgb = DARK_BLUE

        # Project info
        info = doc.add_paragraph()
        info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        info.add_run(f"Project: {project_name} (ID: {project_id})\n").bold = True
        info.add_run(f"Trade: {trade}\n")
        info.add_run(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
        info.add_run(f"Pipeline: {stats.attempts} attempt(s), {completeness.overall_pct}% coverage\n")

        # Executive Summary
        doc.add_heading("1. Executive Summary", level=1)
        summary = doc.add_paragraph()
        summary.add_run(f"{len(items)} scope items extracted\n")
        summary.add_run(f"{len(ambiguities)} ambiguities detected\n")
        summary.add_run(f"{len(gotchas)} gotcha risks identified\n")
        summary.add_run(f"{completeness.overall_pct}% completeness\n")
        summary.add_run(f"{quality.accuracy_score:.0%} quality score\n")

        # Scope Inclusions (grouped by drawing)
        doc.add_heading("2. Scope Inclusions", level=1)
        by_drawing: dict[str, list[ClassifiedItem]] = {}
        for item in items:
            by_drawing.setdefault(item.drawing_name, []).append(item)

        for drawing_name, drawing_items in sorted(by_drawing.items()):
            title_text = drawing_items[0].drawing_title or ""
            doc.add_heading(f"Drawing {drawing_name}: {title_text}", level=2)
            for item in drawing_items:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(item.text).bold = True
                p.add_run(f"\nCSI: {item.csi_code} | Confidence: {item.confidence:.0%}")
                p.add_run(f'\nSource: "{item.source_snippet}"')

        # Ambiguities
        if ambiguities:
            doc.add_heading("3. Ambiguities", level=1)
            for amb in ambiguities:
                p = doc.add_paragraph()
                severity_label = amb.severity.upper()
                p.add_run(f"[{severity_label}] ").bold = True
                p.add_run(f"{amb.scope_text}\n")
                p.add_run(f"Competing trades: {', '.join(amb.competing_trades)}\n")
                p.add_run(f"Recommendation: {amb.recommendation}")

        # Gotchas
        if gotchas:
            doc.add_heading("4. Gotcha Risks", level=1)
            for g in gotchas:
                p = doc.add_paragraph()
                p.add_run(f"[{g.severity.upper()}] {g.risk_type}: ").bold = True
                p.add_run(f"{g.description}\n")
                p.add_run(f"Affected trades: {', '.join(g.affected_trades)}\n")
                p.add_run(f"Recommendation: {g.recommendation}")

        # Completeness
        doc.add_heading("5. Completeness Report", level=1)
        p = doc.add_paragraph()
        p.add_run(f"Drawing coverage: {completeness.drawing_coverage_pct}%\n")
        p.add_run(f"CSI coverage: {completeness.csi_coverage_pct}%\n")
        if completeness.missing_drawings:
            p.add_run(f"Missing drawings: {', '.join(completeness.missing_drawings)}\n")
        p.add_run(f"Attempts: {completeness.attempt}\n")

        # Footer
        doc.add_paragraph("")
        footer = doc.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.add_run("Generated by iFieldSmart ScopeAI Pipeline v1.0").italic = True

        doc.save(str(filepath))
        logger.info("Word document generated: %s", filepath)
        return str(filepath)

    def generate_csv_sync(
        self,
        items: list[ClassifiedItem],
        project_id: int,
        project_name: str,
        trade: str,
    ) -> str:
        """Generate CSV synchronously."""
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        slug = project_name.replace(" ", "") if project_name else f"Project{project_id}"
        filename = f"scope_items_{trade.lower()}_{slug}_{project_id}_{uuid4().hex[:8]}.csv"
        filepath = self._docs_dir / filename

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Trade", "CSI Code", "CSI Division", "Scope Item",
                "Drawing", "Drawing Title", "Page", "Source Snippet",
                "Confidence", "Classification Reason",
            ])
            for item in items:
                writer.writerow([
                    item.trade, item.csi_code, item.csi_division, item.text,
                    item.drawing_name, item.drawing_title or "", item.page,
                    item.source_snippet, f"{item.confidence:.2f}",
                    item.classification_reason,
                ])

        logger.info("CSV generated: %s", filepath)
        return str(filepath)

    def generate_json_sync(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        """Generate JSON synchronously."""
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        slug = project_name.replace(" ", "") if project_name else f"Project{project_id}"
        filename = f"scope_full_{trade.lower()}_{slug}_{project_id}_{uuid4().hex[:8]}.json"
        filepath = self._docs_dir / filename

        data = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": {"id": project_id, "name": project_name},
            "trade": trade,
            "pipeline": {
                "attempts": stats.attempts,
                "total_ms": stats.total_ms,
                "tokens_used": stats.tokens_used,
                "estimated_cost_usd": stats.estimated_cost_usd,
            },
            "completeness": completeness.model_dump(),
            "quality": {
                "accuracy_score": quality.accuracy_score,
                "corrections_applied": len(quality.corrections),
                "items_removed": len(quality.removed_items),
                "summary": quality.summary,
            },
            "items": [item.model_dump() for item in items],
            "ambiguities": [a.model_dump() for a in ambiguities],
            "gotchas": [g.model_dump() for g in gotchas],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("JSON generated: %s", filepath)
        return str(filepath)

    def generate_pdf_sync(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        """Generate PDF using reportlab."""
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        slug = project_name.replace(" ", "") if project_name else f"Project{project_id}"
        filename = f"scope_report_{trade.lower()}_{slug}_{project_id}_{uuid4().hex[:8]}.pdf"
        filepath = self._docs_dir / filename

        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor

        doc_pdf = SimpleDocTemplate(str(filepath), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            "ScopeTitle", parent=styles["Title"],
            textColor=HexColor("#1E3A5F"),
        )

        story.append(Paragraph("SCOPE GAP REPORT", title_style))
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            f"Project: {project_name} (ID: {project_id})<br/>"
            f"Trade: {trade}<br/>"
            f"Items: {len(items)} | Ambiguities: {len(ambiguities)} | Gotchas: {len(gotchas)}<br/>"
            f"Completeness: {completeness.overall_pct}%",
            styles["Normal"],
        ))
        story.append(Spacer(1, 24))

        story.append(Paragraph("Scope Inclusions", styles["Heading2"]))
        for item in items[:100]:  # Cap for PDF size
            story.append(Paragraph(
                f"<b>{item.text}</b><br/>"
                f"Drawing: {item.drawing_name} | CSI: {item.csi_code} | "
                f"Confidence: {item.confidence:.0%}<br/>"
                f"Source: \"{item.source_snippet}\"",
                styles["Normal"],
            ))
            story.append(Spacer(1, 6))

        doc_pdf.build(story)
        logger.info("PDF generated: %s", filepath)
        return str(filepath)
```

- [ ] **Step 4: Run tests (expect pass)**

Run: `python -m pytest tests/scope_pipeline/test_document_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/services/document_agent.py tests/scope_pipeline/test_document_agent.py
git commit -m "feat(scope-gap): document agent — Word/PDF/CSV/JSON generation"
```

---

## Task 12: (Covered in Task 11 — PDF, CSV, JSON already implemented)

Task 11 implements all 4 formats. No separate task needed.

---

## Task 13: Session Manager

**Files:**
- Create: `scope_pipeline/services/session_manager.py`
- Create: `tests/scope_pipeline/test_session_manager.py`

- [ ] **Step 1: Write test**

```python
"""tests/scope_pipeline/test_session_manager.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_create_new_session():
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mgr = ScopeGapSessionManager(cache_service=mock_cache, s3_ops=None)
    session = await mgr.get_or_create(project_id=7298, trade="Electrical")
    
    assert session.project_id == 7298
    assert session.trade == "Electrical"
    assert session.id.startswith("sg_session_")
    assert session.runs == []


@pytest.mark.asyncio
async def test_reuse_existing_session_from_cache():
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    from scope_pipeline.models import ScopeGapSession
    
    existing = ScopeGapSession(project_id=7298, trade="Electrical")
    
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=existing.model_dump_json())
    mock_cache.set = AsyncMock()
    
    mgr = ScopeGapSessionManager(cache_service=mock_cache, s3_ops=None)
    session = await mgr.get_or_create(project_id=7298, trade="Electrical")
    
    assert session.project_id == 7298
    assert session.id == existing.id


@pytest.mark.asyncio
async def test_resolve_ambiguity():
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    from scope_pipeline.models import ScopeGapSession
    
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mgr = ScopeGapSessionManager(cache_service=mock_cache, s3_ops=None)
    session = await mgr.get_or_create(project_id=7298, trade="Electrical")
    
    session.ambiguity_resolutions["amb_123"] = "Roofing"
    await mgr.update(session)
    
    assert session.ambiguity_resolutions["amb_123"] == "Roofing"
    mock_cache.set.assert_called()


@pytest.mark.asyncio
async def test_add_message():
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    from scope_pipeline.models import ScopeGapSession, SessionMessage
    
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mgr = ScopeGapSessionManager(cache_service=mock_cache, s3_ops=None)
    session = await mgr.get_or_create(project_id=7298, trade="Electrical")
    
    session.messages.append(SessionMessage(role="user", content="Why fire stopping?"))
    session.messages.append(SessionMessage(role="assistant", content="Because..."))
    await mgr.update(session)
    
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
```

- [ ] **Step 2: Run tests (expect fail)**
- [ ] **Step 3: Implement session_manager.py**

```python
"""
scope_pipeline/services/session_manager.py — 3-layer session persistence.

Layer 1: In-memory TTLCache (100 sessions, 1hr)
Layer 2: Redis via CacheService (7 days TTL)
Layer 3: S3 (permanent) — optional, graceful fallback
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from cachetools import TTLCache

from scope_pipeline.models import ScopeGapSession

logger = logging.getLogger(__name__)

_SESSION_REDIS_TTL = 604800  # 7 days
_SESSION_REDIS_PREFIX = "sg_session:"


class ScopeGapSessionManager:
    """3-layer session persistence: L1 memory → L2 Redis → L3 S3."""

    def __init__(self, cache_service, s3_ops=None):
        self._l1: TTLCache = TTLCache(maxsize=100, ttl=3600)
        self._cache = cache_service
        self._s3 = s3_ops

    async def get_or_create(
        self,
        project_id: int,
        trade: str,
        set_ids: Optional[list[int]] = None,
        user_id: Optional[str] = None,
    ) -> ScopeGapSession:
        key = self._key(project_id, trade, set_ids)

        # L1
        if key in self._l1:
            return self._l1[key]

        # L2 (Redis)
        try:
            cached = await self._cache.get(f"{_SESSION_REDIS_PREFIX}{key}")
            if cached:
                session = ScopeGapSession.model_validate_json(cached)
                self._l1[key] = session
                return session
        except Exception as e:
            logger.warning("Redis session load failed: %s", e)

        # L3 (S3) — optional
        if self._s3:
            try:
                s3_key = self._s3_path(user_id, key)
                data = await asyncio.to_thread(self._s3.download_bytes, s3_key)
                if data:
                    session = ScopeGapSession.model_validate_json(data)
                    self._l1[key] = session
                    await self._cache.set(
                        f"{_SESSION_REDIS_PREFIX}{key}", data, ttl=_SESSION_REDIS_TTL,
                    )
                    return session
            except Exception:
                pass

        # Create new
        session = ScopeGapSession(
            project_id=project_id,
            trade=trade,
            set_ids=set_ids,
            user_id=user_id,
        )
        await self._persist(session)
        return session

    async def update(self, session: ScopeGapSession) -> None:
        session.updated_at = datetime.now(timezone.utc)
        await self._persist(session)

    async def delete(self, session: ScopeGapSession) -> None:
        key = self._key(session.project_id, session.trade, session.set_ids)
        self._l1.pop(key, None)
        try:
            await self._cache.delete(f"{_SESSION_REDIS_PREFIX}{key}")
        except Exception:
            pass

    async def _persist(self, session: ScopeGapSession) -> None:
        key = self._key(session.project_id, session.trade, session.set_ids)
        data = session.model_dump_json()
        self._l1[key] = session

        persist_tasks = [
            self._cache.set(f"{_SESSION_REDIS_PREFIX}{key}", data, ttl=_SESSION_REDIS_TTL),
        ]
        if self._s3:
            s3_key = self._s3_path(session.user_id, key)
            persist_tasks.append(
                asyncio.to_thread(self._s3.upload_bytes, data.encode(), s3_key)
            )
        try:
            await asyncio.gather(*persist_tasks)
        except Exception as e:
            logger.warning("Session persist partial failure: %s", e)

    @staticmethod
    def _key(project_id: int, trade: str, set_ids: Optional[list[int]]) -> str:
        base = f"{project_id}_{trade.lower().replace(' ', '_')}"
        if set_ids:
            base += f"_sets_{'_'.join(map(str, sorted(set_ids)))}"
        return base

    @staticmethod
    def _s3_path(user_id: Optional[str], key: str) -> str:
        user = user_id or "anonymous"
        return f"construction-intelligence-agent/scope_gap_sessions/{user}/{key}.json"
```

- [ ] **Step 4: Run tests (expect pass)**
- [ ] **Step 5: Commit**: `git commit -m "feat(scope-gap): session manager — 3-layer persistence"`

---

## Task 14: Chat Handler

> Follow-up Q&A about scope reports. Uses session.latest_result as context, maintains message history.

- [ ] **Step 1-5: TDD pattern. Commit**: `git commit -m "feat(scope-gap): chat handler — follow-up Q&A"`

---

## Task 15: Job Manager

> In-memory job tracking with asyncio.Task, semaphore(3), progress queues, cancellation.

- [ ] **Step 1-5: TDD pattern. Commit**: `git commit -m "feat(scope-gap): job manager — background pipeline execution"`

---

## Task 16: Orchestrator

**Files:**
- Create: `scope_pipeline/orchestrator.py`
- Create: `tests/scope_pipeline/test_orchestrator.py`

This is the master pipeline controller. It wires all agents together with the backpropagation loop.

- [ ] **Step 1: Write test (mock all agents, verify pipeline flow)**

```python
"""tests/scope_pipeline/test_orchestrator.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_pipeline_completes_in_one_pass():
    from scope_pipeline.orchestrator import ScopeGapPipeline
    from scope_pipeline.models import (
        ScopeItem, ClassifiedItem, AmbiguityItem, GotchaItem,
        CompletenessReport, QualityReport, ScopeGapRequest,
    )
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    
    # Mock all agents
    mock_extraction = AsyncMock()
    mock_extraction.run = AsyncMock(return_value=MagicMock(
        data=[ScopeItem(text="item1", drawing_name="E-103", page=1, source_snippet="test")]
    ))
    
    mock_classification = AsyncMock()
    mock_classification.run = AsyncMock(return_value=MagicMock(
        data=[ClassifiedItem(
            text="item1", drawing_name="E-103", page=1, source_snippet="test",
            trade="Electrical", csi_code="26 24 16", csi_division="26 - Electrical",
            classification_confidence=0.9, classification_reason="test",
        )]
    ))
    
    mock_ambiguity = AsyncMock()
    mock_ambiguity.run = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_gotcha = AsyncMock()
    mock_gotcha.run = AsyncMock(return_value=MagicMock(data=[]))
    
    mock_completeness = AsyncMock()
    mock_completeness.run = AsyncMock(return_value=MagicMock(
        data=CompletenessReport(
            drawing_coverage_pct=100.0, csi_coverage_pct=100.0,
            hallucination_count=0, overall_pct=100.0,
            missing_drawings=[], missing_csi_codes=[],
            hallucinated_items=[], is_complete=True, attempt=1,
        )
    ))
    
    mock_quality = AsyncMock()
    mock_quality.run = AsyncMock(return_value=MagicMock(
        data=QualityReport(
            accuracy_score=0.97, corrections=[], validated_items=[
                ClassifiedItem(
                    text="item1", drawing_name="E-103", page=1, source_snippet="test",
                    trade="Electrical", csi_code="26 24 16", csi_division="26 - Electrical",
                    classification_confidence=0.9, classification_reason="test",
                )
            ],
            removed_items=[], summary="97%",
        )
    ))
    
    mock_document = AsyncMock()
    mock_document.generate_all = AsyncMock(return_value=MagicMock(
        word_path="/tmp/test.docx", pdf_path=None, csv_path=None, json_path=None,
    ))
    
    mock_data_agent = AsyncMock()
    mock_data_agent.fetch_records = AsyncMock(return_value={
        "records": [{"drawing_name": "E-103", "text": "test data"}],
        "drawing_names": {"E-103"},
        "csi_codes": {"26 24 16"},
    })
    
    mock_session_mgr = AsyncMock()
    mock_session_mgr.get_or_create = AsyncMock(return_value=MagicMock(
        runs=[], ambiguity_resolutions={}, ignored_items=[],
        gotcha_acknowledgments=[], latest_result=None, messages=[],
    ))
    mock_session_mgr.update = AsyncMock()
    
    pipeline = ScopeGapPipeline(
        extraction_agent=mock_extraction,
        classification_agent=mock_classification,
        ambiguity_agent=mock_ambiguity,
        gotcha_agent=mock_gotcha,
        completeness_agent=mock_completeness,
        quality_agent=mock_quality,
        document_agent=mock_document,
        data_fetcher=mock_data_agent,
        session_manager=mock_session_mgr,
    )
    
    emitter = ProgressEmitter()
    request = ScopeGapRequest(project_id=7298, trade="Electrical")
    result = await pipeline.run(request, emitter)
    
    assert result.project_id == 7298
    assert result.completeness.is_complete is True
    assert len(result.items) == 1
    assert result.pipeline_stats.attempts == 1
    
    # Verify parallel fan-out happened
    mock_classification.run.assert_called_once()
    mock_ambiguity.run.assert_called_once()
    mock_gotcha.run.assert_called_once()
```

- [ ] **Step 2: Run test (expect fail)**
- [ ] **Step 3: Implement orchestrator.py**

```python
"""
scope_pipeline/orchestrator.py — Master pipeline controller.

Orchestrates the 7-agent pipeline with backpropagation loop:
  Data Fetch → Extraction → (Classification | Ambiguity | Gotcha) →
  Completeness → [backprop if < threshold] → Quality → Documents
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from scope_pipeline.config import PipelineConfig
from scope_pipeline.models import (
    AmbiguityItem, ClassifiedItem, CompletenessReport, DocumentSet,
    GotchaItem, MergedResults, PipelineStats, QualityReport,
    ScopeGapRequest, ScopeGapResult, ScopeItem, PipelineRun,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)


class ScopeGapPipeline:
    """Orchestrates the multi-agent scope gap extraction pipeline."""

    def __init__(
        self,
        extraction_agent,
        classification_agent,
        ambiguity_agent,
        gotcha_agent,
        completeness_agent,
        quality_agent,
        document_agent,
        data_fetcher,
        session_manager,
        config: Optional[PipelineConfig] = None,
    ):
        self._extraction = extraction_agent
        self._classification = classification_agent
        self._ambiguity = ambiguity_agent
        self._gotcha = gotcha_agent
        self._completeness = completeness_agent
        self._quality = quality_agent
        self._document = document_agent
        self._data_fetcher = data_fetcher
        self._session_mgr = session_manager
        self._config = config

    async def run(
        self,
        request: ScopeGapRequest,
        emitter: ProgressEmitter,
        project_name: str = "",
    ) -> ScopeGapResult:
        """Execute the full pipeline with backpropagation."""
        start = time.monotonic()
        max_attempts = self._config.max_attempts if self._config else 3
        threshold = self._config.completeness_threshold if self._config else 95.0
        total_tokens = 0

        # Load/create session
        session = await self._session_mgr.get_or_create(
            request.project_id, request.trade, request.set_ids,
        )

        emitter.emit("pipeline_start", {
            "project_id": request.project_id,
            "trade": request.trade,
        })

        # Phase 1: Data fetch
        fetch_result = await self._data_fetcher.fetch_records(
            request.project_id, request.trade, request.set_ids,
        )
        records = fetch_result["records"]
        source_drawings = fetch_result["drawing_names"]
        source_csi = fetch_result["csi_codes"]

        all_items: list[ScopeItem] = []
        all_classified: list[ClassifiedItem] = []
        all_ambiguities: list[AmbiguityItem] = []
        all_gotchas: list[GotchaItem] = []
        completeness_report: Optional[CompletenessReport] = None

        for attempt in range(1, max_attempts + 1):
            emitter.emit("attempt_start", {"attempt": attempt})

            # Determine input for this attempt
            if attempt == 1:
                extraction_input = {
                    "drawing_records": records,
                    "trade": request.trade,
                    "drawing_list": sorted(source_drawings),
                }
            else:
                # Targeted: only missing drawings
                missing = completeness_report.missing_drawings if completeness_report else []
                targeted_records = [
                    r for r in records if r.get("drawing_name") in set(missing)
                ]
                extraction_input = {
                    "drawing_records": targeted_records,
                    "trade": request.trade,
                    "drawing_list": sorted(source_drawings),
                }

            # Phase 2: Extraction
            extraction_result = await self._extraction.run(extraction_input, emitter)
            new_items: list[ScopeItem] = extraction_result.data
            total_tokens += extraction_result.tokens_used

            # Merge with previous attempts (dedup by drawing_name + text)
            existing_keys = {(i.drawing_name, i.text) for i in all_items}
            for item in new_items:
                if (item.drawing_name, item.text) not in existing_keys:
                    all_items.append(item)
                    existing_keys.add((item.drawing_name, item.text))

            # Phase 3: Parallel fan-out
            classification_result, ambiguity_result, gotcha_result = await asyncio.gather(
                self._classification.run(new_items, emitter),
                self._ambiguity.run(new_items, emitter),
                self._gotcha.run(new_items, emitter),
            )
            total_tokens += (
                classification_result.tokens_used
                + ambiguity_result.tokens_used
                + gotcha_result.tokens_used
            )

            # Merge classified items
            new_classified: list[ClassifiedItem] = classification_result.data
            existing_classified_keys = {(i.drawing_name, i.text) for i in all_classified}
            for item in new_classified:
                if (item.drawing_name, item.text) not in existing_classified_keys:
                    all_classified.append(item)
                    existing_classified_keys.add((item.drawing_name, item.text))

            # Merge ambiguities and gotchas (append, no dedup needed)
            if attempt == 1:
                all_ambiguities = ambiguity_result.data
                all_gotchas = gotcha_result.data
            # On retries, keep original ambiguities/gotchas

            # Phase 4: Completeness check
            merged = MergedResults(
                items=all_items,
                classified_items=all_classified,
                ambiguities=all_ambiguities,
                gotchas=all_gotchas,
            )
            completeness_result = await self._completeness.run(
                merged, emitter,
                source_drawings=source_drawings,
                source_csi=source_csi,
                attempt=attempt,
                threshold=threshold,
            )
            completeness_report = completeness_result.data

            if completeness_report.is_complete:
                logger.info("Pipeline complete at attempt %d (%.1f%%)", attempt, completeness_report.overall_pct)
                break

            if attempt < max_attempts:
                emitter.emit("backpropagation", {
                    "attempt": attempt + 1,
                    "reason": f"{len(completeness_report.missing_drawings)} drawings missing",
                    "missing_drawings": completeness_report.missing_drawings,
                })

        # Remove hallucinated items
        if completeness_report and completeness_report.hallucinated_items:
            hallucinated_set = set(completeness_report.hallucinated_items)
            all_items = [i for i in all_items if i.id not in hallucinated_set]
            all_classified = [i for i in all_classified if i.id not in hallucinated_set]

        # Phase 5: Quality review
        final_merged = MergedResults(
            items=all_items,
            classified_items=all_classified,
            ambiguities=all_ambiguities,
            gotchas=all_gotchas,
        )
        quality_result = await self._quality.run(final_merged, emitter)
        quality_report: QualityReport = quality_result.data
        total_tokens += quality_result.tokens_used

        # Phase 6: Document generation
        validated_items = quality_report.validated_items or all_classified
        elapsed_ms = int((time.monotonic() - start) * 1000)
        stats = PipelineStats(
            total_ms=elapsed_ms,
            attempts=completeness_report.attempt if completeness_report else 1,
            tokens_used=total_tokens,
            estimated_cost_usd=total_tokens * 0.000002,  # rough estimate
            per_agent_timing={},
            records_processed=len(records),
            items_extracted=len(validated_items),
        )

        documents = await self._document.generate_all(
            items=validated_items,
            ambiguities=all_ambiguities,
            gotchas=all_gotchas,
            completeness=completeness_report,
            quality=quality_report,
            project_id=request.project_id,
            project_name=project_name,
            trade=request.trade,
            stats=stats,
        )

        result = ScopeGapResult(
            project_id=request.project_id,
            project_name=project_name,
            trade=request.trade,
            items=validated_items,
            ambiguities=all_ambiguities,
            gotchas=all_gotchas,
            completeness=completeness_report,
            quality=quality_report,
            documents=documents,
            pipeline_stats=stats,
        )

        # Update session
        run = PipelineRun(
            status="completed" if completeness_report.is_complete else "partial",
            attempts=completeness_report.attempt,
            completeness_pct=completeness_report.overall_pct,
            items_count=len(validated_items),
            ambiguities_count=len(all_ambiguities),
            gotchas_count=len(all_gotchas),
            token_usage=total_tokens,
            cost_usd=stats.estimated_cost_usd,
            documents=documents,
        )
        session.runs.insert(0, run)
        if len(session.runs) > 10:
            session.runs = session.runs[:10]
        session.latest_result = result
        await self._session_mgr.update(session)

        terminal_event = "pipeline_complete" if completeness_report.is_complete else "pipeline_partial"
        emitter.emit(terminal_event, {
            "total_ms": elapsed_ms,
            "attempts": stats.attempts,
            "items": len(validated_items),
            "ambiguities": len(all_ambiguities),
            "gotchas": len(all_gotchas),
            "completeness_pct": completeness_report.overall_pct,
        })

        return result
```

- [ ] **Step 4: Run test (expect pass)**
- [ ] **Step 5: Commit**: `git commit -m "feat(scope-gap): orchestrator — pipeline controller with backpropagation"`

---

## Task 17: Router (API Endpoints)

> All endpoints from the spec: /generate, /stream, /submit, /jobs, /sessions, /chat. Hybrid routing logic. SSE streaming via sse-starlette.

- [ ] **Step 1-5: TDD pattern. Commit**: `git commit -m "feat(scope-gap): router — all API endpoints with hybrid routing"`

---

## Task 18: Integration (main.py + config.py)

**Files:**
- Modify: `main.py` (add ~15 lines)

- [ ] **Step 1: Add router import and pipeline init to main.py**

After line 50 (`from routers.projects import router as projects_router`), add:

```python
from scope_pipeline.routers.scope_gap import router as scope_gap_router
```

In the `lifespan` function, after `generation_agent` creation (line 110), add:

```python
    # ── Scope Gap Pipeline (Phase 11) ─────────────────────────
    from scope_pipeline.config import get_pipeline_config
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.agents.classification_agent import ClassificationAgent
    from scope_pipeline.agents.ambiguity_agent import AmbiguityAgent
    from scope_pipeline.agents.gotcha_agent import GotchaAgent
    from scope_pipeline.agents.completeness_agent import CompletenessAgent
    from scope_pipeline.agents.quality_agent import QualityAgent
    from scope_pipeline.services.document_agent import DocumentAgent as ScopeDocAgent
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    from scope_pipeline.services.job_manager import JobManager
    from scope_pipeline.orchestrator import ScopeGapPipeline

    pcfg = get_pipeline_config()
    scope_pipeline = ScopeGapPipeline(
        extraction_agent=ExtractionAgent(api_key=pcfg.openai_api_key, model=pcfg.model, max_tokens=pcfg.extraction_max_tokens),
        classification_agent=ClassificationAgent(api_key=pcfg.openai_api_key, model=pcfg.model, max_tokens=pcfg.classification_max_tokens),
        ambiguity_agent=AmbiguityAgent(api_key=pcfg.openai_api_key, model=pcfg.model),
        gotcha_agent=GotchaAgent(api_key=pcfg.openai_api_key, model=pcfg.model),
        completeness_agent=CompletenessAgent(),
        quality_agent=QualityAgent(api_key=pcfg.openai_api_key, model=pcfg.model, max_tokens=pcfg.quality_max_tokens),
        document_agent=ScopeDocAgent(docs_dir=pcfg.docs_dir),
        data_fetcher=data_agent,
        session_manager=ScopeGapSessionManager(cache_service=cache),
        config=pcfg,
    )
    app.state.scope_pipeline = scope_pipeline
    app.state.scope_job_manager = JobManager(pipeline=scope_pipeline, max_concurrent=pcfg.max_concurrent_jobs)
    app.state.scope_session_manager = ScopeGapSessionManager(cache_service=cache)
    logger.info("Scope Gap Pipeline initialized (model=%s, threshold=%.0f%%)", pcfg.model, pcfg.completeness_threshold)
```

After line 182 (`app.include_router(projects_router)`), add:

```python
app.include_router(scope_gap_router)
```

- [ ] **Step 2: Verify server starts**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -c "from main import app; print('OK')" `
Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add main.py config.py
git commit -m "feat(scope-gap): integration — pipeline wired into FastAPI app"
```

---

## Task 19: Integration Test (Full Pipeline)

> Test the complete pipeline with a real test project via the API endpoint. Verify all 4 document formats are generated.

- [ ] **Step 1-5: Write and run integration test. Commit**: `git commit -m "test(scope-gap): integration test — full pipeline verification"`

---

## Task 20: Security Hardening

> Prompt injection defense (delimiters in system prompts), Pydantic validation on all inputs, rate limiting on pipeline endpoints, input sanitization.

- [ ] **Step 1-5: Review and harden. Commit**: `git commit -m "fix(scope-gap): security hardening — input validation, prompt defense"`

---

## Task 21: CLAUDE.md Update

- [ ] **Step 1: Add Phase 11 section to CLAUDE.md**

Add a new section documenting the scope gap pipeline: endpoints, env vars, agent registry, file inventory, modification guide.

- [ ] **Step 2: Commit**: `git commit -m "docs(scope-gap): CLAUDE.md — Phase 11 scope gap pipeline documentation"`

---

## Task 22: Final Verification

- [ ] **Step 1: Run all existing tests (zero regression)**

Run: `python -m pytest tests/ -v --ignore=tests/scope_pipeline/`
Expected: ALL PASS

- [ ] **Step 2: Run all scope pipeline tests**

Run: `python -m pytest tests/scope_pipeline/ -v`
Expected: ALL PASS

- [ ] **Step 3: Run coverage check**

Run: `python -m pytest tests/scope_pipeline/ --cov=scope_pipeline --cov-report=term-missing`
Expected: >= 80% coverage

- [ ] **Step 4: Verify server starts and health check passes**

Run: `python main.py &` then `curl http://localhost:8003/health`
Expected: `{"status":"ok",...}`

- [ ] **Step 5: Verify scope gap endpoint responds**

Run: `curl http://localhost:8003/api/scope-gap/sessions`
Expected: `[]` (empty list, no errors)

- [ ] **Step 6: Final commit**

```bash
git commit -m "chore(scope-gap): final verification — all tests pass, 80%+ coverage"
```
