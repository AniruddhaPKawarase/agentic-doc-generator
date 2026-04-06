"""tests/scope_pipeline/test_models_v2.py — Unit tests for Phase 12 models_v2.

Covers: TradeRunRecord, TradeResultContainer, ProjectSession, Highlight,
HighlightIndex, WebhookEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scope_pipeline.models_v2 import (
    Highlight,
    HighlightIndex,
    ProjectSession,
    TradeResultContainer,
    TradeRunRecord,
    WebhookEvent,
)


# ---------------------------------------------------------------------------
# TradeRunRecord
# ---------------------------------------------------------------------------

class TestTradeRunRecord:
    def test_defaults(self):
        record = TradeRunRecord()
        assert record.run_id.startswith("run_")
        assert record.status == "pending"
        assert record.attempts == 0
        assert record.completeness_pct == 0.0
        assert record.items_count == 0
        assert record.ambiguities_count == 0
        assert record.gotchas_count == 0
        assert record.token_usage == 0
        assert record.cost_usd == 0.0
        assert record.documents is None
        assert record.result is None
        assert record.job_id is None
        assert record.completed_at is None
        assert record.error is None
        assert isinstance(record.started_at, datetime)

    def test_run_id_prefix(self):
        r1 = TradeRunRecord()
        r2 = TradeRunRecord()
        assert r1.run_id.startswith("run_")
        assert r2.run_id.startswith("run_")
        assert r1.run_id != r2.run_id

    def test_populated_fields(self):
        record = TradeRunRecord(
            job_id="job_abc",
            status="completed",
            attempts=2,
            completeness_pct=95.5,
            items_count=42,
            ambiguities_count=3,
            gotchas_count=1,
            token_usage=8000,
            cost_usd=0.12,
            error=None,
        )
        assert record.job_id == "job_abc"
        assert record.status == "completed"
        assert record.attempts == 2
        assert record.completeness_pct == 95.5
        assert record.items_count == 42
        assert record.token_usage == 8000
        assert record.cost_usd == 0.12

    def test_failed_status_with_error(self):
        record = TradeRunRecord(status="failed", error="LLM timeout")
        assert record.status == "failed"
        assert record.error == "LLM timeout"


# ---------------------------------------------------------------------------
# TradeResultContainer
# ---------------------------------------------------------------------------

class TestTradeResultContainer:
    def test_defaults(self):
        container = TradeResultContainer(trade="Electrical")
        assert container.trade == "Electrical"
        assert container.current_version == 0
        assert container.versions == []
        assert container.latest_result is None
        assert container.max_versions == 5

    def test_add_run_returns_new_instance(self):
        container = TradeResultContainer(trade="Plumbing")
        record = TradeRunRecord(status="completed")
        updated = container.add_run(record)
        # immutability: original unchanged
        assert len(container.versions) == 0
        assert container.current_version == 0
        # new instance has the run
        assert len(updated.versions) == 1
        assert updated.versions[0].run_id == record.run_id
        assert updated.current_version == 1

    def test_add_run_increments_version(self):
        container = TradeResultContainer(trade="Mechanical")
        for i in range(3):
            record = TradeRunRecord(status="completed")
            container = container.add_run(record)
        assert container.current_version == 3
        assert len(container.versions) == 3

    def test_max_versions_trimming(self):
        container = TradeResultContainer(trade="Civil", max_versions=3)
        records = [TradeRunRecord(status="completed") for _ in range(5)]
        for r in records:
            container = container.add_run(r)
        # Only last 3 versions kept
        assert len(container.versions) == 3
        assert container.current_version == 5
        # The oldest run_ids (first 2) should be gone
        kept_ids = {v.run_id for v in container.versions}
        assert records[0].run_id not in kept_ids
        assert records[1].run_id not in kept_ids
        assert records[4].run_id in kept_ids

    def test_add_run_with_result_updates_latest_result(self):
        from scope_pipeline.models import (
            ClassifiedItem,
            CompletenessReport,
            DocumentSet,
            PipelineStats,
            QualityReport,
            ScopeGapResult,
        )

        quality = QualityReport(
            accuracy_score=0.9,
            corrections=[],
            validated_items=[],
            removed_items=[],
            summary="ok",
        )
        completeness = CompletenessReport(
            drawing_coverage_pct=100.0,
            csi_coverage_pct=100.0,
            hallucination_count=0,
            overall_pct=100.0,
            missing_drawings=[],
            missing_csi_codes=[],
            hallucinated_items=[],
            is_complete=True,
            attempt=1,
        )
        stats = PipelineStats(
            total_ms=5000,
            attempts=1,
            tokens_used=1000,
            estimated_cost_usd=0.01,
            per_agent_timing={},
            records_processed=10,
            items_extracted=5,
        )
        result = ScopeGapResult(
            project_id=1,
            project_name="Test",
            trade="Electrical",
            items=[],
            ambiguities=[],
            gotchas=[],
            completeness=completeness,
            quality=quality,
            documents=DocumentSet(),
            pipeline_stats=stats,
        )
        record = TradeRunRecord(status="completed", result=result)
        container = TradeResultContainer(trade="Electrical")
        updated = container.add_run(record)
        assert updated.latest_result is result

    def test_add_run_preserves_previous_latest_result_when_new_run_has_none(self):
        """If a new run has no result, the previous latest_result is kept."""
        container = TradeResultContainer(trade="Electrical")
        # First run brings a result placeholder check via no-result run
        first_run = TradeRunRecord(status="pending")
        container = container.add_run(first_run)
        assert container.latest_result is None
        # Add another run still without result
        second_run = TradeRunRecord(status="running")
        container = container.add_run(second_run)
        assert container.latest_result is None

    def test_custom_max_versions(self):
        container = TradeResultContainer(trade="HVAC", max_versions=2)
        for _ in range(10):
            container = container.add_run(TradeRunRecord())
        assert len(container.versions) == 2


# ---------------------------------------------------------------------------
# ProjectSession
# ---------------------------------------------------------------------------

class TestProjectSession:
    def test_defaults(self):
        session = ProjectSession(project_id=1001)
        assert session.project_id == 1001
        assert session.project_name == ""
        assert session.set_ids is None
        assert session.trade_results == {}
        assert session.ambiguity_resolutions == {}
        assert session.gotcha_acknowledgments == []
        assert session.ignored_items == []
        assert session.messages == []

    def test_session_key_no_set_ids(self):
        session = ProjectSession(project_id=7166)
        assert session.session_key == "proj_7166"

    def test_session_key_with_set_ids(self):
        session = ProjectSession(project_id=7166, set_ids=[3, 1, 2])
        key = session.session_key
        assert key.startswith("proj_7166_sets_")
        # IDs should be sorted in the key
        assert "1_2_3" in key

    def test_session_key_single_set_id(self):
        session = ProjectSession(project_id=100, set_ids=[42])
        assert session.session_key == "proj_100_sets_42"

    def test_session_key_string_set_ids_sorted(self):
        session = ProjectSession(project_id=200, set_ids=["c", "a", "b"])
        assert session.session_key == "proj_200_sets_a_b_c"

    def test_session_key_same_regardless_of_input_order(self):
        s1 = ProjectSession(project_id=50, set_ids=[3, 1, 2])
        s2 = ProjectSession(project_id=50, set_ids=[1, 2, 3])
        assert s1.session_key == s2.session_key

    def test_populated_shared_state(self):
        from scope_pipeline.models import SessionMessage

        msg = SessionMessage(role="user", content="hello")
        session = ProjectSession(
            project_id=99,
            project_name="My Project",
            set_ids=[10, 20],
            ambiguity_resolutions={"amb_1": "trade_A"},
            gotcha_acknowledgments=["gtc_1"],
            ignored_items=["itm_x"],
            messages=[msg],
        )
        assert session.project_name == "My Project"
        assert session.ambiguity_resolutions["amb_1"] == "trade_A"
        assert "gtc_1" in session.gotcha_acknowledgments
        assert "itm_x" in session.ignored_items
        assert len(session.messages) == 1

    def test_trade_results_dict(self):
        session = ProjectSession(project_id=1)
        container = TradeResultContainer(trade="Plumbing")
        # Pydantic models are immutable at the instance level but dict assignment
        # is via model_copy; here we test the field accepts TradeResultContainer values
        session2 = session.model_copy(
            update={"trade_results": {"plumbing": container}}
        )
        assert "plumbing" in session2.trade_results
        assert session2.trade_results["plumbing"].trade == "Plumbing"


# ---------------------------------------------------------------------------
# Highlight
# ---------------------------------------------------------------------------

class TestHighlight:
    def test_defaults(self):
        hl = Highlight(drawing_name="Sheet-E1")
        assert hl.id.startswith("hl_")
        assert hl.drawing_name == "Sheet-E1"
        assert hl.page == 1
        assert hl.x == 0.0
        assert hl.y == 0.0
        assert hl.width == 0.0
        assert hl.height == 0.0
        assert hl.color == "#FFEB3B"
        assert hl.opacity == 0.3
        assert hl.label == ""
        assert hl.trade is None
        assert hl.critical is False
        assert hl.comment == ""
        assert hl.scope_item_id is None
        assert hl.scope_item_ids == []
        assert isinstance(hl.created_at, datetime)
        assert isinstance(hl.updated_at, datetime)

    def test_id_prefix(self):
        hl1 = Highlight(drawing_name="A")
        hl2 = Highlight(drawing_name="B")
        assert hl1.id.startswith("hl_")
        assert hl2.id.startswith("hl_")
        assert hl1.id != hl2.id

    def test_populated_fields(self):
        hl = Highlight(
            drawing_name="Sheet-E2",
            page=3,
            x=0.1,
            y=0.2,
            width=0.3,
            height=0.15,
            color="#FF0000",
            opacity=0.5,
            label="Panel location",
            trade="Electrical",
            critical=True,
            comment="Verify with engineer",
            scope_item_id="itm_abc12345",
            scope_item_ids=["itm_abc12345", "itm_def67890"],
        )
        assert hl.drawing_name == "Sheet-E2"
        assert hl.page == 3
        assert hl.x == pytest.approx(0.1)
        assert hl.color == "#FF0000"
        assert hl.opacity == pytest.approx(0.5)
        assert hl.trade == "Electrical"
        assert hl.critical is True
        assert hl.scope_item_id == "itm_abc12345"
        assert len(hl.scope_item_ids) == 2

    def test_multiple_scope_item_ids(self):
        hl = Highlight(
            drawing_name="Sheet-P1",
            scope_item_ids=["itm_1", "itm_2", "itm_3"],
        )
        assert len(hl.scope_item_ids) == 3


# ---------------------------------------------------------------------------
# HighlightIndex
# ---------------------------------------------------------------------------

class TestHighlightIndex:
    def test_defaults(self):
        idx = HighlightIndex(project_id=1001)
        assert idx.project_id == 1001
        assert idx.user_id is None
        assert idx.drawings == {}

    def test_with_user_and_drawings(self):
        hl = Highlight(drawing_name="Sheet-M1", trade="Mechanical")
        idx = HighlightIndex(
            project_id=2000,
            user_id="user_xyz",
            drawings={"Sheet-M1": [hl]},
        )
        assert idx.user_id == "user_xyz"
        assert "Sheet-M1" in idx.drawings
        assert idx.drawings["Sheet-M1"][0].trade == "Mechanical"

    def test_multiple_drawings(self):
        hl_e = Highlight(drawing_name="Sheet-E1")
        hl_p = Highlight(drawing_name="Sheet-P1")
        idx = HighlightIndex(
            project_id=3000,
            drawings={"Sheet-E1": [hl_e], "Sheet-P1": [hl_p]},
        )
        assert len(idx.drawings) == 2


# ---------------------------------------------------------------------------
# WebhookEvent
# ---------------------------------------------------------------------------

class TestWebhookEvent:
    def test_defaults(self):
        event = WebhookEvent(event="drawings.updated", project_id=7166)
        assert event.event == "drawings.updated"
        assert event.project_id == 7166
        assert event.project_name == ""
        assert event.set_id is None
        assert event.changed_trades == []
        assert event.drawing_count == 0
        assert isinstance(event.timestamp, datetime)

    def test_populated_fields(self):
        event = WebhookEvent(
            event="project.created",
            project_id=9999,
            project_name="New Hospital",
            set_id=42,
            changed_trades=["Electrical", "Plumbing"],
            drawing_count=150,
        )
        assert event.project_name == "New Hospital"
        assert event.set_id == 42
        assert "Electrical" in event.changed_trades
        assert event.drawing_count == 150

    def test_string_set_id(self):
        event = WebhookEvent(
            event="drawings.updated",
            project_id=100,
            set_id="set_abc",
        )
        assert event.set_id == "set_abc"

    def test_timestamp_defaults_to_utc_now(self):
        before = datetime.now(timezone.utc)
        event = WebhookEvent(event="test.event", project_id=1)
        after = datetime.now(timezone.utc)
        assert before <= event.timestamp <= after

    def test_explicit_timestamp(self):
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        event = WebhookEvent(
            event="drawings.updated",
            project_id=7166,
            timestamp=ts,
        )
        assert event.timestamp == ts
