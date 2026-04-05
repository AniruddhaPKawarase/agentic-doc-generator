"""
tests/scope_pipeline/test_orchestrator.py — Tests for ScopeGapPipeline orchestrator.

Covers:
  1. Single-pass completion
  2. Backpropagation on incomplete first attempt
  3. Partial result after max attempts exhausted
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    MergedResults,
    QualityCorrection,
    QualityReport,
    ScopeGapRequest,
    ScopeGapSession,
    ScopeItem,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_scope_item(drawing: str = "E-103", text: str = "test data") -> ScopeItem:
    return ScopeItem(
        text=text,
        drawing_name=drawing,
        drawing_title="Power Plan",
        confidence=0.9,
    )


def _make_classified_item(
    drawing: str = "E-103",
    text: str = "test data",
    trade: str = "Electrical",
    csi: str = "26 24 16",
) -> ClassifiedItem:
    return ClassifiedItem(
        text=text,
        drawing_name=drawing,
        drawing_title="Power Plan",
        confidence=0.9,
        trade=trade,
        csi_code=csi,
        csi_division="Division 26",
        classification_confidence=0.85,
        classification_reason="Electrical scope",
    )


def _make_ambiguity(scope_text: str = "conduit routing") -> AmbiguityItem:
    return AmbiguityItem(
        scope_text=scope_text,
        competing_trades=["Electrical", "Mechanical"],
        severity="medium",
        recommendation="Clarify responsibility",
        source_items=["itm_001"],
        drawing_refs=["E-103"],
    )


def _make_gotcha(description: str = "Missing grounding detail") -> GotchaItem:
    return GotchaItem(
        risk_type="missing_scope",
        description=description,
        severity="high",
        affected_trades=["Electrical"],
        recommendation="Review grounding plan",
        drawing_refs=["E-103"],
    )


def _make_quality_report() -> QualityReport:
    return QualityReport(
        accuracy_score=0.95,
        corrections=[],
        validated_items=["itm_001"],
        removed_items=[],
        summary="All items validated",
    )


def _make_completeness(
    is_complete: bool = True,
    attempt: int = 1,
    missing_drawings: list[str] | None = None,
    hallucinated_items: list[str] | None = None,
) -> CompletenessReport:
    return CompletenessReport(
        drawing_coverage_pct=100.0 if is_complete else 50.0,
        csi_coverage_pct=100.0,
        hallucination_count=len(hallucinated_items) if hallucinated_items else 0,
        overall_pct=98.0 if is_complete else 60.0,
        missing_drawings=missing_drawings or [],
        missing_csi_codes=[],
        hallucinated_items=hallucinated_items or [],
        is_complete=is_complete,
        attempt=attempt,
    )


def _build_mock_data_fetcher(records=None, drawing_names=None, csi_codes=None):
    fetcher = AsyncMock()
    fetcher.fetch_records = AsyncMock(return_value={
        "records": records or [
            {"drawing_name": "E-103", "text": "test data", "drawing_title": "Power Plan"},
        ],
        "drawing_names": drawing_names or {"E-103"},
        "csi_codes": csi_codes or {"26 24 16"},
    })
    return fetcher


def _build_mock_session_manager():
    session = ScopeGapSession(project_id=7298, trade="Electrical")
    mgr = AsyncMock()
    mgr.get_or_create = AsyncMock(return_value=session)
    mgr.update = AsyncMock()
    return mgr, session


def _build_mock_emitter():
    return MagicMock(spec=ProgressEmitter)


def _build_mock_extraction_agent(items=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=items or [_make_scope_item()],
        tokens_used=100,
        elapsed_ms=500,
    ))
    return agent


def _build_mock_classification_agent(items=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=items or [_make_classified_item()],
        tokens_used=80,
        elapsed_ms=400,
    ))
    return agent


def _build_mock_ambiguity_agent(items=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=items or [_make_ambiguity()],
        tokens_used=60,
        elapsed_ms=300,
    ))
    return agent


def _build_mock_gotcha_agent(items=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=items or [_make_gotcha()],
        tokens_used=60,
        elapsed_ms=300,
    ))
    return agent


def _build_mock_completeness_agent(report=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=report or _make_completeness(is_complete=True),
        tokens_used=0,
        elapsed_ms=10,
    ))
    return agent


def _build_mock_quality_agent(report=None):
    agent = AsyncMock()
    agent.run = AsyncMock(return_value=MagicMock(
        data=report or _make_quality_report(),
        tokens_used=50,
        elapsed_ms=200,
    ))
    return agent


def _build_mock_document_agent():
    agent = AsyncMock()
    agent.generate_all = AsyncMock(return_value=DocumentSet(word_path="/tmp/test.docx"))
    return agent


# ---------------------------------------------------------------------------
# Test 1: Pipeline completes in one pass
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_completes_in_one_pass():
    """All agents succeed, completeness is_complete=True on first attempt."""
    from scope_pipeline.orchestrator import ScopeGapPipeline

    extraction = _build_mock_extraction_agent()
    classification = _build_mock_classification_agent()
    ambiguity = _build_mock_ambiguity_agent()
    gotcha = _build_mock_gotcha_agent()
    completeness = _build_mock_completeness_agent()
    quality = _build_mock_quality_agent()
    document = _build_mock_document_agent()
    fetcher = _build_mock_data_fetcher()
    session_mgr, _ = _build_mock_session_manager()
    emitter = _build_mock_emitter()

    pipeline = ScopeGapPipeline(
        extraction_agent=extraction,
        classification_agent=classification,
        ambiguity_agent=ambiguity,
        gotcha_agent=gotcha,
        completeness_agent=completeness,
        quality_agent=quality,
        document_agent=document,
        data_fetcher=fetcher,
        session_manager=session_mgr,
    )

    request = ScopeGapRequest(project_id=7298, trade="Electrical")
    result = await pipeline.run(request, emitter, project_name="Test Project")

    # Verify result structure
    assert result.project_id == 7298
    assert result.trade == "Electrical"
    assert result.completeness.is_complete is True
    assert result.pipeline_stats.attempts == 1
    assert len(result.items) >= 1

    # Verify parallel agents each called exactly once
    classification.run.assert_called_once()
    ambiguity.run.assert_called_once()
    gotcha.run.assert_called_once()

    # Verify extraction called once (no backpropagation)
    extraction.run.assert_called_once()

    # Verify session was updated
    session_mgr.update.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Backpropagation on incomplete first attempt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_backpropagation_on_incomplete():
    """Completeness fails on attempt 1 (missing E-104), succeeds on attempt 2."""
    from scope_pipeline.orchestrator import ScopeGapPipeline

    # Extraction: attempt 1 returns E-103 items, attempt 2 adds E-104 items
    extraction = AsyncMock()
    extraction.run = AsyncMock(side_effect=[
        MagicMock(
            data=[_make_scope_item("E-103", "panel schedule")],
            tokens_used=100,
            elapsed_ms=500,
        ),
        MagicMock(
            data=[_make_scope_item("E-104", "grounding detail")],
            tokens_used=100,
            elapsed_ms=500,
        ),
    ])

    # Classification returns items for whatever was extracted
    classification = AsyncMock()
    classification.run = AsyncMock(side_effect=[
        MagicMock(
            data=[_make_classified_item("E-103", "panel schedule")],
            tokens_used=80,
            elapsed_ms=400,
        ),
        MagicMock(
            data=[
                _make_classified_item("E-103", "panel schedule"),
                _make_classified_item("E-104", "grounding detail"),
            ],
            tokens_used=80,
            elapsed_ms=400,
        ),
    ])

    ambiguity = _build_mock_ambiguity_agent()
    gotcha = _build_mock_gotcha_agent()

    # Completeness: attempt 1 incomplete (missing E-104), attempt 2 complete
    completeness = AsyncMock()
    completeness.run = AsyncMock(side_effect=[
        MagicMock(
            data=_make_completeness(
                is_complete=False,
                attempt=1,
                missing_drawings=["E-104"],
            ),
            tokens_used=0,
            elapsed_ms=10,
        ),
        MagicMock(
            data=_make_completeness(is_complete=True, attempt=2),
            tokens_used=0,
            elapsed_ms=10,
        ),
    ])

    quality = _build_mock_quality_agent()
    document = _build_mock_document_agent()
    fetcher = _build_mock_data_fetcher(
        records=[
            {"drawing_name": "E-103", "text": "panel schedule", "drawing_title": "Power Plan"},
            {"drawing_name": "E-104", "text": "grounding detail", "drawing_title": "Grounding Plan"},
        ],
        drawing_names={"E-103", "E-104"},
        csi_codes={"26 24 16"},
    )
    session_mgr, _ = _build_mock_session_manager()
    emitter = _build_mock_emitter()

    pipeline = ScopeGapPipeline(
        extraction_agent=extraction,
        classification_agent=classification,
        ambiguity_agent=ambiguity,
        gotcha_agent=gotcha,
        completeness_agent=completeness,
        quality_agent=quality,
        document_agent=document,
        data_fetcher=fetcher,
        session_manager=session_mgr,
    )

    request = ScopeGapRequest(project_id=7298, trade="Electrical")
    result = await pipeline.run(request, emitter, project_name="Test Project")

    # Extraction called twice: full pass + targeted pass
    assert extraction.run.call_count == 2
    assert result.pipeline_stats.attempts == 2
    assert result.completeness.is_complete is True


# ---------------------------------------------------------------------------
# Test 3: Partial result after max attempts exhausted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_returns_partial_after_max_attempts():
    """Completeness never reaches threshold after 3 attempts."""
    from scope_pipeline.orchestrator import ScopeGapPipeline
    from scope_pipeline.config import PipelineConfig

    extraction = _build_mock_extraction_agent()
    classification = _build_mock_classification_agent()
    ambiguity = _build_mock_ambiguity_agent()
    gotcha = _build_mock_gotcha_agent()

    # Completeness always returns incomplete with missing E-104
    incomplete_report = _make_completeness(
        is_complete=False,
        attempt=1,
        missing_drawings=["E-104"],
    )
    completeness = AsyncMock()
    completeness.run = AsyncMock(return_value=MagicMock(
        data=incomplete_report,
        tokens_used=0,
        elapsed_ms=10,
    ))

    quality = _build_mock_quality_agent()
    document = _build_mock_document_agent()
    fetcher = _build_mock_data_fetcher()
    session_mgr, _ = _build_mock_session_manager()
    emitter = _build_mock_emitter()

    # Use config with max_attempts=3
    config = MagicMock()
    config.max_attempts = 3
    config.completeness_threshold = 95.0

    pipeline = ScopeGapPipeline(
        extraction_agent=extraction,
        classification_agent=classification,
        ambiguity_agent=ambiguity,
        gotcha_agent=gotcha,
        completeness_agent=completeness,
        quality_agent=quality,
        document_agent=document,
        data_fetcher=fetcher,
        session_manager=session_mgr,
        config=config,
    )

    request = ScopeGapRequest(project_id=7298, trade="Electrical")
    result = await pipeline.run(request, emitter, project_name="Test Project")

    assert result.completeness.is_complete is False
    assert result.pipeline_stats.attempts == 3

    # Verify terminal event is pipeline_partial
    partial_calls = [
        c for c in emitter.emit.call_args_list
        if c[0][0] == "pipeline_partial"
    ]
    assert len(partial_calls) == 1
