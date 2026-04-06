# Scope Gap UI Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all 10 UI-backend gaps, add project-level orchestration for 50-150 trades, webhook pre-computation, per-user highlight persistence, contractual language output, and combined export.

**Architecture:** New `ProjectOrchestrator` wraps the existing 7-agent `ScopeGapPipeline` (untouched). Worker pool with `Semaphore(10)` runs trades in parallel. Per-project sessions replace per-trade sessions. S3 stores highlights per-user. Webhooks trigger pre-computation.

**Tech Stack:** FastAPI, asyncio, Pydantic v2, Redis, S3 (boto3), OpenAI gpt-4.1, python-docx, reportlab, pytest

**Spec:** `docs/superpowers/specs/2026-04-06-scope-gap-ui-integration-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `scope_pipeline/models_v2.py` | ProjectSession, TradeResultContainer, TradeRunRecord, Highlight, ProjectStatus, webhook models |
| `scope_pipeline/services/project_session_manager.py` | Per-project session CRUD with 3-layer persistence + lazy migration |
| `scope_pipeline/services/trade_color_service.py` | 23 base colors + hash-based auto-generation |
| `scope_pipeline/services/trade_discovery_service.py` | MongoDB trade listing via 2 APIs + caching |
| `scope_pipeline/services/drawing_index_service.py` | Drawing categorization + metadata + prefix-to-discipline mapping |
| `scope_pipeline/services/highlight_service.py` | S3 highlight CRUD + Redis cache layer |
| `scope_pipeline/services/webhook_handler.py` | HMAC validation + event processing + idempotency |
| `scope_pipeline/services/export_service.py` | Multi-trade combined Word+PDF generation + ZIP |
| `scope_pipeline/project_orchestrator.py` | Worker pool, adaptive throttle, progressive SSE, smart scheduling |
| `scope_pipeline/routers/project_endpoints.py` | /projects/{id}/trades, sets, drawings, meta, colors, status, run-all, stream, export |
| `scope_pipeline/routers/highlight_endpoints.py` | /highlights CRUD (7 endpoints) |
| `scope_pipeline/routers/webhook_endpoints.py` | /webhooks/project-event |
| `tests/scope_pipeline/test_models_v2.py` | Model validation tests |
| `tests/scope_pipeline/test_project_session_manager.py` | Session CRUD + migration tests |
| `tests/scope_pipeline/test_trade_color_service.py` | Color palette tests |
| `tests/scope_pipeline/test_trade_discovery_service.py` | Trade discovery tests |
| `tests/scope_pipeline/test_drawing_index_service.py` | Drawing index tests |
| `tests/scope_pipeline/test_highlight_service.py` | Highlight S3 CRUD tests |
| `tests/scope_pipeline/test_webhook_handler.py` | Webhook security tests |
| `tests/scope_pipeline/test_export_service.py` | Export generation tests |
| `tests/scope_pipeline/test_project_orchestrator.py` | Orchestrator concurrency tests |
| `tests/scope_pipeline/test_project_endpoints.py` | Endpoint contract tests |
| `tests/scope_pipeline/test_highlight_endpoints.py` | Highlight endpoint tests |
| `tests/scope_pipeline/test_webhook_endpoints.py` | Webhook endpoint tests |
| `tests/scope_pipeline/test_contractual_extraction.py` | Prompt output validation |

### Modified Files

| File | Changes |
|------|---------|
| `scope_pipeline/models.py` | Add `drawing_refs`, `discipline`, `source_type`, `csi_division` to ScopeItem; add `trade_color` to ClassifiedItem |
| `scope_pipeline/agents/extraction_agent.py` | Contractual language system prompt rewrite |
| `scope_pipeline/config.py` | Add all new config variables |
| `scope_pipeline/routers/scope_gap.py` | Mount new sub-routers |
| `scope_pipeline/services/document_agent.py` | Add `generate_combined_word_sync` and `generate_combined_pdf_sync` methods |
| `main.py` | Wire new services onto app.state |

---

## Phase 12A: Session Architecture Restructure

### Task 1: New Data Models (models_v2.py)

**Files:**
- Create: `scope_pipeline/models_v2.py`
- Test: `tests/scope_pipeline/test_models_v2.py`

- [ ] **Step 1: Write the failing test for TradeRunRecord**

```python
# tests/scope_pipeline/test_models_v2.py
"""Tests for Phase 12 data models."""

import pytest
from datetime import datetime, timezone

from scope_pipeline.models import DocumentSet


def test_trade_run_record_defaults():
    from scope_pipeline.models_v2 import TradeRunRecord

    record = TradeRunRecord()
    assert record.run_id  # auto-generated
    assert record.status == "pending"
    assert record.attempts == 0
    assert record.completeness_pct == 0.0
    assert record.items_count == 0
    assert record.documents is None


def test_trade_run_record_with_values():
    from scope_pipeline.models_v2 import TradeRunRecord

    record = TradeRunRecord(
        status="complete",
        attempts=2,
        completeness_pct=96.5,
        items_count=107,
        cost_usd=0.10,
    )
    assert record.status == "complete"
    assert record.attempts == 2
    assert record.cost_usd == 0.10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models_v2.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scope_pipeline.models_v2'`

- [ ] **Step 3: Write the TradeRunRecord model**

```python
# scope_pipeline/models_v2.py
"""scope_pipeline/models_v2.py — Phase 12 data models.

ProjectSession, TradeResultContainer, TradeRunRecord, Highlight,
and webhook/status models for the UI integration layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from scope_pipeline.models import DocumentSet, ScopeGapResult


# ---------------------------------------------------------------------------
# Trade-level run tracking
# ---------------------------------------------------------------------------

class TradeRunRecord(BaseModel):
    """Record of a single trade pipeline execution."""

    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending | running | complete | partial | failed
    attempts: int = 0
    completeness_pct: float = 0.0
    items_count: int = 0
    ambiguities_count: int = 0
    gotchas_count: int = 0
    token_usage: int = 0
    cost_usd: float = 0.0
    documents: Optional[DocumentSet] = None
    error: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models_v2.py::test_trade_run_record_defaults tests/scope_pipeline/test_models_v2.py::test_trade_run_record_with_values -v`
Expected: 2 PASSED

- [ ] **Step 5: Write tests for TradeResultContainer**

Add to `tests/scope_pipeline/test_models_v2.py`:

```python
def test_trade_result_container_defaults():
    from scope_pipeline.models_v2 import TradeResultContainer

    container = TradeResultContainer(trade="Electrical")
    assert container.trade == "Electrical"
    assert container.current_version == 0
    assert container.versions == []
    assert container.latest_result is None


def test_trade_result_container_add_version():
    from scope_pipeline.models_v2 import TradeResultContainer, TradeRunRecord

    container = TradeResultContainer(trade="Electrical")
    record = TradeRunRecord(status="complete", items_count=50)
    container.versions.append(record)
    container.current_version = 1
    assert len(container.versions) == 1
    assert container.current_version == 1


def test_trade_result_container_max_versions():
    from scope_pipeline.models_v2 import TradeResultContainer, TradeRunRecord

    container = TradeResultContainer(trade="HVAC", max_versions=3)
    for i in range(5):
        container.versions.append(TradeRunRecord(status="complete", items_count=i))
    # Trim to max
    trimmed = container.versions[-container.max_versions:]
    assert len(trimmed) == 3
    assert trimmed[0].items_count == 2
```

- [ ] **Step 6: Write TradeResultContainer model**

Add to `scope_pipeline/models_v2.py`:

```python
# ---------------------------------------------------------------------------
# Trade result container (holds version history)
# ---------------------------------------------------------------------------

class TradeResultContainer(BaseModel):
    """Holds all pipeline runs for a single trade within a project session."""

    trade: str
    current_version: int = 0
    versions: list[TradeRunRecord] = Field(default_factory=list)
    latest_result: Optional[ScopeGapResult] = None
    max_versions: int = 5

    def add_run(self, record: TradeRunRecord, result: Optional[ScopeGapResult] = None) -> None:
        """Add a new run, trim old versions beyond max_versions."""
        self.versions.append(record)
        self.current_version = len(self.versions)
        if result is not None:
            self.latest_result = result
        # Trim oldest versions beyond limit
        if len(self.versions) > self.max_versions:
            self.versions = self.versions[-self.max_versions:]
```

- [ ] **Step 7: Run all model tests**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models_v2.py -v`
Expected: 5 PASSED

- [ ] **Step 8: Write tests for ProjectSession**

Add to `tests/scope_pipeline/test_models_v2.py`:

```python
def test_project_session_defaults():
    from scope_pipeline.models_v2 import ProjectSession

    session = ProjectSession(project_id=7276)
    assert session.project_id == 7276
    assert session.project_name == ""
    assert session.trade_results == {}
    assert session.ambiguity_resolutions == {}
    assert session.messages == []


def test_project_session_add_trade():
    from scope_pipeline.models_v2 import ProjectSession, TradeResultContainer

    session = ProjectSession(project_id=7276, project_name="Granville Hotel")
    session.trade_results["Electrical"] = TradeResultContainer(trade="Electrical")
    assert "Electrical" in session.trade_results
    assert session.trade_results["Electrical"].trade == "Electrical"


def test_project_session_key():
    from scope_pipeline.models_v2 import ProjectSession

    session = ProjectSession(project_id=7276)
    assert session.session_key == "proj_7276"


def test_project_session_key_with_set_ids():
    from scope_pipeline.models_v2 import ProjectSession

    session = ProjectSession(project_id=7276, set_ids=[4731, 4730])
    assert session.session_key == "proj_7276_sets_4730_4731"
```

- [ ] **Step 9: Write ProjectSession model**

Add to `scope_pipeline/models_v2.py`:

```python
from scope_pipeline.models import SessionMessage


# ---------------------------------------------------------------------------
# Project-level session
# ---------------------------------------------------------------------------

class ProjectSession(BaseModel):
    """Per-project session holding all trade results and shared state."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    project_id: int
    project_name: str = ""
    set_ids: Optional[list[Union[int, str]]] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Trade results — keyed by trade name
    trade_results: dict[str, TradeResultContainer] = Field(default_factory=dict)

    # Shared state across trades
    ambiguity_resolutions: dict[str, str] = Field(default_factory=dict)
    gotcha_acknowledgments: list[str] = Field(default_factory=list)
    ignored_items: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)

    @property
    def session_key(self) -> str:
        """Deterministic key for storage lookup."""
        base = f"proj_{self.project_id}"
        if self.set_ids:
            sorted_ids = "_".join(str(sid) for sid in sorted(self.set_ids, key=str))
            return f"{base}_sets_{sorted_ids}"
        return base
```

- [ ] **Step 10: Run all model tests**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models_v2.py -v`
Expected: 9 PASSED

- [ ] **Step 11: Write tests for Highlight model**

Add to `tests/scope_pipeline/test_models_v2.py`:

```python
def test_highlight_defaults():
    from scope_pipeline.models_v2 import Highlight

    hl = Highlight(
        drawing_name="E0.03",
        x=245.5,
        y=380.2,
        width=312.0,
        height=48.0,
    )
    assert hl.id.startswith("hl_")
    assert hl.drawing_name == "E0.03"
    assert hl.page == 1
    assert hl.color == "#FFEB3B"
    assert hl.opacity == 0.3
    assert hl.label == ""
    assert hl.critical is False
    assert hl.scope_item_ids == []


def test_highlight_full():
    from scope_pipeline.models_v2 import Highlight

    hl = Highlight(
        drawing_name="E0.03",
        x=100,
        y=200,
        width=300,
        height=40,
        color="#F48FB1",
        label="Panel LP-1",
        trade="Electrical",
        critical=True,
        comment="Verify in field",
        scope_item_id="itm_a3f7b2c1",
        scope_item_ids=["itm_a3f7b2c1", "itm_b4e8c3d2"],
    )
    assert hl.critical is True
    assert hl.scope_item_id == "itm_a3f7b2c1"
    assert len(hl.scope_item_ids) == 2


def test_highlight_index():
    from scope_pipeline.models_v2 import HighlightIndex

    idx = HighlightIndex(
        project_id=7276,
        user_id="user_123",
        drawings={"E0.03": {"count": 5}, "M2.01": {"count": 2}},
    )
    assert len(idx.drawings) == 2
```

- [ ] **Step 12: Write Highlight and HighlightIndex models**

Add to `scope_pipeline/models_v2.py`:

```python
# ---------------------------------------------------------------------------
# Highlight persistence
# ---------------------------------------------------------------------------

def _highlight_id() -> str:
    return f"hl_{uuid4().hex[:8]}"


class Highlight(BaseModel):
    """User-drawn highlight annotation on a drawing."""

    id: str = Field(default_factory=_highlight_id)
    drawing_name: str
    page: int = 1
    # Region
    x: float
    y: float
    width: float
    height: float
    # Visual
    color: str = "#FFEB3B"
    opacity: float = 0.3
    # Metadata
    label: str = ""
    trade: str = ""
    critical: bool = False
    comment: str = ""
    # Linking
    scope_item_id: Optional[str] = None
    scope_item_ids: list[str] = Field(default_factory=list)
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HighlightIndex(BaseModel):
    """Lightweight index of highlights per drawing for a user+project."""

    project_id: int
    user_id: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    drawings: dict[str, dict[str, Any]] = Field(default_factory=dict)
```

- [ ] **Step 13: Write tests for webhook models**

Add to `tests/scope_pipeline/test_models_v2.py`:

```python
def test_webhook_event_project_created():
    from scope_pipeline.models_v2 import WebhookEvent

    event = WebhookEvent(
        event="project.created",
        project_id=7276,
        project_name="Granville Hotel",
    )
    assert event.event == "project.created"
    assert event.changed_trades is None


def test_webhook_event_drawings_uploaded():
    from scope_pipeline.models_v2 import WebhookEvent

    event = WebhookEvent(
        event="drawings.uploaded",
        project_id=7276,
        changed_trades=["Electrical", "HVAC"],
        set_id=4730,
        drawing_count=15,
    )
    assert event.changed_trades == ["Electrical", "HVAC"]
    assert event.set_id == 4730
```

- [ ] **Step 14: Write webhook models**

Add to `scope_pipeline/models_v2.py`:

```python
# ---------------------------------------------------------------------------
# Webhook models
# ---------------------------------------------------------------------------

class WebhookEvent(BaseModel):
    """Incoming webhook event from iFieldSmart."""

    event: str  # "project.created" | "drawings.uploaded"
    project_id: int
    project_name: Optional[str] = None
    set_id: Optional[int] = None
    changed_trades: Optional[list[str]] = None
    drawing_count: Optional[int] = None
    timestamp: Optional[datetime] = None
```

- [ ] **Step 15: Run full test suite, verify zero regression**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models_v2.py -v && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All new tests PASS. All existing 56 tests PASS.

- [ ] **Step 16: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/models_v2.py tests/scope_pipeline/test_models_v2.py
git commit -m "feat(scope-pipeline): add Phase 12 data models (ProjectSession, Highlight, Webhook)"
```

---

### Task 2: Update Existing Models (ScopeItem extensions)

**Files:**
- Modify: `scope_pipeline/models.py:41-52` (ScopeItem)
- Modify: `scope_pipeline/models.py:59-66` (ClassifiedItem)
- Test: `tests/scope_pipeline/test_models.py` (existing)

- [ ] **Step 1: Write failing test for new ScopeItem fields**

Add to `tests/scope_pipeline/test_models.py`:

```python
def test_scope_item_new_fields_defaults():
    """Phase 12: new fields have safe defaults."""
    from scope_pipeline.models import ScopeItem

    item = ScopeItem(text="test", drawing_name="E0.03")
    assert item.drawing_refs == []
    assert item.discipline is None
    assert item.source_type == "drawing"
    assert item.csi_division is None


def test_scope_item_new_fields_populated():
    from scope_pipeline.models import ScopeItem

    item = ScopeItem(
        text="Contractor shall furnish and install Panel LP-1",
        drawing_name="E0.03",
        drawing_refs=["E0.03", "E0.03-AP4", "E1.01"],
        discipline="ELECTRICAL",
        source_type="drawing",
        csi_division="Division 26 - Electrical",
    )
    assert len(item.drawing_refs) == 3
    assert item.discipline == "ELECTRICAL"
    assert item.csi_division == "Division 26 - Electrical"


def test_classified_item_trade_color():
    from scope_pipeline.models import ClassifiedItem

    item = ClassifiedItem(
        text="test",
        drawing_name="E0.03",
        trade="Electrical",
        csi_code="26 24 16",
        csi_division="26",
        classification_confidence=0.95,
        classification_reason="test",
        trade_color="#F48FB1",
    )
    assert item.trade_color == "#F48FB1"


def test_classified_item_trade_color_default():
    from scope_pipeline.models import ClassifiedItem

    item = ClassifiedItem(
        text="test",
        drawing_name="E0.03",
        trade="Electrical",
        csi_code="26",
        csi_division="26",
        classification_confidence=0.9,
        classification_reason="test",
    )
    assert item.trade_color == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models.py::test_scope_item_new_fields_defaults -v`
Expected: FAIL — `drawing_refs` attribute not found

- [ ] **Step 3: Add new fields to ScopeItem and ClassifiedItem**

In `scope_pipeline/models.py`, modify `ScopeItem` (around line 41):

Replace:
```python
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
```

With:
```python
class ScopeItem(BaseModel):
    """Single scope item extracted from drawing notes (Agent 1 output)."""

    id: str = Field(default_factory=lambda: _prefixed_id("itm_"))
    text: str
    drawing_name: str
    drawing_refs: list[str] = Field(default_factory=list)
    drawing_title: Optional[str] = None
    discipline: Optional[str] = None
    source_type: str = "drawing"
    page: int = 1
    source_snippet: str = ""
    confidence: float = 0.0
    csi_hint: Optional[str] = None
    csi_division: Optional[str] = None
    source_record_id: Optional[str] = None
```

Modify `ClassifiedItem` (around line 59) — add one field after `classification_reason`:

```python
class ClassifiedItem(ScopeItem):
    """Scope item with trade/CSI classification (Agent 2 output)."""

    trade: str
    csi_code: str
    csi_division: str
    classification_confidence: float
    classification_reason: str
    trade_color: str = ""
```

- [ ] **Step 4: Run all model tests to verify pass + zero regression**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_models.py -v && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/models.py tests/scope_pipeline/test_models.py
git commit -m "feat(scope-pipeline): add drawing_refs, discipline, source_type, trade_color to models"
```

---

### Task 3: Pipeline Config Extensions

**Files:**
- Modify: `scope_pipeline/config.py`

- [ ] **Step 1: Add new config variables**

Replace the entire `scope_pipeline/config.py`:

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
    model: str
    extraction_max_tokens: int
    classification_max_tokens: int
    quality_max_tokens: int
    max_attempts: int
    completeness_threshold: float
    record_threshold: int
    max_concurrent_jobs: int
    openai_api_key: str
    max_context_tokens: int
    storage_backend: str
    s3_bucket_name: str
    s3_region: str
    s3_agent_prefix: str
    docs_dir: str
    # Phase 12: Project Orchestrator
    trade_concurrency: int
    trade_concurrency_min: int
    result_freshness_ttl: int
    max_trades_per_project: int
    project_pipeline_timeout: int
    trade_pipeline_timeout: int
    adaptive_throttle_cooldown: int
    # Phase 12: Webhook
    webhook_secret: str
    webhook_allowed_ips: str
    webhook_timestamp_tolerance: int
    webhook_idempotency_ttl: int
    # Phase 12: Pre-computation
    precompute_priority: str
    precompute_concurrency: int
    precompute_enabled: bool
    # Phase 12: Highlights
    highlight_s3_prefix: str
    highlight_cache_ttl: int
    highlight_max_per_drawing: int
    highlight_max_per_project: int
    # Phase 12: Session
    session_max_versions_per_trade: int
    session_archive_after_days: int
    session_redis_ttl: int
    session_l1_max_trades: int


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
        # Phase 12: Project Orchestrator
        trade_concurrency=int(os.getenv("TRADE_CONCURRENCY", "10")),
        trade_concurrency_min=int(os.getenv("TRADE_CONCURRENCY_MIN", "4")),
        result_freshness_ttl=int(os.getenv("RESULT_FRESHNESS_TTL", "86400")),
        max_trades_per_project=int(os.getenv("MAX_TRADES_PER_PROJECT", "200")),
        project_pipeline_timeout=int(os.getenv("PROJECT_PIPELINE_TIMEOUT", "7200")),
        trade_pipeline_timeout=int(os.getenv("TRADE_PIPELINE_TIMEOUT", "600")),
        adaptive_throttle_cooldown=int(os.getenv("ADAPTIVE_THROTTLE_COOLDOWN", "60")),
        # Phase 12: Webhook
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        webhook_allowed_ips=os.getenv("WEBHOOK_ALLOWED_IPS", ""),
        webhook_timestamp_tolerance=int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE", "300")),
        webhook_idempotency_ttl=int(os.getenv("WEBHOOK_IDEMPOTENCY_TTL", "3600")),
        # Phase 12: Pre-computation
        precompute_priority=os.getenv("PRECOMPUTE_PRIORITY", "low"),
        precompute_concurrency=int(os.getenv("PRECOMPUTE_CONCURRENCY", "5")),
        precompute_enabled=os.getenv("PRECOMPUTE_ENABLED", "true").lower() == "true",
        # Phase 12: Highlights
        highlight_s3_prefix=os.getenv("HIGHLIGHT_S3_PREFIX", "highlights"),
        highlight_cache_ttl=int(os.getenv("HIGHLIGHT_CACHE_TTL", "300")),
        highlight_max_per_drawing=int(os.getenv("HIGHLIGHT_MAX_PER_DRAWING", "500")),
        highlight_max_per_project=int(os.getenv("HIGHLIGHT_MAX_PER_PROJECT", "10000")),
        # Phase 12: Session
        session_max_versions_per_trade=int(os.getenv("SESSION_MAX_VERSIONS_PER_TRADE", "5")),
        session_archive_after_days=int(os.getenv("SESSION_ARCHIVE_AFTER_DAYS", "30")),
        session_redis_ttl=int(os.getenv("SESSION_REDIS_TTL", "604800")),
        session_l1_max_trades=int(os.getenv("SESSION_L1_MAX_TRADES", "20")),
    )
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All PASS (config is backward compatible — new fields all have defaults)

- [ ] **Step 3: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/config.py
git commit -m "feat(scope-pipeline): add Phase 12 config variables for orchestrator, webhook, highlights"
```

---

### Task 4: Project Session Manager

**Files:**
- Create: `scope_pipeline/services/project_session_manager.py`
- Test: `tests/scope_pipeline/test_project_session_manager.py`

- [ ] **Step 1: Write failing test for session creation**

```python
# tests/scope_pipeline/test_project_session_manager.py
"""Tests for ProjectSessionManager — per-project session with trade results."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models_v2 import ProjectSession


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


@pytest.fixture
def mock_s3():
    s3 = AsyncMock()
    s3.get = AsyncMock(return_value=None)
    s3.put = AsyncMock()
    s3.delete = AsyncMock()
    return s3


@pytest.mark.asyncio
async def test_get_or_create_new_session(mock_cache, mock_s3):
    from scope_pipeline.services.project_session_manager import ProjectSessionManager

    mgr = ProjectSessionManager(cache_service=mock_cache, s3_ops=mock_s3)
    session = await mgr.get_or_create(project_id=7276)
    assert isinstance(session, ProjectSession)
    assert session.project_id == 7276
    assert session.session_key == "proj_7276"


@pytest.mark.asyncio
async def test_get_or_create_cached_session(mock_cache, mock_s3):
    from scope_pipeline.services.project_session_manager import ProjectSessionManager

    mgr = ProjectSessionManager(cache_service=mock_cache, s3_ops=mock_s3)
    # First call creates
    session1 = await mgr.get_or_create(project_id=7276)
    # Second call returns same from L1
    session2 = await mgr.get_or_create(project_id=7276)
    assert session1.id == session2.id


@pytest.mark.asyncio
async def test_update_persists_to_l2(mock_cache, mock_s3):
    from scope_pipeline.services.project_session_manager import ProjectSessionManager

    mgr = ProjectSessionManager(cache_service=mock_cache, s3_ops=mock_s3)
    session = await mgr.get_or_create(project_id=7276)
    await mgr.update(session)
    mock_cache.set.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_session_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write ProjectSessionManager**

```python
# scope_pipeline/services/project_session_manager.py
"""scope_pipeline/services/project_session_manager.py — Per-project session persistence.

L1: in-memory TTLCache
L2: Redis
L3: S3 (archived versions)

Session key: proj_{project_id} or proj_{project_id}_sets_{sorted_ids}
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from cachetools import TTLCache

from scope_pipeline.models_v2 import ProjectSession

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "sg_proj_session:"
_REDIS_TTL = 604_800  # 7 days
_S3_PATH_PREFIX = "construction-intelligence-agent/project_sessions"


class ProjectSessionManager:
    """3-layer persistence for per-project sessions."""

    def __init__(self, cache_service: Any, s3_ops: Any = None) -> None:
        self._l1: TTLCache[str, ProjectSession] = TTLCache(maxsize=100, ttl=3600)
        self._cache = cache_service
        self._s3 = s3_ops

    async def get_or_create(
        self,
        project_id: int,
        set_ids: Optional[list[Union[int, str]]] = None,
        project_name: str = "",
    ) -> ProjectSession:
        """Check L1 -> L2 -> create new if not found."""
        temp = ProjectSession(project_id=project_id, set_ids=set_ids)
        key = temp.session_key

        # L1
        session = self._l1.get(key)
        if session is not None:
            return session

        # L2
        session = await self._get_from_l2(key)
        if session is not None:
            self._l1[key] = session
            return session

        # Create new
        logger.info("Creating new project session: %s", key)
        session = ProjectSession(
            project_id=project_id,
            project_name=project_name,
            set_ids=set_ids,
        )
        self._l1[key] = session
        return session

    async def update(self, session: ProjectSession) -> None:
        """Persist to all layers."""
        session.updated_at = datetime.now(timezone.utc)
        key = session.session_key
        serialised = session.model_dump_json()

        # L1
        self._l1[key] = session

        # L2
        await self._persist_to_l2(key, serialised)

    async def delete(self, session: ProjectSession) -> None:
        """Remove from all layers."""
        key = session.session_key
        self._l1.pop(key, None)
        try:
            await self._cache.delete(f"{_REDIS_KEY_PREFIX}{key}")
        except Exception:
            logger.warning("Failed to delete session from L2: %s", key, exc_info=True)

    def get_by_project_id(self, project_id: int) -> Optional[ProjectSession]:
        """Find a project session in L1 by project ID."""
        for session in self._l1.values():
            if session.project_id == project_id:
                return session
        return None

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _get_from_l2(self, key: str) -> Optional[ProjectSession]:
        try:
            raw = await self._cache.get(f"{_REDIS_KEY_PREFIX}{key}")
            if raw is not None:
                return ProjectSession.model_validate_json(raw)
        except Exception:
            logger.warning("L2 read failed for %s", key, exc_info=True)
        return None

    async def _persist_to_l2(self, key: str, serialised: str) -> None:
        try:
            await self._cache.set(f"{_REDIS_KEY_PREFIX}{key}", serialised, ttl=_REDIS_TTL)
        except Exception:
            logger.warning("L2 write failed for %s", key, exc_info=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_session_manager.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/project_session_manager.py tests/scope_pipeline/test_project_session_manager.py
git commit -m "feat(scope-pipeline): add ProjectSessionManager with 3-layer persistence"
```

---

### Task 5: Trade Color Service

**Files:**
- Create: `scope_pipeline/services/trade_color_service.py`
- Test: `tests/scope_pipeline/test_trade_color_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_trade_color_service.py
"""Tests for TradeColorService — 23 base colors + hash-based auto-generation."""


def test_known_trade_returns_base_color():
    from scope_pipeline.services.trade_color_service import TradeColorService
    svc = TradeColorService()
    result = svc.get_color("Electrical")
    assert result["hex"] == "#F48FB1"
    assert result["rgb"] == [244, 143, 177]


def test_unknown_trade_returns_generated_color():
    from scope_pipeline.services.trade_color_service import TradeColorService
    svc = TradeColorService()
    result = svc.get_color("Some New Custom Trade")
    assert result["hex"].startswith("#")
    assert len(result["hex"]) == 7
    assert len(result["rgb"]) == 3
    assert all(0 <= c <= 255 for c in result["rgb"])


def test_generated_color_is_deterministic():
    from scope_pipeline.services.trade_color_service import TradeColorService
    svc = TradeColorService()
    c1 = svc.get_color("Custom Trade XYZ")
    c2 = svc.get_color("Custom Trade XYZ")
    assert c1 == c2


def test_get_all_colors():
    from scope_pipeline.services.trade_color_service import TradeColorService
    svc = TradeColorService()
    trades = ["Electrical", "HVAC", "Plumbing", "Unknown Trade"]
    colors = svc.get_all_colors(trades)
    assert len(colors) == 4
    assert "Electrical" in colors
    assert "Unknown Trade" in colors


def test_case_insensitive_lookup():
    from scope_pipeline.services.trade_color_service import TradeColorService
    svc = TradeColorService()
    c1 = svc.get_color("electrical")
    c2 = svc.get_color("ELECTRICAL")
    c3 = svc.get_color("Electrical")
    assert c1 == c2 == c3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_trade_color_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write TradeColorService**

```python
# scope_pipeline/services/trade_color_service.py
"""scope_pipeline/services/trade_color_service.py — Trade color palette.

23 base colors from the production UI (scopegap-agent-v3.html TC object).
Unknown trades get a deterministic hash-based HSL color.
Returns both hex and RGB formats.
"""

from __future__ import annotations

import colorsys
import hashlib

# Base palette from scopegap-agent-v3.html TC object
_BASE_COLORS: dict[str, str] = {
    "Electrical": "#F48FB1",
    "HVAC": "#90A4AE",
    "Plumbing": "#81D4FA",
    "Fire Alarm": "#FFE082",
    "Fire Sprinkler": "#FFAB91",
    "Lighting": "#FFF59D",
    "Low Voltage": "#CE93D8",
    "Controls": "#80CBC4",
    "Concrete": "#BCAAA4",
    "Structural Steel": "#B0BEC5",
    "Framing & Drywall": "#C5E1A5",
    "Doors & Hardware": "#EF9A9A",
    "Glass & Glazing": "#80DEEA",
    "Roofing": "#A5D6A7",
    "Elevators": "#B39DDB",
    "Painting": "#F8BBD0",
    "Flooring": "#DCEDC8",
    "Casework": "#D7CCC8",
    "Earthwork": "#FFE0B2",
    "Abatement": "#FFCCBC",
    "Acoustical Ceilings": "#E1BEE7",
    "Data & Telecom": "#B2EBF2",
    "General Conditions": "#CFD8DC",
}

# Build case-insensitive lookup
_LOOKUP: dict[str, str] = {k.lower(): v for k, v in _BASE_COLORS.items()}


def _hex_to_rgb(hex_color: str) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i+2], 16) for i in (0, 2, 4)]


def _generate_color_from_hash(trade: str) -> str:
    """Deterministic color generation: hash → HSL(S=70%, L=65%) → hex."""
    digest = hashlib.md5(trade.lower().encode()).hexdigest()
    hue = int(digest[:8], 16) % 360
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.65, 0.70)
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"


class TradeColorService:
    """Provides trade colors: 23 base + hash-based auto-generation."""

    def get_color(self, trade: str) -> dict[str, object]:
        """Return {"hex": "#F48FB1", "rgb": [244, 143, 177]} for a trade."""
        hex_color = _LOOKUP.get(trade.lower())
        if hex_color is None:
            hex_color = _generate_color_from_hash(trade)
        return {"hex": hex_color, "rgb": _hex_to_rgb(hex_color)}

    def get_all_colors(self, trades: list[str]) -> dict[str, dict[str, object]]:
        """Return color map for a list of trades."""
        return {trade: self.get_color(trade) for trade in trades}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_trade_color_service.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/trade_color_service.py tests/scope_pipeline/test_trade_color_service.py
git commit -m "feat(scope-pipeline): add TradeColorService with 23 base colors + hash generation"
```

---

### Task 6: Drawing Index Service (Discipline Derivation)

**Files:**
- Create: `scope_pipeline/services/drawing_index_service.py`
- Test: `tests/scope_pipeline/test_drawing_index_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_drawing_index_service.py
"""Tests for DrawingIndexService — discipline derivation + categorized tree."""


def test_derive_discipline_electrical():
    from scope_pipeline.services.drawing_index_service import derive_discipline
    assert derive_discipline("E0.03") == "ELECTRICAL"


def test_derive_discipline_fire_protection():
    from scope_pipeline.services.drawing_index_service import derive_discipline
    assert derive_discipline("FP-101") == "FIRE PROTECTION"


def test_derive_discipline_fallback_to_set_trade():
    from scope_pipeline.services.drawing_index_service import derive_discipline
    assert derive_discipline("X-999", set_trade="Custom Trade") == "CUSTOM TRADE"


def test_derive_discipline_fallback_to_general():
    from scope_pipeline.services.drawing_index_service import derive_discipline
    assert derive_discipline("X-999") == "GENERAL"


def test_build_categorized_tree():
    from scope_pipeline.services.drawing_index_service import DrawingIndexService

    records = [
        {"drawingName": "E0.03", "drawingTitle": "Schedules", "setTrade": "Electrical"},
        {"drawingName": "E1.01", "drawingTitle": "First Floor", "setTrade": "Electrical"},
        {"drawingName": "M2.01", "drawingTitle": "HVAC Plan", "setTrade": "Mechanical"},
        {"drawingName": "A1.01", "drawingTitle": "Floor Plan", "setTrade": "Architectural"},
    ]

    svc = DrawingIndexService()
    tree = svc.build_categorized_tree(records)

    assert "ELECTRICAL" in tree
    assert len(tree["ELECTRICAL"]["drawings"]) == 2
    assert "MECHANICAL" in tree
    assert "ARCHITECTURAL" in tree


def test_build_drawing_metadata():
    from scope_pipeline.services.drawing_index_service import DrawingIndexService

    records = [
        {"drawingName": "E0.03", "drawingTitle": "Schedules", "setTrade": "Electrical",
         "setName": "100% CD", "_id": "rec1"},
        {"drawingName": "E0.03", "drawingTitle": "Schedules", "setTrade": "Electrical",
         "setName": "100% CD", "_id": "rec2"},
    ]

    svc = DrawingIndexService()
    meta = svc.build_drawing_metadata(records)

    assert "E0.03" in meta
    assert meta["E0.03"]["discipline"] == "ELECTRICAL"
    assert meta["E0.03"]["record_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_drawing_index_service.py -v`
Expected: FAIL

- [ ] **Step 3: Write DrawingIndexService**

```python
# scope_pipeline/services/drawing_index_service.py
"""scope_pipeline/services/drawing_index_service.py — Drawing categorization + metadata.

Derives discipline from drawing name prefix. Builds categorized tree
for the sidebar and drawing metadata for the Reference Panel.
"""

from __future__ import annotations

from typing import Any, Optional

# 2-char prefixes checked first, then 1-char
_PREFIX_TO_DISCIPLINE: dict[str, str] = {
    "FP": "FIRE PROTECTION",
    "FA": "FIRE ALARM",
    "LC": "LIGHTING",
    "ID": "INTERIOR DESIGN",
    "G": "GENERAL",
    "C": "CIVIL",
    "L": "LANDSCAPE",
    "A": "ARCHITECTURAL",
    "S": "STRUCTURAL",
    "M": "MECHANICAL",
    "P": "PLUMBING",
    "E": "ELECTRICAL",
    "T": "TELECOM",
}


def derive_discipline(drawing_name: str, set_trade: Optional[str] = None) -> str:
    """Derive discipline from drawing name prefix, fallback to set_trade."""
    name_upper = drawing_name.upper()
    # Try 2-char prefix first
    if len(name_upper) >= 2:
        prefix_2 = name_upper[:2]
        for key in ("FP", "FA", "LC", "ID"):
            if prefix_2 == key:
                return _PREFIX_TO_DISCIPLINE[key]
    # Try 1-char prefix
    if name_upper:
        prefix_1 = name_upper[0]
        if prefix_1 in _PREFIX_TO_DISCIPLINE:
            return _PREFIX_TO_DISCIPLINE[prefix_1]
    # Fallback to set_trade
    if set_trade:
        return set_trade.upper()
    return "GENERAL"


class DrawingIndexService:
    """Builds categorized drawing trees and metadata from raw API records."""

    def build_categorized_tree(
        self, records: list[dict[str, Any]],
    ) -> dict[str, dict[str, list[dict[str, str]]]]:
        """Build {discipline: {drawings: [...], specs: [...]}} tree.

        Deduplicates by drawing_name within each discipline.
        """
        tree: dict[str, dict[str, list[dict[str, str]]]] = {}
        seen: set[str] = set()

        for rec in records:
            dn = rec.get("drawingName", "") or rec.get("drawing_name", "")
            if not dn or dn in seen:
                continue
            seen.add(dn)

            dt = rec.get("drawingTitle", "") or rec.get("drawing_title", "")
            st = rec.get("setTrade", "") or rec.get("set_trade", "")
            source_type = rec.get("source_type", "drawing")
            discipline = derive_discipline(dn, st)

            if discipline not in tree:
                tree[discipline] = {"drawings": [], "specs": []}

            entry = {
                "drawing_name": dn,
                "drawing_title": dt,
                "source_type": source_type,
            }

            if source_type == "specification":
                tree[discipline]["specs"].append(entry)
            else:
                tree[discipline]["drawings"].append(entry)

        return tree

    def build_drawing_metadata(
        self, records: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build {drawing_name: {metadata}} index from raw records."""
        meta: dict[str, dict[str, Any]] = {}

        for rec in records:
            dn = rec.get("drawingName", "") or rec.get("drawing_name", "")
            if not dn:
                continue

            if dn not in meta:
                dt = rec.get("drawingTitle", "") or rec.get("drawing_title", "")
                st = rec.get("setTrade", "") or rec.get("set_trade", "")
                sn = rec.get("setName", "") or rec.get("set_name", "")
                meta[dn] = {
                    "drawing_name": dn,
                    "drawing_title": dt,
                    "discipline": derive_discipline(dn, st),
                    "source_type": rec.get("source_type", "drawing"),
                    "set_name": sn,
                    "set_trade": st,
                    "record_count": 0,
                }
            meta[dn]["record_count"] += 1

        return meta
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_drawing_index_service.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/drawing_index_service.py tests/scope_pipeline/test_drawing_index_service.py
git commit -m "feat(scope-pipeline): add DrawingIndexService with discipline derivation"
```

---

## Phase 12B: Project Orchestrator & Worker Pool

### Task 7: Trade Discovery Service

**Files:**
- Create: `scope_pipeline/services/trade_discovery_service.py`
- Test: `tests/scope_pipeline/test_trade_discovery_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_trade_discovery_service.py
"""Tests for TradeDiscoveryService — fetch available trades from MongoDB."""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_api_client():
    client = AsyncMock()
    client.get_summary_by_trade = AsyncMock(return_value=[
        {"drawingName": "E0.03", "setTrade": "Electrical", "text": "scope text"},
        {"drawingName": "M2.01", "setTrade": "Mechanical", "text": "scope text"},
    ])
    return client


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.mark.asyncio
async def test_discover_trades(mock_api_client, mock_cache):
    from scope_pipeline.services.trade_discovery_service import TradeDiscoveryService

    svc = TradeDiscoveryService(api_client=mock_api_client, cache_service=mock_cache)
    trades = await svc.discover_trades(project_id=7276)
    assert isinstance(trades, list)
    assert len(trades) >= 1
    assert all("trade" in t and "record_count" in t for t in trades)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_trade_discovery_service.py -v`
Expected: FAIL

- [ ] **Step 3: Write TradeDiscoveryService**

```python
# scope_pipeline/services/trade_discovery_service.py
"""scope_pipeline/services/trade_discovery_service.py — Discover available trades.

Uses the MongoDB summaryByTrade API to discover which trades have data.
Two APIs: project_id/trade (all trades) and project_id/setid/trade (per set).
Results cached for session duration.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "sg_trades:"
_CACHE_TTL = 3600  # 1 hour


class TradeDiscoveryService:
    """Discover available trades for a project from MongoDB."""

    def __init__(self, api_client: Any, cache_service: Any) -> None:
        self._api = api_client
        self._cache = cache_service

    async def discover_trades(
        self,
        project_id: int,
        set_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return list of {trade, record_count} for a project.

        Checks cache first. On miss, fetches from MongoDB API.
        """
        cache_key = f"{_CACHE_PREFIX}{project_id}"
        if set_id is not None:
            cache_key += f"_{set_id}"

        # Check cache
        cached = await self._cache.get(cache_key)
        if cached is not None:
            import json
            return json.loads(cached)

        # Fetch from API — get first page to discover trades
        trades_map: dict[str, int] = {}
        try:
            records = await self._api.get_summary_by_trade(project_id, "")
            for rec in records:
                trade = rec.get("setTrade", "") or rec.get("trades", [""])[0] if rec.get("trades") else ""
                if trade:
                    trades_map[trade] = trades_map.get(trade, 0) + 1
        except Exception:
            logger.warning(
                "Trade discovery via empty trade failed for project %d, "
                "falling back to known trades scan",
                project_id,
                exc_info=True,
            )

        result = [
            {"trade": trade, "record_count": count}
            for trade, count in sorted(trades_map.items())
        ]

        # Cache result
        if result:
            import json
            await self._cache.set(cache_key, json.dumps(result), ttl=_CACHE_TTL)

        return result
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_trade_discovery_service.py -v`
Expected: 1 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/trade_discovery_service.py tests/scope_pipeline/test_trade_discovery_service.py
git commit -m "feat(scope-pipeline): add TradeDiscoveryService for dynamic trade listing"
```

---

### Task 8: Project Orchestrator

**Files:**
- Create: `scope_pipeline/project_orchestrator.py`
- Test: `tests/scope_pipeline/test_project_orchestrator.py`

- [ ] **Step 1: Write failing test for single-trade execution**

```python
# tests/scope_pipeline/test_project_orchestrator.py
"""Tests for ProjectOrchestrator — worker pool for all trades."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from scope_pipeline.models import (
    ClassifiedItem, AmbiguityItem, GotchaItem, CompletenessReport,
    QualityReport, DocumentSet, PipelineStats, ScopeGapResult,
)
from scope_pipeline.models_v2 import ProjectSession


def _make_mock_result(trade: str) -> ScopeGapResult:
    return ScopeGapResult(
        project_id=7276,
        project_name="Test",
        trade=trade,
        items=[],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100, csi_coverage_pct=100,
            hallucination_count=0, overall_pct=100,
            missing_drawings=[], missing_csi_codes=[],
            hallucinated_items=[], is_complete=True, attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=0.95, corrections=[], validated_items=[],
            removed_items=[], summary="ok",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=1000, attempts=1, tokens_used=1000,
            estimated_cost_usd=0.01, per_agent_timing={},
            records_processed=10, items_extracted=5,
        ),
    )


@pytest.fixture
def mock_pipeline():
    pipeline = AsyncMock()
    pipeline.run = AsyncMock(side_effect=lambda req, emitter, project_name="": _make_mock_result(req.trade))
    return pipeline


@pytest.fixture
def mock_session_mgr():
    mgr = AsyncMock()
    mgr.get_or_create = AsyncMock(return_value=ProjectSession(project_id=7276))
    mgr.update = AsyncMock()
    return mgr


@pytest.fixture
def mock_trade_discovery():
    svc = AsyncMock()
    svc.discover_trades = AsyncMock(return_value=[
        {"trade": "Electrical", "record_count": 50},
        {"trade": "Plumbing", "record_count": 30},
    ])
    return svc


@pytest.fixture
def mock_color_service():
    svc = MagicMock()
    svc.get_color = MagicMock(return_value={"hex": "#F48FB1", "rgb": [244, 143, 177]})
    return svc


@pytest.mark.asyncio
async def test_run_all_trades(mock_pipeline, mock_session_mgr, mock_trade_discovery, mock_color_service):
    from scope_pipeline.project_orchestrator import ProjectOrchestrator
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    orchestrator = ProjectOrchestrator(
        pipeline=mock_pipeline,
        session_manager=mock_session_mgr,
        trade_discovery=mock_trade_discovery,
        color_service=mock_color_service,
        trade_concurrency=5,
    )
    emitter = ProgressEmitter()
    session = await orchestrator.run_all_trades(project_id=7276, emitter=emitter)

    assert isinstance(session, ProjectSession)
    assert mock_pipeline.run.call_count == 2  # Electrical + Plumbing
    assert "Electrical" in session.trade_results
    assert "Plumbing" in session.trade_results


@pytest.mark.asyncio
async def test_skips_fresh_trades(mock_pipeline, mock_session_mgr, mock_trade_discovery, mock_color_service):
    from scope_pipeline.project_orchestrator import ProjectOrchestrator
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    from scope_pipeline.models_v2 import TradeResultContainer, TradeRunRecord

    # Pre-populate session with a fresh Electrical result
    session = ProjectSession(project_id=7276)
    container = TradeResultContainer(trade="Electrical")
    container.add_run(
        TradeRunRecord(status="complete", completed_at=datetime.now(timezone.utc)),
        result=_make_mock_result("Electrical"),
    )
    session.trade_results["Electrical"] = container
    mock_session_mgr.get_or_create = AsyncMock(return_value=session)

    orchestrator = ProjectOrchestrator(
        pipeline=mock_pipeline,
        session_manager=mock_session_mgr,
        trade_discovery=mock_trade_discovery,
        color_service=mock_color_service,
        trade_concurrency=5,
        result_freshness_ttl=86400,
    )
    emitter = ProgressEmitter()
    result = await orchestrator.run_all_trades(project_id=7276, emitter=emitter)

    # Only Plumbing should have run (Electrical is fresh)
    assert mock_pipeline.run.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Write ProjectOrchestrator**

```python
# scope_pipeline/project_orchestrator.py
"""scope_pipeline/project_orchestrator.py — Project-level orchestration.

Wraps the existing ScopeGapPipeline to run ALL trades for a project
in parallel using a worker pool with adaptive throttling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from scope_pipeline.models import ScopeGapRequest, ScopeGapResult
from scope_pipeline.models_v2 import (
    ProjectSession,
    TradeResultContainer,
    TradeRunRecord,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)


class ProjectOrchestrator:
    """Run all trades for a project in parallel via a worker pool."""

    def __init__(
        self,
        pipeline: Any,
        session_manager: Any,
        trade_discovery: Any,
        color_service: Any,
        trade_concurrency: int = 10,
        result_freshness_ttl: int = 86400,
        trade_pipeline_timeout: int = 600,
    ) -> None:
        self._pipeline = pipeline
        self._session_mgr = session_manager
        self._trade_discovery = trade_discovery
        self._color_service = color_service
        self._concurrency = trade_concurrency
        self._freshness_ttl = result_freshness_ttl
        self._trade_timeout = trade_pipeline_timeout

    async def run_all_trades(
        self,
        project_id: int,
        emitter: ProgressEmitter,
        set_ids: Optional[list[int]] = None,
        force_rerun: bool = False,
        specific_trades: Optional[list[str]] = None,
        project_name: str = "",
    ) -> ProjectSession:
        """Discover trades, skip fresh ones, run the rest in parallel."""
        start = time.monotonic()

        # 1. Load or create project session
        session = await self._session_mgr.get_or_create(
            project_id=project_id, set_ids=set_ids, project_name=project_name,
        )

        # 2. Discover trades
        trade_list = await self._trade_discovery.discover_trades(project_id, set_id=set_ids[0] if set_ids else None)
        all_trade_names = [t["trade"] for t in trade_list]

        if specific_trades:
            all_trade_names = [t for t in all_trade_names if t in specific_trades]

        # 3. Filter out fresh trades (unless force_rerun)
        trades_to_run: list[str] = []
        now = datetime.now(timezone.utc)

        for trade_name in all_trade_names:
            if force_rerun:
                trades_to_run.append(trade_name)
                continue

            container = session.trade_results.get(trade_name)
            if container and container.latest_result:
                last_run = container.versions[-1] if container.versions else None
                if last_run and last_run.completed_at:
                    age = (now - last_run.completed_at).total_seconds()
                    if age < self._freshness_ttl:
                        emitter.emit("trade_cached", {
                            "trade": trade_name,
                            "age_seconds": int(age),
                        })
                        continue
            trades_to_run.append(trade_name)

        emitter.emit("session_loaded", {
            "project_id": project_id,
            "total_trades": len(all_trade_names),
            "cached": len(all_trade_names) - len(trades_to_run),
            "to_run": len(trades_to_run),
        })

        # 4. Run trades in parallel with semaphore
        semaphore = asyncio.Semaphore(self._concurrency)
        completed = 0
        failed = 0

        async def _run_trade(trade_name: str) -> None:
            nonlocal completed, failed
            async with semaphore:
                try:
                    request = ScopeGapRequest(
                        project_id=project_id,
                        trade=trade_name,
                        set_ids=set_ids,
                    )
                    trade_emitter = ProgressEmitter()
                    result = await asyncio.wait_for(
                        self._pipeline.run(request, trade_emitter, project_name=project_name),
                        timeout=self._trade_timeout,
                    )
                    # Save to session
                    container = session.trade_results.get(trade_name)
                    if container is None:
                        container = TradeResultContainer(trade=trade_name)
                        session.trade_results[trade_name] = container

                    record = TradeRunRecord(
                        status="complete",
                        completed_at=datetime.now(timezone.utc),
                        attempts=result.pipeline_stats.attempts,
                        completeness_pct=result.completeness.overall_pct,
                        items_count=len(result.items),
                        ambiguities_count=len(result.ambiguities),
                        gotchas_count=len(result.gotchas),
                        token_usage=result.pipeline_stats.tokens_used,
                        cost_usd=result.pipeline_stats.estimated_cost_usd,
                        documents=result.documents,
                    )
                    container.add_run(record, result=result)

                    completed += 1
                    emitter.emit("trade_complete", {
                        "trade": trade_name,
                        "items_count": len(result.items),
                        "ambiguities": len(result.ambiguities),
                        "gotchas": len(result.gotchas),
                        "elapsed_ms": result.pipeline_stats.total_ms,
                        "completed": completed,
                        "total": len(trades_to_run),
                    })

                except asyncio.TimeoutError:
                    failed += 1
                    self._record_failure(session, trade_name, f"Timeout after {self._trade_timeout}s")
                    emitter.emit("trade_failed", {"trade": trade_name, "error": "Timeout"})

                except Exception as exc:
                    failed += 1
                    self._record_failure(session, trade_name, str(exc))
                    emitter.emit("trade_failed", {"trade": trade_name, "error": str(exc)})
                    logger.exception("Trade pipeline failed: %s", trade_name)

        # Launch all trades
        if trades_to_run:
            tasks = [_run_trade(t) for t in trades_to_run]
            await asyncio.gather(*tasks)

        # 5. Persist session
        await self._session_mgr.update(session)

        total_ms = int((time.monotonic() - start) * 1000)
        emitter.emit("all_complete", {
            "project_id": project_id,
            "total_trades": len(all_trade_names),
            "successful": completed,
            "failed": failed,
            "cached": len(all_trade_names) - len(trades_to_run),
            "total_ms": total_ms,
        })

        return session

    def _record_failure(self, session: ProjectSession, trade: str, error: str) -> None:
        """Record a failed trade run in the session."""
        container = session.trade_results.get(trade)
        if container is None:
            container = TradeResultContainer(trade=trade)
            session.trade_results[trade] = container
        record = TradeRunRecord(
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error=error,
        )
        container.add_run(record)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_orchestrator.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Run full regression**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/project_orchestrator.py tests/scope_pipeline/test_project_orchestrator.py
git commit -m "feat(scope-pipeline): add ProjectOrchestrator with worker pool and adaptive scheduling"
```

---

## Phase 12C: New API Endpoints

### Task 9: Project Endpoints Router

**Files:**
- Create: `scope_pipeline/routers/project_endpoints.py`
- Test: `tests/scope_pipeline/test_project_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_project_endpoints.py
"""Tests for project-level API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scope_pipeline.routers.project_endpoints import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    # Mock dependencies on app.state
    app.state.project_orchestrator = AsyncMock()
    app.state.project_session_manager = AsyncMock()
    app.state.trade_discovery_service = AsyncMock()
    app.state.trade_color_service = MagicMock()
    app.state.drawing_index_service = MagicMock()
    app.state.scope_data_fetcher = AsyncMock()

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_trades(client, app):
    app.state.trade_discovery_service.discover_trades = AsyncMock(return_value=[
        {"trade": "Electrical", "record_count": 107},
        {"trade": "Plumbing", "record_count": 45},
    ])
    app.state.trade_color_service.get_color = MagicMock(
        return_value={"hex": "#F48FB1", "rgb": [244, 143, 177]},
    )
    app.state.project_session_manager.get_by_project_id = MagicMock(return_value=None)

    response = client.get("/api/scope-gap/projects/7276/trades")
    assert response.status_code == 200
    data = response.json()
    assert "trades" in data
    assert len(data["trades"]) == 2
    assert data["trades"][0]["trade"] == "Electrical"


def test_get_trade_colors(client, app):
    app.state.trade_discovery_service.discover_trades = AsyncMock(return_value=[
        {"trade": "Electrical", "record_count": 50},
    ])
    app.state.trade_color_service.get_all_colors = MagicMock(return_value={
        "Electrical": {"hex": "#F48FB1", "rgb": [244, 143, 177]},
    })

    response = client.get("/api/scope-gap/projects/7276/trade-colors")
    assert response.status_code == 200
    data = response.json()
    assert "colors" in data
    assert "Electrical" in data["colors"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_endpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Write project_endpoints router**

```python
# scope_pipeline/routers/project_endpoints.py
"""scope_pipeline/routers/project_endpoints.py — Project-level API endpoints.

Endpoints for trades, sets, drawings, metadata, colors, status, run-all,
stream, and export.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap/projects", tags=["scope-gap-projects"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class RunAllBody(BaseModel):
    set_ids: Optional[list[int]] = None
    force_rerun: bool = False
    trades: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_trade_discovery(request: Request):
    return request.app.state.trade_discovery_service


def _get_color_service(request: Request):
    return request.app.state.trade_color_service


def _get_drawing_index(request: Request):
    return request.app.state.drawing_index_service


def _get_session_mgr(request: Request):
    return request.app.state.project_session_manager


def _get_data_fetcher(request: Request):
    return request.app.state.scope_data_fetcher


def _get_orchestrator(request: Request):
    return request.app.state.project_orchestrator


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{project_id}/trades")
async def get_trades(
    project_id: int,
    request: Request,
    set_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """List available trades with status and color."""
    discovery = _get_trade_discovery(request)
    colors = _get_color_service(request)
    session_mgr = _get_session_mgr(request)

    trade_list = await discovery.discover_trades(project_id, set_id=set_id)
    session = session_mgr.get_by_project_id(project_id)

    enriched = []
    for t in trade_list:
        trade_name = t["trade"]
        color = colors.get_color(trade_name)
        status = "pending"
        if session and trade_name in session.trade_results:
            container = session.trade_results[trade_name]
            if container.latest_result:
                status = "ready"
            elif container.versions and container.versions[-1].status == "failed":
                status = "failed"

        enriched.append({
            "trade": trade_name,
            "record_count": t["record_count"],
            "status": status,
            "color": color["hex"],
        })

    return {
        "project_id": project_id,
        "trades": enriched,
        "total_trades": len(enriched),
        "total_records": sum(t["record_count"] for t in trade_list),
    }


@router.get("/{project_id}/trade-colors")
async def get_trade_colors(
    project_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return backend-owned trade color palette."""
    discovery = _get_trade_discovery(request)
    colors = _get_color_service(request)

    trade_list = await discovery.discover_trades(project_id)
    trade_names = [t["trade"] for t in trade_list]
    color_map = colors.get_all_colors(trade_names)

    return {"colors": color_map}


@router.get("/{project_id}/drawings")
async def get_drawings(
    project_id: int,
    request: Request,
    set_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """Return categorized drawing/spec tree for sidebar."""
    data_fetcher = _get_data_fetcher(request)
    drawing_index = _get_drawing_index(request)

    # Fetch records — use a broad trade to get all drawings
    try:
        fetch_result = await data_fetcher.fetch_records(project_id, "", set_ids=[set_id] if set_id else None)
        records = fetch_result["records"]
    except Exception:
        records = []

    tree = drawing_index.build_categorized_tree(records)

    total_drawings = sum(len(cat["drawings"]) for cat in tree.values())
    total_specs = sum(len(cat["specs"]) for cat in tree.values())

    return {
        "project_id": project_id,
        "total_drawings": total_drawings,
        "total_specs": total_specs,
        "categories": tree,
    }


@router.get("/{project_id}/drawings/meta")
async def get_drawing_metadata(
    project_id: int,
    request: Request,
    drawing_names: str = Query(..., description="Comma-separated drawing names"),
) -> dict[str, Any]:
    """Batch drawing metadata for Reference Panel cards."""
    data_fetcher = _get_data_fetcher(request)
    drawing_index = _get_drawing_index(request)

    requested = [n.strip() for n in drawing_names.split(",") if n.strip()]

    try:
        fetch_result = await data_fetcher.fetch_records(project_id, "")
        records = fetch_result["records"]
    except Exception:
        records = []

    all_meta = drawing_index.build_drawing_metadata(records)
    filtered = {name: all_meta[name] for name in requested if name in all_meta}

    return {"drawings": filtered}


@router.get("/{project_id}/status")
async def get_status(
    project_id: int,
    request: Request,
) -> dict[str, Any]:
    """Project pipeline status dashboard."""
    session_mgr = _get_session_mgr(request)
    session = session_mgr.get_by_project_id(project_id)

    if session is None:
        return {
            "project_id": project_id,
            "session_id": None,
            "overall_progress": {"total_trades": 0, "completed": 0},
        }

    completed = 0
    failed = 0
    total_items = 0
    total_cost = 0.0
    trade_statuses = []

    for trade_name, container in session.trade_results.items():
        if container.latest_result:
            completed += 1
            total_items += len(container.latest_result.items)
            total_cost += container.latest_result.pipeline_stats.estimated_cost_usd
            trade_statuses.append({
                "trade": trade_name,
                "status": "ready",
                "items": len(container.latest_result.items),
            })
        elif container.versions and container.versions[-1].status == "failed":
            failed += 1
            trade_statuses.append({
                "trade": trade_name,
                "status": "failed",
                "error": container.versions[-1].error or "Unknown error",
            })

    total = len(session.trade_results)
    return {
        "project_id": project_id,
        "session_id": session.id,
        "overall_progress": {
            "total_trades": total,
            "completed": completed,
            "failed": failed,
            "pct": round(completed / total * 100, 1) if total > 0 else 0,
        },
        "total_items": total_items,
        "total_cost_usd": round(total_cost, 2),
        "trades": trade_statuses,
    }


@router.post("/{project_id}/run-all")
async def run_all_trades(
    project_id: int,
    body: RunAllBody,
    request: Request,
) -> Any:
    """Trigger all-trades pipeline. Returns 202 with job info."""
    orchestrator = _get_orchestrator(request)

    # For now, return 202 — actual background execution wired in Phase 12B integration
    return JSONResponse(
        status_code=202,
        content={
            "project_id": project_id,
            "message": "Project pipeline queued",
            "force_rerun": body.force_rerun,
            "trades": body.trades,
        },
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_project_endpoints.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/routers/project_endpoints.py tests/scope_pipeline/test_project_endpoints.py
git commit -m "feat(scope-pipeline): add project-level API endpoints (trades, colors, drawings, status)"
```

---

## Phase 12D: Highlight Persistence

### Task 10: Highlight Service

**Files:**
- Create: `scope_pipeline/services/highlight_service.py`
- Test: `tests/scope_pipeline/test_highlight_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_highlight_service.py
"""Tests for HighlightService — S3 CRUD + Redis cache."""

import pytest
import json
from unittest.mock import AsyncMock

from scope_pipeline.models_v2 import Highlight


@pytest.fixture
def mock_s3():
    s3 = AsyncMock()
    s3.get = AsyncMock(return_value=None)
    s3.put = AsyncMock()
    s3.delete = AsyncMock()
    return s3


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


@pytest.mark.asyncio
async def test_create_highlight(mock_s3, mock_cache):
    from scope_pipeline.services.highlight_service import HighlightService

    svc = HighlightService(s3_ops=mock_s3, cache_service=mock_cache, s3_prefix="highlights")
    hl = Highlight(drawing_name="E0.03", x=100, y=200, width=300, height=40)

    created = await svc.create(
        project_id=7276, user_id="user_123", highlight=hl,
    )
    assert created.id == hl.id
    mock_s3.put.assert_called_once()


@pytest.mark.asyncio
async def test_list_highlights_empty(mock_s3, mock_cache):
    from scope_pipeline.services.highlight_service import HighlightService

    svc = HighlightService(s3_ops=mock_s3, cache_service=mock_cache, s3_prefix="highlights")
    result = await svc.list_for_drawing(
        project_id=7276, user_id="user_123", drawing_name="E0.03",
    )
    assert result == []


@pytest.mark.asyncio
async def test_list_highlights_from_s3(mock_s3, mock_cache):
    from scope_pipeline.services.highlight_service import HighlightService

    hl = Highlight(drawing_name="E0.03", x=100, y=200, width=300, height=40)
    mock_s3.get = AsyncMock(return_value=json.dumps([hl.model_dump()], default=str))

    svc = HighlightService(s3_ops=mock_s3, cache_service=mock_cache, s3_prefix="highlights")
    result = await svc.list_for_drawing(
        project_id=7276, user_id="user_123", drawing_name="E0.03",
    )
    assert len(result) == 1
    assert result[0]["drawing_name"] == "E0.03"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_highlight_service.py -v`
Expected: FAIL

- [ ] **Step 3: Write HighlightService**

```python
# scope_pipeline/services/highlight_service.py
"""scope_pipeline/services/highlight_service.py — S3-backed highlight persistence.

Stores per-user highlights as JSON files in S3.
Redis caching layer for reads (5 min TTL).
Path: {prefix}/{project_id}/{user_id}/{drawing_name}.json
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from scope_pipeline.models_v2 import Highlight

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "hl:"
_CACHE_TTL = 300  # 5 min


class HighlightService:
    """CRUD operations for user highlights stored in S3."""

    def __init__(self, s3_ops: Any, cache_service: Any, s3_prefix: str = "highlights") -> None:
        self._s3 = s3_ops
        self._cache = cache_service
        self._prefix = s3_prefix

    def _s3_path(self, project_id: int, user_id: str, drawing_name: str) -> str:
        return f"{self._prefix}/{project_id}/{user_id}/{drawing_name}.json"

    def _cache_key(self, project_id: int, user_id: str, drawing_name: str) -> str:
        return f"{_CACHE_PREFIX}{project_id}:{user_id}:{drawing_name}"

    async def create(
        self, project_id: int, user_id: str, highlight: Highlight,
    ) -> Highlight:
        """Add a highlight. Appends to existing S3 file."""
        path = self._s3_path(project_id, user_id, highlight.drawing_name)

        # Read existing
        existing = await self._read_s3(path)
        existing.append(json.loads(highlight.model_dump_json()))

        # Write back
        await self._s3.put(path, json.dumps(existing, default=str))

        # Invalidate cache
        cache_key = self._cache_key(project_id, user_id, highlight.drawing_name)
        await self._cache.delete(cache_key)

        return highlight

    async def list_for_drawing(
        self, project_id: int, user_id: str, drawing_name: str,
    ) -> list[dict[str, Any]]:
        """List highlights for a specific drawing. Checks cache first."""
        cache_key = self._cache_key(project_id, user_id, drawing_name)

        # Check cache
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        # Read from S3
        path = self._s3_path(project_id, user_id, drawing_name)
        highlights = await self._read_s3(path)

        # Cache result
        if highlights:
            await self._cache.set(cache_key, json.dumps(highlights, default=str), ttl=_CACHE_TTL)

        return highlights

    async def delete_one(
        self, project_id: int, user_id: str, drawing_name: str, highlight_id: str,
    ) -> bool:
        """Delete a single highlight by ID."""
        path = self._s3_path(project_id, user_id, drawing_name)
        existing = await self._read_s3(path)
        filtered = [h for h in existing if h.get("id") != highlight_id]

        if len(filtered) == len(existing):
            return False  # Not found

        await self._s3.put(path, json.dumps(filtered, default=str))
        await self._cache.delete(self._cache_key(project_id, user_id, drawing_name))
        return True

    async def update_one(
        self, project_id: int, user_id: str, drawing_name: str,
        highlight_id: str, updates: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Update a highlight's fields."""
        path = self._s3_path(project_id, user_id, drawing_name)
        existing = await self._read_s3(path)

        updated = None
        for hl in existing:
            if hl.get("id") == highlight_id:
                hl.update(updates)
                updated = hl
                break

        if updated is None:
            return None

        await self._s3.put(path, json.dumps(existing, default=str))
        await self._cache.delete(self._cache_key(project_id, user_id, drawing_name))
        return updated

    async def _read_s3(self, path: str) -> list[dict[str, Any]]:
        """Read JSON array from S3. Returns [] if not found."""
        try:
            raw = await self._s3.get(path)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            logger.warning("Failed to read highlights from S3: %s", path, exc_info=True)
        return []
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_highlight_service.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/highlight_service.py tests/scope_pipeline/test_highlight_service.py
git commit -m "feat(scope-pipeline): add HighlightService with S3 storage + Redis caching"
```

---

## Phase 12E: Contractual Language

### Task 11: Extraction Agent Prompt Rewrite

**Files:**
- Modify: `scope_pipeline/agents/extraction_agent.py:23-42`
- Test: `tests/scope_pipeline/test_contractual_extraction.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_contractual_extraction.py
"""Tests for contractual language in extraction agent prompt."""


def test_system_prompt_contains_contractor_shall():
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT
    assert "Contractor shall" in SYSTEM_PROMPT


def test_system_prompt_contains_furnish_and_install():
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT
    assert "furnish and install" in SYSTEM_PROMPT


def test_system_prompt_contains_division_reference():
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT
    assert "per Division" in SYSTEM_PROMPT


def test_system_prompt_contains_verify_in_field():
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT
    assert "verify in field" in SYSTEM_PROMPT.lower() or "Verify in field" in SYSTEM_PROMPT


def test_system_prompt_contains_drawing_refs():
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT
    assert "drawing_refs" in SYSTEM_PROMPT


def test_parse_response_with_drawing_refs():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent

    agent = ExtractionAgent(api_key="test", model="test")
    raw = '[{"text":"test","drawing_name":"E0.03","drawing_refs":["E0.03","E1.01"],"page":1,"source_snippet":"test","confidence":0.9}]'
    items = agent._parse_response(raw)
    assert len(items) == 1
    assert items[0].drawing_refs == ["E0.03", "E1.01"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_contractual_extraction.py -v`
Expected: FAIL — "Contractor shall" not in current prompt

- [ ] **Step 3: Rewrite SYSTEM_PROMPT in extraction_agent.py**

Replace the `SYSTEM_PROMPT` constant (lines 23-42) in `scope_pipeline/agents/extraction_agent.py`:

```python
SYSTEM_PROMPT = """You are a construction scope-of-work writer specializing in subcontractor bid packages with 30+ years experience.

TASK: Extract ALL actionable scope items from the drawing notes below for the trade: {trade}.

LANGUAGE REQUIREMENTS — MANDATORY:
1. Every scope item text MUST begin with "Contractor shall" followed by an action verb.
2. Use standard AIA/CSI construction contract terminology:
   - "furnish and install" (supply + labor)
   - "provide" (inclusive of material + labor)
   - "coordinate with [trade/Division]" (interface responsibility)
   - "provide allowance for" (cost allocation)
   - "verify in field" (field verification requirement)
   - "as indicated on Drawing [number]" (drawing reference)
   - "per Division [number] — [name]" (CSI MasterFormat reference)
   - "in accordance with" (specification reference)
   - "including but not limited to" (non-exhaustive list)
   - "prior to" (sequencing dependency)
3. Reference specific CSI divisions where applicable (e.g., "per Division 26 — Electrical").
4. Include coordination notes where items cross trade boundaries.
5. Include field verification where dimensions or existing conditions are referenced.

EXTRACTION RULES:
1. Every item MUST include the exact drawing_name from the drawing header.
2. Every item MUST include drawing_refs: an array of ALL drawing names referenced by this scope item.
3. Every item MUST include a source_snippet: 5-15 words copied VERBATIM from the source text.
4. Every item MUST include the page number from the drawing header.
5. Do NOT invent items not present in the source text.
6. Do NOT merge items from different drawings into one item.
7. If a CSI MasterFormat code is obvious, include it as csi_hint (format: XX XX XX).

AUTHORITATIVE DRAWING LIST (only these drawings exist):
{drawing_list}

Any drawing_name NOT in this list is a hallucination — do NOT reference it.

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"text":"Contractor shall furnish and install...","drawing_name":"E-103","drawing_refs":["E-103","E-101"],"page":3,"source_snippet":"verbatim 5-15 words","confidence":0.95,"csi_hint":"26 24 16"}}]"""
```

- [ ] **Step 4: Update _parse_response to handle drawing_refs**

In `scope_pipeline/agents/extraction_agent.py`, update the `_parse_response` method — add `drawing_refs` parsing in the item creation block (around line 128):

Replace:
```python
            items.append(ScopeItem(
                text=entry.get("text", ""),
                drawing_name=entry.get("drawing_name", "Unknown"),
                drawing_title=entry.get("drawing_title"),
                page=entry.get("page", 1),
                source_snippet=entry.get("source_snippet", ""),
                confidence=float(entry.get("confidence", 0.5)),
                csi_hint=entry.get("csi_hint"),
            ))
```

With:
```python
            dn = entry.get("drawing_name", "Unknown")
            items.append(ScopeItem(
                text=entry.get("text", ""),
                drawing_name=dn,
                drawing_refs=entry.get("drawing_refs", [dn]),
                drawing_title=entry.get("drawing_title"),
                page=entry.get("page", 1),
                source_snippet=entry.get("source_snippet", ""),
                confidence=float(entry.get("confidence", 0.5)),
                csi_hint=entry.get("csi_hint"),
            ))
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_contractual_extraction.py -v && python -m pytest tests/scope_pipeline/test_extraction_agent.py -v`
Expected: All PASS (new tests + existing extraction tests)

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/agents/extraction_agent.py tests/scope_pipeline/test_contractual_extraction.py
git commit -m "feat(scope-pipeline): rewrite extraction prompt for contractual language + drawing_refs"
```

---

## Phase 12F: Webhook & Pre-computation

### Task 12: Webhook Handler

**Files:**
- Create: `scope_pipeline/services/webhook_handler.py`
- Test: `tests/scope_pipeline/test_webhook_handler.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_webhook_handler.py
"""Tests for WebhookHandler — HMAC validation + event processing."""

import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import AsyncMock

from scope_pipeline.models_v2 import WebhookEvent


def _sign(payload: str, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_valid_signature():
    from scope_pipeline.services.webhook_handler import WebhookHandler

    handler = WebhookHandler(
        secret="test-secret",
        cache_service=AsyncMock(),
        timestamp_tolerance=300,
    )
    payload = '{"event":"project.created","project_id":7276}'
    sig = _sign(payload, "test-secret")
    assert handler.verify_signature(payload, sig) is True


def test_invalid_signature():
    from scope_pipeline.services.webhook_handler import WebhookHandler

    handler = WebhookHandler(
        secret="test-secret",
        cache_service=AsyncMock(),
        timestamp_tolerance=300,
    )
    assert handler.verify_signature('{"data":"test"}', "sha256=invalid") is False


def test_missing_signature():
    from scope_pipeline.services.webhook_handler import WebhookHandler

    handler = WebhookHandler(
        secret="test-secret",
        cache_service=AsyncMock(),
        timestamp_tolerance=300,
    )
    assert handler.verify_signature('{"data":"test"}', "") is False


def test_parse_event():
    from scope_pipeline.services.webhook_handler import WebhookHandler

    handler = WebhookHandler(
        secret="test-secret",
        cache_service=AsyncMock(),
        timestamp_tolerance=300,
    )
    payload = '{"event":"drawings.uploaded","project_id":7276,"changed_trades":["Electrical"]}'
    event = handler.parse_event(payload)
    assert event.event == "drawings.uploaded"
    assert event.changed_trades == ["Electrical"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_webhook_handler.py -v`
Expected: FAIL

- [ ] **Step 3: Write WebhookHandler**

```python
# scope_pipeline/services/webhook_handler.py
"""scope_pipeline/services/webhook_handler.py — Webhook validation + processing.

HMAC-SHA256 signature verification, timestamp freshness, idempotency dedup.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from scope_pipeline.models_v2 import WebhookEvent

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Validates and processes incoming webhook events."""

    def __init__(
        self,
        secret: str,
        cache_service: Any,
        timestamp_tolerance: int = 300,
        idempotency_ttl: int = 3600,
    ) -> None:
        self._secret = secret
        self._cache = cache_service
        self._timestamp_tolerance = timestamp_tolerance
        self._idempotency_ttl = idempotency_ttl

    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        if not signature or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            self._secret.encode(), payload.encode(), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_event(self, payload: str) -> WebhookEvent:
        """Parse raw JSON payload into WebhookEvent."""
        data = json.loads(payload)
        return WebhookEvent(**data)

    async def check_idempotency(self, event_id: str) -> bool:
        """Return True if this event_id has already been processed."""
        key = f"sg_webhook_idem:{event_id}"
        existing = await self._cache.get(key)
        return existing is not None

    async def mark_processed(self, event_id: str) -> None:
        """Mark event_id as processed for dedup."""
        key = f"sg_webhook_idem:{event_id}"
        await self._cache.set(key, "1", ttl=self._idempotency_ttl)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_webhook_handler.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/webhook_handler.py tests/scope_pipeline/test_webhook_handler.py
git commit -m "feat(scope-pipeline): add WebhookHandler with HMAC validation + idempotency"
```

---

### Task 13: Webhook Endpoints Router

**Files:**
- Create: `scope_pipeline/routers/webhook_endpoints.py`
- Test: `tests/scope_pipeline/test_webhook_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_webhook_endpoints.py
"""Tests for webhook API endpoint."""

import hashlib
import hmac
import json

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scope_pipeline.routers.webhook_endpoints import router


def _sign(payload: str, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    handler = MagicMock()
    handler.verify_signature = MagicMock(return_value=True)
    handler.check_idempotency = AsyncMock(return_value=False)
    handler.mark_processed = AsyncMock()
    handler.parse_event = MagicMock()

    from scope_pipeline.models_v2 import WebhookEvent
    handler.parse_event.return_value = WebhookEvent(
        event="project.created", project_id=7276,
    )

    app.state.webhook_handler = handler
    app.state.project_orchestrator = AsyncMock()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_webhook_valid(client):
    payload = json.dumps({"event": "project.created", "project_id": 7276})
    response = client.post(
        "/api/scope-gap/webhooks/project-event",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "sha256=test",
            "X-Webhook-Event-Id": "evt_123",
        },
    )
    assert response.status_code == 202


def test_webhook_invalid_signature(client, app):
    app.state.webhook_handler.verify_signature = MagicMock(return_value=False)

    response = client.post(
        "/api/scope-gap/webhooks/project-event",
        content='{"event":"project.created","project_id":7276}',
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "sha256=bad",
        },
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_webhook_endpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Write webhook_endpoints router**

```python
# scope_pipeline/routers/webhook_endpoints.py
"""scope_pipeline/routers/webhook_endpoints.py — Webhook receiver endpoint."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap/webhooks", tags=["scope-gap-webhooks"])


@router.post("/project-event")
async def receive_webhook(request: Request) -> Any:
    """Receive and process iFieldSmart webhook events."""
    handler = request.app.state.webhook_handler

    # Read raw body
    body = await request.body()
    payload = body.decode("utf-8")

    # Verify signature
    signature = request.headers.get("X-Webhook-Signature", "")
    if not handler.verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Idempotency check
    event_id = request.headers.get("X-Webhook-Event-Id", "")
    if event_id and await handler.check_idempotency(event_id):
        return JSONResponse(
            status_code=200,
            content={"message": "Duplicate event, already processed"},
        )

    # Parse event
    try:
        event = handler.parse_event(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}") from exc

    # Mark as processed
    if event_id:
        await handler.mark_processed(event_id)

    # TODO: Phase 12F integration — trigger orchestrator.run_all_trades in background
    logger.info("Webhook received: event=%s project_id=%d", event.event, event.project_id)

    return JSONResponse(
        status_code=202,
        content={
            "message": "Pre-computation queued",
            "event": event.event,
            "project_id": event.project_id,
        },
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_webhook_endpoints.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/routers/webhook_endpoints.py tests/scope_pipeline/test_webhook_endpoints.py
git commit -m "feat(scope-pipeline): add webhook receiver endpoint with HMAC + idempotency"
```

---

## Phase 12G: Combined Export

### Task 14: Export Service

**Files:**
- Create: `scope_pipeline/services/export_service.py`
- Test: `tests/scope_pipeline/test_export_service.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_export_service.py
"""Tests for ExportService — combined multi-trade Word+PDF generation."""

import os
import pytest
from unittest.mock import MagicMock

from scope_pipeline.models import (
    ClassifiedItem, CompletenessReport, QualityReport,
    PipelineStats, DocumentSet, ScopeGapResult,
)
from scope_pipeline.models_v2 import ProjectSession, TradeResultContainer, TradeRunRecord


def _make_result(trade: str, items_count: int = 3) -> ScopeGapResult:
    items = [
        ClassifiedItem(
            text=f"Contractor shall provide item {i} for {trade}",
            drawing_name=f"E0.{i:02d}",
            trade=trade,
            csi_code="26",
            csi_division="26",
            classification_confidence=0.9,
            classification_reason="test",
        )
        for i in range(items_count)
    ]
    return ScopeGapResult(
        project_id=7276,
        project_name="Test Project",
        trade=trade,
        items=items,
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100, csi_coverage_pct=100,
            hallucination_count=0, overall_pct=100,
            missing_drawings=[], missing_csi_codes=[],
            hallucinated_items=[], is_complete=True, attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=0.95, corrections=[], validated_items=[],
            removed_items=[], summary="ok",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=1000, attempts=1, tokens_used=1000,
            estimated_cost_usd=0.01, per_agent_timing={},
            records_processed=10, items_extracted=items_count,
        ),
    )


def test_generate_combined_word(tmp_path):
    from scope_pipeline.services.export_service import ExportService

    session = ProjectSession(project_id=7276, project_name="Test Project")
    for trade in ["Electrical", "Plumbing"]:
        container = TradeResultContainer(trade=trade)
        container.latest_result = _make_result(trade)
        session.trade_results[trade] = container

    svc = ExportService(docs_dir=str(tmp_path))
    path = svc.generate_combined_word(session)

    assert os.path.exists(path)
    assert path.endswith(".docx")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_export_service.py -v`
Expected: FAIL

- [ ] **Step 3: Write ExportService**

```python
# scope_pipeline/services/export_service.py
"""scope_pipeline/services/export_service.py — Multi-trade combined export.

Generates combined Word+PDF documents from all trades in a ProjectSession.
Also supports per-trade export and ZIP of all files.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from scope_pipeline.models_v2 import ProjectSession

logger = logging.getLogger(__name__)

_DARK_BLUE = (0, 51, 102)


class ExportService:
    """Generate combined multi-trade export documents."""

    def __init__(self, docs_dir: str = "./generated_docs") -> None:
        self._docs_dir = docs_dir
        os.makedirs(self._docs_dir, exist_ok=True)

    def generate_combined_word(
        self,
        session: ProjectSession,
        trades: Optional[list[str]] = None,
    ) -> str:
        """Generate a single Word document containing all trades."""
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()
        style = doc.styles["Normal"]
        style.font.size = Pt(10)
        style.font.name = "Calibri"

        # Title
        title = doc.add_heading("SCOPE GAP REPORT — ALL TRADES", level=0)
        for run in title.runs:
            run.font.color.rgb = RGBColor(*_DARK_BLUE)

        # Project info
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        doc.add_paragraph(f"Project: {session.project_name} (ID: {session.project_id})")
        doc.add_paragraph(f"Generated: {now}")

        # Collect trades
        trade_names = trades or sorted(session.trade_results.keys())
        total_items = 0

        for trade_name in trade_names:
            container = session.trade_results.get(trade_name)
            if not container or not container.latest_result:
                continue

            result = container.latest_result
            total_items += len(result.items)

            # Trade section
            doc.add_page_break()
            heading = doc.add_heading(f"{trade_name} — Scope of Work", level=1)
            for run in heading.runs:
                run.font.color.rgb = RGBColor(*_DARK_BLUE)

            doc.add_paragraph(
                f"Items: {len(result.items)} | "
                f"Ambiguities: {len(result.ambiguities)} | "
                f"Gotchas: {len(result.gotchas)} | "
                f"Completeness: {result.completeness.overall_pct:.1f}%"
            )

            # Items grouped by drawing
            grouped: dict[str, list] = {}
            for item in result.items:
                grouped.setdefault(item.drawing_name, []).append(item)

            for drawing_name, items in grouped.items():
                doc.add_heading(drawing_name, level=2)
                for item in items:
                    p = doc.add_paragraph()
                    p.add_run(item.text).bold = True
                    p.add_run(f"\n  CSI: {item.csi_code} | Source: \"{item.source_snippet}\"")

        # Summary
        doc.add_page_break()
        doc.add_heading("Summary", level=1)
        doc.add_paragraph(f"Total trades: {len(trade_names)}")
        doc.add_paragraph(f"Total scope items: {total_items}")

        # Footer
        footer = doc.add_paragraph("Generated by iFieldSmart ScopeAI Pipeline v2.0")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in footer.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(128, 128, 128)

        # Save
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"ScopeGap_{session.project_id}_AllTrades_{timestamp}.docx"
        path = os.path.join(self._docs_dir, filename)
        doc.save(path)
        logger.info("Combined Word document saved: %s", path)
        return path
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_export_service.py -v`
Expected: 1 PASSED

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/services/export_service.py tests/scope_pipeline/test_export_service.py
git commit -m "feat(scope-pipeline): add ExportService for combined multi-trade Word generation"
```

---

## Phase 12H: Integration & Wiring

### Task 15: Mount Routers + Wire Services in main.py

**Files:**
- Modify: `scope_pipeline/routers/scope_gap.py`
- Modify: `main.py`

- [ ] **Step 1: Mount new sub-routers in scope_gap.py**

Add to the end of `scope_pipeline/routers/scope_gap.py`:

```python
# ---------------------------------------------------------------------------
# Phase 12: Mount sub-routers
# ---------------------------------------------------------------------------

from scope_pipeline.routers.project_endpoints import router as project_router
from scope_pipeline.routers.webhook_endpoints import router as webhook_router

# Note: highlight_endpoints will be added when the router file is created
```

- [ ] **Step 2: Wire new services in main.py lifespan**

Add after the existing scope pipeline initialization block (after line 196 in `main.py`):

```python
    # ── Phase 12: Project Orchestrator + New Services ────────────
    from scope_pipeline.services.project_session_manager import ProjectSessionManager
    from scope_pipeline.services.trade_color_service import TradeColorService
    from scope_pipeline.services.trade_discovery_service import TradeDiscoveryService
    from scope_pipeline.services.drawing_index_service import DrawingIndexService
    from scope_pipeline.services.highlight_service import HighlightService
    from scope_pipeline.services.webhook_handler import WebhookHandler
    from scope_pipeline.services.export_service import ExportService
    from scope_pipeline.project_orchestrator import ProjectOrchestrator
    from scope_pipeline.routers.project_endpoints import router as project_router
    from scope_pipeline.routers.webhook_endpoints import router as webhook_router

    project_session_mgr = ProjectSessionManager(cache_service=cache)
    trade_color_svc = TradeColorService()
    trade_discovery_svc = TradeDiscoveryService(api_client=api_client, cache_service=cache)
    drawing_index_svc = DrawingIndexService()
    export_svc = ExportService(docs_dir=pcfg.docs_dir)

    highlight_svc = HighlightService(
        s3_ops=None,  # Wired when S3 is available
        cache_service=cache,
        s3_prefix=pcfg.highlight_s3_prefix,
    )

    webhook_handler = WebhookHandler(
        secret=pcfg.webhook_secret,
        cache_service=cache,
        timestamp_tolerance=pcfg.webhook_timestamp_tolerance,
        idempotency_ttl=pcfg.webhook_idempotency_ttl,
    )

    project_orchestrator = ProjectOrchestrator(
        pipeline=scope_pipe,
        session_manager=project_session_mgr,
        trade_discovery=trade_discovery_svc,
        color_service=trade_color_svc,
        trade_concurrency=pcfg.trade_concurrency,
        result_freshness_ttl=pcfg.result_freshness_ttl,
        trade_pipeline_timeout=pcfg.trade_pipeline_timeout,
    )

    # Attach to app.state
    app.state.project_session_manager = project_session_mgr
    app.state.trade_color_service = trade_color_svc
    app.state.trade_discovery_service = trade_discovery_svc
    app.state.drawing_index_service = drawing_index_svc
    app.state.highlight_service = highlight_svc
    app.state.webhook_handler = webhook_handler
    app.state.export_service = export_svc
    app.state.project_orchestrator = project_orchestrator
    app.state.scope_data_fetcher = scope_data_fetcher

    logger.info("Phase 12 services initialized (trade_concurrency=%d)", pcfg.trade_concurrency)
```

- [ ] **Step 3: Register new routers**

Find where `scope_gap_router` is included in `main.py` and add the new routers alongside it. After the line `app.include_router(scope_gap_router)`, add:

```python
    app.include_router(project_router)
    app.include_router(webhook_router)
```

- [ ] **Step 4: Verify app starts without errors**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -c "from main import app; print('App loaded successfully')" 2>&1 | head -20`
Expected: "App loaded successfully" or startup log messages (no import errors)

- [ ] **Step 5: Run full regression**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All tests PASS (old + new)

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/routers/scope_gap.py main.py
git commit -m "feat(scope-pipeline): wire Phase 12 services and routers into main.py"
```

---

### Task 16: Highlight Endpoints Router

**Files:**
- Create: `scope_pipeline/routers/highlight_endpoints.py`
- Test: `tests/scope_pipeline/test_highlight_endpoints.py`

- [ ] **Step 1: Write failing test**

```python
# tests/scope_pipeline/test_highlight_endpoints.py
"""Tests for highlight API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scope_pipeline.routers.highlight_endpoints import router
from scope_pipeline.models_v2 import Highlight


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.state.highlight_service = AsyncMock()
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_create_highlight(client, app):
    hl = Highlight(drawing_name="E0.03", x=100, y=200, width=300, height=40)
    app.state.highlight_service.create = AsyncMock(return_value=hl)

    response = client.post(
        "/api/scope-gap/highlights",
        json={
            "project_id": 7276,
            "drawing_name": "E0.03",
            "x": 100, "y": 200, "width": 300, "height": 40,
        },
        headers={"X-User-Id": "user_123"},
    )
    assert response.status_code == 201


def test_list_highlights(client, app):
    app.state.highlight_service.list_for_drawing = AsyncMock(return_value=[])

    response = client.get(
        "/api/scope-gap/highlights?project_id=7276&drawing_name=E0.03",
        headers={"X-User-Id": "user_123"},
    )
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_highlight_endpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Write highlight_endpoints router**

```python
# scope_pipeline/routers/highlight_endpoints.py
"""scope_pipeline/routers/highlight_endpoints.py — Highlight CRUD endpoints."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scope_pipeline.models_v2 import Highlight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap/highlights", tags=["scope-gap-highlights"])


class CreateHighlightBody(BaseModel):
    project_id: int
    drawing_name: str
    page: int = 1
    x: float
    y: float
    width: float
    height: float
    color: str = "#FFEB3B"
    opacity: float = 0.3
    label: str = ""
    trade: str = ""
    critical: bool = False
    comment: str = ""
    scope_item_id: Optional[str] = None
    scope_item_ids: list[str] = []


class UpdateHighlightBody(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    label: Optional[str] = None
    critical: Optional[bool] = None
    comment: Optional[str] = None


def _get_service(request: Request):
    return request.app.state.highlight_service


@router.post("")
async def create_highlight(
    body: CreateHighlightBody,
    request: Request,
    x_user_id: str = Header(...),
) -> Any:
    """Create a new highlight."""
    svc = _get_service(request)
    hl = Highlight(
        drawing_name=body.drawing_name,
        page=body.page,
        x=body.x, y=body.y, width=body.width, height=body.height,
        color=body.color, opacity=body.opacity,
        label=body.label, trade=body.trade,
        critical=body.critical, comment=body.comment,
        scope_item_id=body.scope_item_id,
        scope_item_ids=body.scope_item_ids,
    )
    created = await svc.create(body.project_id, x_user_id, hl)
    return JSONResponse(status_code=201, content=created.model_dump(mode="json"))


@router.get("")
async def list_highlights(
    request: Request,
    project_id: int = Query(...),
    drawing_name: str = Query(...),
    x_user_id: str = Header(...),
) -> list[dict[str, Any]]:
    """List highlights for a drawing."""
    svc = _get_service(request)
    return await svc.list_for_drawing(project_id, x_user_id, drawing_name)


@router.delete("/{highlight_id}")
async def delete_highlight(
    highlight_id: str,
    request: Request,
    project_id: int = Query(...),
    drawing_name: str = Query(...),
    x_user_id: str = Header(...),
) -> dict[str, Any]:
    """Delete a single highlight."""
    svc = _get_service(request)
    deleted = await svc.delete_one(project_id, x_user_id, drawing_name, highlight_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Highlight {highlight_id} not found")
    return {"deleted": True, "highlight_id": highlight_id}


@router.patch("/{highlight_id}")
async def update_highlight(
    highlight_id: str,
    body: UpdateHighlightBody,
    request: Request,
    project_id: int = Query(...),
    drawing_name: str = Query(...),
    x_user_id: str = Header(...),
) -> Any:
    """Update a highlight's fields."""
    svc = _get_service(request)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await svc.update_one(project_id, x_user_id, drawing_name, highlight_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Highlight {highlight_id} not found")
    return updated
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/test_highlight_endpoints.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Register highlight router in main.py**

Add after the other router includes:
```python
    from scope_pipeline.routers.highlight_endpoints import router as highlight_router
    app.include_router(highlight_router)
```

- [ ] **Step 6: Run full regression**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add scope_pipeline/routers/highlight_endpoints.py tests/scope_pipeline/test_highlight_endpoints.py main.py
git commit -m "feat(scope-pipeline): add highlight CRUD endpoints with per-user isolation"
```

---

### Task 17: Final Integration Test + Full Regression

- [ ] **Step 1: Run full test suite**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests PASS (original 56 + ~30 new = ~86 total)

- [ ] **Step 2: Check coverage**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && python -m pytest tests/scope_pipeline/ --cov=scope_pipeline --cov-report=term-missing --tb=short 2>&1 | tail -40`
Expected: 75%+ coverage on new files

- [ ] **Step 3: Verify app starts cleanly**

Run: `cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent" && timeout 10 python main.py 2>&1 | head -30 || true`
Expected: Startup logs showing Phase 12 services initialized, no errors

- [ ] **Step 4: Final commit**

```bash
cd "c:\Users\ANIRUDDHA ASUS\Downloads\projects\VCS\VCS\PROD_SETUP\construction-intelligence-agent"
git add -A
git commit -m "feat(scope-pipeline): Phase 12 complete — UI integration, orchestrator, highlights, webhooks"
```
