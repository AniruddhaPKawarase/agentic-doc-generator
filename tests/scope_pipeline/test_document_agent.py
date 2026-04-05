"""tests/scope_pipeline/test_document_agent.py — Agent 7: Document generation."""

import csv
import json
import os
import tempfile

import pytest

from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    GotchaItem,
    PipelineStats,
    QualityReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_items() -> list[ClassifiedItem]:
    return [
        ClassifiedItem(
            id="itm_001",
            text="Install 200A panel board",
            drawing_name="E-103",
            drawing_title="Power Plan",
            page=3,
            source_snippet="200A panel board, 42-circuit",
            confidence=0.95,
            trade="Electrical",
            csi_code="26 24 16",
            csi_division="Electrical",
            classification_confidence=0.90,
            classification_reason="Panel installation",
        ),
        ClassifiedItem(
            id="itm_002",
            text="Furnish conduit runs",
            drawing_name="E-104",
            drawing_title="Lighting Plan",
            page=5,
            source_snippet="EMT conduit runs per plan",
            confidence=0.88,
            trade="Electrical",
            csi_code="26 05 33",
            csi_division="Electrical",
            classification_confidence=0.85,
            classification_reason="Conduit and raceways",
        ),
    ]


def _make_ambiguities() -> list[AmbiguityItem]:
    return [
        AmbiguityItem(
            scope_text="Fire alarm wiring",
            competing_trades=["Electrical", "Fire Protection"],
            severity="medium",
            recommendation="Clarify in bid",
            source_items=["itm_001"],
            drawing_refs=["E-103"],
        ),
    ]


def _make_gotchas() -> list[GotchaItem]:
    return [
        GotchaItem(
            risk_type="hidden_cost",
            description="Temporary power during construction",
            severity="high",
            affected_trades=["Electrical"],
            recommendation="Budget for temp power setup",
            drawing_refs=["E-103"],
        ),
    ]


def _make_completeness() -> CompletenessReport:
    return CompletenessReport(
        drawing_coverage_pct=95.0,
        csi_coverage_pct=90.0,
        hallucination_count=0,
        overall_pct=92.5,
        missing_drawings=["E-110"],
        missing_csi_codes=["26 51 00"],
        hallucinated_items=[],
        is_complete=True,
        attempt=1,
    )


def _make_quality() -> QualityReport:
    return QualityReport(
        accuracy_score=0.97,
        corrections=[],
        validated_items=["itm_001", "itm_002"],
        removed_items=[],
        summary="97% accuracy. No corrections needed.",
    )


def _make_stats() -> PipelineStats:
    return PipelineStats(
        total_ms=12000,
        attempts=1,
        tokens_used=15000,
        estimated_cost_usd=0.03,
        per_agent_timing={"extraction": 3000, "classification": 2000},
        records_processed=10,
        items_extracted=2,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_word_document():
    """Word document is created and exists on disk."""
    from scope_pipeline.services.document_agent import DocumentAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DocumentAgent(docs_dir=tmpdir)
        doc_set = await agent.generate_all(
            items=_make_items(),
            ambiguities=_make_ambiguities(),
            gotchas=_make_gotchas(),
            completeness=_make_completeness(),
            quality=_make_quality(),
            project_id=7166,
            project_name="Granville Hotel",
            trade="Electrical",
            stats=_make_stats(),
        )

        assert doc_set.word_path is not None
        assert os.path.exists(doc_set.word_path)
        assert doc_set.word_path.endswith(".docx")


@pytest.mark.asyncio
async def test_generate_csv():
    """CSV file is created with correct header row."""
    from scope_pipeline.services.document_agent import DocumentAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DocumentAgent(docs_dir=tmpdir)
        doc_set = await agent.generate_all(
            items=_make_items(),
            ambiguities=_make_ambiguities(),
            gotchas=_make_gotchas(),
            completeness=_make_completeness(),
            quality=_make_quality(),
            project_id=7166,
            project_name="Granville Hotel",
            trade="Electrical",
            stats=_make_stats(),
        )

        assert doc_set.csv_path is not None
        assert os.path.exists(doc_set.csv_path)

        with open(doc_set.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "Trade" in header
            assert "CSI Code" in header
            assert "Scope Item" in header
            assert "Drawing" in header
            assert "Confidence" in header

            # At least 2 data rows
            rows = list(reader)
            assert len(rows) == 2


@pytest.mark.asyncio
async def test_generate_json():
    """JSON file is created with correct structure."""
    from scope_pipeline.services.document_agent import DocumentAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        agent = DocumentAgent(docs_dir=tmpdir)
        doc_set = await agent.generate_all(
            items=_make_items(),
            ambiguities=_make_ambiguities(),
            gotchas=_make_gotchas(),
            completeness=_make_completeness(),
            quality=_make_quality(),
            project_id=7166,
            project_name="Granville Hotel",
            trade="Electrical",
            stats=_make_stats(),
        )

        assert doc_set.json_path is not None
        assert os.path.exists(doc_set.json_path)

        with open(doc_set.json_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["project_id"] == 7166
        assert data["project_name"] == "Granville Hotel"
        assert data["trade"] == "Electrical"
        assert len(data["items"]) == 2
        assert len(data["ambiguities"]) == 1
        assert len(data["gotchas"]) == 1
        assert "completeness" in data
        assert "quality" in data
