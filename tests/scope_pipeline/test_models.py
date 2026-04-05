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
    assert item.id
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
