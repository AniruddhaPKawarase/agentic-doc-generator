"""tests/scope_pipeline/test_export_service.py — Unit tests for ExportService."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import pytest

from scope_pipeline.models import (
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    PipelineStats,
    QualityReport,
    ScopeGapResult,
)
from scope_pipeline.models_v2 import ProjectSession, TradeResultContainer, TradeRunRecord
from scope_pipeline.services.export_service import ExportService


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_classified_item(
    trade: str,
    drawing_name: str = "DWG-001",
    text: str = "Install conduit",
) -> ClassifiedItem:
    return ClassifiedItem(
        text=text,
        drawing_name=drawing_name,
        drawing_title="Electrical Plan",
        page=1,
        source_snippet="conduit run",
        confidence=0.9,
        trade=trade,
        csi_code="16050",
        csi_division="Division 16",
        classification_confidence=0.85,
        classification_reason="Matches electrical keywords",
    )


def _make_completeness_report() -> CompletenessReport:
    return CompletenessReport(
        drawing_coverage_pct=90.0,
        csi_coverage_pct=85.0,
        hallucination_count=0,
        overall_pct=87.5,
        missing_drawings=[],
        missing_csi_codes=[],
        hallucinated_items=[],
        is_complete=True,
        attempt=1,
    )


def _make_quality_report() -> QualityReport:
    return QualityReport(
        accuracy_score=0.95,
        corrections=[],
        validated_items=[],
        removed_items=[],
        summary="All items validated.",
    )


def _make_pipeline_stats() -> PipelineStats:
    return PipelineStats(
        total_ms=5000,
        attempts=1,
        tokens_used=2000,
        estimated_cost_usd=0.01,
        per_agent_timing={"extraction": 1000, "classification": 2000},
        records_processed=10,
        items_extracted=5,
    )


def _make_scope_gap_result(trade: str) -> ScopeGapResult:
    return ScopeGapResult(
        project_id=9999,
        project_name="Test Project",
        trade=trade,
        items=[_make_classified_item(trade)],
        ambiguities=[],
        gotchas=[],
        completeness=_make_completeness_report(),
        quality=_make_quality_report(),
        documents=DocumentSet(),
        pipeline_stats=_make_pipeline_stats(),
    )


def _make_session_with_trades(trade_names: list[str]) -> ProjectSession:
    """Build a ProjectSession populated with completed TradeResultContainers."""
    trade_results: dict[str, TradeResultContainer] = {}
    for trade in trade_names:
        result = _make_scope_gap_result(trade)
        record = TradeRunRecord(
            status="completed",
            items_count=len(result.items),
            completeness_pct=result.completeness.overall_pct,
            result=result,
            completed_at=datetime.now(timezone.utc),
        )
        container = TradeResultContainer(trade=trade)
        container = container.add_run(record)
        trade_results[trade.lower()] = container

    return ProjectSession(
        project_id=9999,
        project_name="Test Project",
        trade_results=trade_results,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExportService:

    def test_generate_combined_word_creates_file(self, tmp_path):
        """generate_combined_word should create a .docx file at the returned path."""
        session = _make_session_with_trades(["Electrical", "Plumbing"])
        service = ExportService(docs_dir=str(tmp_path))

        result_path = service.generate_combined_word(session)

        assert os.path.exists(result_path), "Expected file to exist on disk"
        assert result_path.endswith(".docx"), "File should have .docx extension"

    def test_generate_combined_word_filename_contains_project_id(self, tmp_path):
        """The generated filename should include the project_id."""
        session = _make_session_with_trades(["Electrical"])
        service = ExportService(docs_dir=str(tmp_path))

        result_path = service.generate_combined_word(session)

        assert "9999" in os.path.basename(result_path)

    def test_generate_combined_word_with_trade_filter(self, tmp_path):
        """Passing a trades list should not raise and should still produce a file."""
        session = _make_session_with_trades(["Electrical", "Plumbing", "HVAC"])
        service = ExportService(docs_dir=str(tmp_path))

        result_path = service.generate_combined_word(session, trades=["Electrical"])

        assert os.path.exists(result_path)
        assert result_path.endswith(".docx")

    def test_generate_combined_word_empty_session(self, tmp_path):
        """An empty session (no trades) should still produce a valid .docx."""
        session = ProjectSession(project_id=1, project_name="Empty Project")
        service = ExportService(docs_dir=str(tmp_path))

        result_path = service.generate_combined_word(session)

        assert os.path.exists(result_path)
        assert result_path.endswith(".docx")

    def test_docs_dir_created_if_missing(self, tmp_path):
        """ExportService should auto-create docs_dir when it does not exist."""
        new_dir = str(tmp_path / "auto_created_subdir")
        assert not os.path.exists(new_dir)

        ExportService(docs_dir=new_dir)

        assert os.path.isdir(new_dir)

    def test_generate_combined_word_two_trades(self, tmp_path):
        """Sanity check with exactly 2 trades — the primary acceptance criterion."""
        session = _make_session_with_trades(["Electrical", "Plumbing"])
        service = ExportService(docs_dir=str(tmp_path))

        result_path = service.generate_combined_word(session)

        assert os.path.exists(result_path)
        assert result_path.endswith(".docx")
        # File must be non-empty
        assert os.path.getsize(result_path) > 0
