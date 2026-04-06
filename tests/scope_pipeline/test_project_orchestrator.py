"""tests/scope_pipeline/test_project_orchestrator.py — Tests for ProjectOrchestrator.

Covers:
  1. test_run_all_trades — happy path with 2 trades, both complete successfully.
  2. test_skips_fresh_trades — one trade has a recent result, so it is skipped.
  3. test_handles_trade_failure — one trade raises an exception; others still complete.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    PipelineStats,
    QualityCorrection,
    QualityReport,
    ScopeGapResult,
)
from scope_pipeline.models_v2 import (
    ProjectSession,
    TradeResultContainer,
    TradeRunRecord,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_result(trade: str, project_id: int = 7298) -> ScopeGapResult:
    """Build a minimal but valid ScopeGapResult for the given trade."""
    return ScopeGapResult(
        project_id=project_id,
        project_name="Test Project",
        trade=trade,
        items=[
            ClassifiedItem(
                text="some scope text",
                drawing_name="E-101",
                trade=trade,
                csi_code="26 00 00",
                csi_division="Division 26",
                classification_confidence=0.9,
                classification_reason="test",
            )
        ],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100.0,
            csi_coverage_pct=100.0,
            hallucination_count=0,
            overall_pct=100.0,
            missing_drawings=[],
            missing_csi_codes=[],
            hallucinated_items=[],
            is_complete=True,
            attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=1.0,
            corrections=[],
            validated_items=["itm_001"],
            removed_items=[],
            summary="All validated",
        ),
        documents=DocumentSet(word_path="/tmp/test.docx"),
        pipeline_stats=PipelineStats(
            total_ms=1000,
            attempts=1,
            tokens_used=500,
            estimated_cost_usd=0.001,
            per_agent_timing={"extraction_attempt_1": 500},
            records_processed=10,
            items_extracted=1,
        ),
    )


def _make_mock_pipeline(trades_to_result: dict[str, ScopeGapResult] | None = None):
    """Return a mock ScopeGapPipeline whose run() returns results per trade."""
    pipeline = MagicMock()

    async def _run(request, emitter, project_name=""):
        result = (trades_to_result or {}).get(request.trade)
        if result is None:
            result = _make_mock_result(request.trade, request.project_id)
        return result

    pipeline.run = AsyncMock(side_effect=_run)
    return pipeline


def _make_mock_session_manager(existing_session: ProjectSession | None = None):
    """Return a mock ProjectSessionManager."""
    mgr = MagicMock()

    async def _get_or_create(project_id, set_ids=None, project_name=""):
        if existing_session is not None:
            return existing_session
        return ProjectSession(
            project_id=project_id,
            project_name=project_name,
            set_ids=set_ids,
        )

    mgr.get_or_create = AsyncMock(side_effect=_get_or_create)
    mgr.update = AsyncMock()
    return mgr


def _make_mock_trade_discovery(trades: list[str]):
    """Return a mock TradeDiscovery object."""
    discovery = MagicMock()
    discovery.discover_trades = AsyncMock(return_value=trades)
    return discovery


def _make_mock_color_service():
    color_svc = MagicMock()
    color_svc.get_color = MagicMock(return_value={"hex": "#F48FB1", "rgb": [244, 143, 177]})
    return color_svc


def _make_emitter() -> MagicMock:
    return MagicMock(spec=ProgressEmitter)


# ---------------------------------------------------------------------------
# Test 1: run_all_trades — happy path, 2 trades
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_all_trades():
    """Both trades run successfully; session contains completed containers for each."""
    from scope_pipeline.project_orchestrator import ProjectOrchestrator

    trades = ["Electrical", "Plumbing"]
    pipeline = _make_mock_pipeline()
    session_mgr = _make_mock_session_manager()
    discovery = _make_mock_trade_discovery(trades)
    color_svc = _make_mock_color_service()
    emitter = _make_emitter()

    orchestrator = ProjectOrchestrator(
        pipeline=pipeline,
        session_manager=session_mgr,
        trade_discovery=discovery,
        color_service=color_svc,
        trade_concurrency=5,
    )

    session = await orchestrator.run_all_trades(
        project_id=7298,
        emitter=emitter,
        project_name="Test Project",
    )

    # Both trades should have been run
    assert pipeline.run.call_count == 2

    # Session should contain results for both trades (lowercased keys)
    assert "electrical" in session.trade_results
    assert "plumbing" in session.trade_results

    # Each container should have exactly one completed run
    elec_container = session.trade_results["electrical"]
    assert elec_container.versions[-1].status == "complete"

    plumb_container = session.trade_results["plumbing"]
    assert plumb_container.versions[-1].status == "complete"

    # session_manager.update must have been called once (after all trades finish)
    session_mgr.update.assert_awaited_once()

    # SSE events: session_loaded and all_complete must be emitted
    event_types = [call[0][0] for call in emitter.emit.call_args_list]
    assert "session_loaded" in event_types
    assert "all_complete" in event_types

    # trade_complete events for each trade
    trade_complete_events = [c for c in emitter.emit.call_args_list if c[0][0] == "trade_complete"]
    assert len(trade_complete_events) == 2


# ---------------------------------------------------------------------------
# Test 2: skips fresh trades
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_fresh_trades():
    """A trade whose last run is within the freshness TTL is skipped."""
    from scope_pipeline.project_orchestrator import ProjectOrchestrator

    # Pre-build a session where Electrical has a fresh result (completed 60s ago)
    fresh_record = TradeRunRecord(
        status="complete",
        completed_at=datetime.now(timezone.utc) - timedelta(seconds=60),
        items_count=5,
    )
    elec_container = TradeResultContainer(trade="electrical").add_run(fresh_record)
    existing_session = ProjectSession(
        project_id=7298,
        project_name="Test Project",
        trade_results={"electrical": elec_container},
    )

    trades = ["Electrical", "Plumbing"]
    pipeline = _make_mock_pipeline()
    session_mgr = _make_mock_session_manager(existing_session=existing_session)
    discovery = _make_mock_trade_discovery(trades)
    color_svc = _make_mock_color_service()
    emitter = _make_emitter()

    orchestrator = ProjectOrchestrator(
        pipeline=pipeline,
        session_manager=session_mgr,
        trade_discovery=discovery,
        color_service=color_svc,
        result_freshness_ttl=86400,  # 24hr TTL — 60s-old result is fresh
    )

    session = await orchestrator.run_all_trades(
        project_id=7298,
        emitter=emitter,
        project_name="Test Project",
    )

    # Only Plumbing should have run; Electrical was skipped
    assert pipeline.run.call_count == 1
    call_args = pipeline.run.call_args_list[0]
    run_request = call_args[0][0]
    assert run_request.trade == "Plumbing"

    # session_loaded event should report 1 cached, 1 to_run
    session_loaded_calls = [
        c for c in emitter.emit.call_args_list if c[0][0] == "session_loaded"
    ]
    assert len(session_loaded_calls) == 1
    session_loaded_data = session_loaded_calls[0][0][1]
    assert session_loaded_data["cached_count"] == 1
    assert session_loaded_data["to_run_count"] == 1


# ---------------------------------------------------------------------------
# Test 3: handles trade failure — others continue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handles_trade_failure():
    """One trade raises an exception; the other trade still completes."""
    from scope_pipeline.project_orchestrator import ProjectOrchestrator

    trades = ["Electrical", "Plumbing"]
    pipeline = MagicMock()

    plumbing_result = _make_mock_result("Plumbing")

    async def _run(request, emitter, project_name=""):
        if request.trade == "Electrical":
            raise RuntimeError("LLM timeout")
        return plumbing_result

    pipeline.run = AsyncMock(side_effect=_run)

    session_mgr = _make_mock_session_manager()
    discovery = _make_mock_trade_discovery(trades)
    color_svc = _make_mock_color_service()
    emitter = _make_emitter()

    orchestrator = ProjectOrchestrator(
        pipeline=pipeline,
        session_manager=session_mgr,
        trade_discovery=discovery,
        color_service=color_svc,
    )

    session = await orchestrator.run_all_trades(
        project_id=7298,
        emitter=emitter,
        project_name="Test Project",
    )

    # Pipeline called for both trades
    assert pipeline.run.call_count == 2

    # Electrical should be recorded as failed
    assert "electrical" in session.trade_results
    elec_record = session.trade_results["electrical"].versions[-1]
    assert elec_record.status == "failed"
    assert "LLM timeout" in (elec_record.error or "")

    # Plumbing should be recorded as complete
    assert "plumbing" in session.trade_results
    plumb_record = session.trade_results["plumbing"].versions[-1]
    assert plumb_record.status == "complete"

    # trade_failed event emitted for Electrical
    trade_failed_events = [c for c in emitter.emit.call_args_list if c[0][0] == "trade_failed"]
    assert len(trade_failed_events) == 1
    assert trade_failed_events[0][0][1]["trade"] == "Electrical"

    # trade_complete event emitted for Plumbing
    trade_complete_events = [c for c in emitter.emit.call_args_list if c[0][0] == "trade_complete"]
    assert len(trade_complete_events) == 1
    assert trade_complete_events[0][0][1]["trade"] == "Plumbing"

    # all_complete still emitted even though one trade failed
    all_complete_events = [c for c in emitter.emit.call_args_list if c[0][0] == "all_complete"]
    assert len(all_complete_events) == 1

    # session persisted
    session_mgr.update.assert_awaited_once()
