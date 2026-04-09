"""tests/scope_pipeline/test_completeness_v2.py — Trade-filtered CSI and new weights."""

import pytest

from scope_pipeline.agents.completeness_agent import (
    TRADE_CSI_PREFIX,
    CompletenessAgent,
    _filter_csi_for_trade,
)
from scope_pipeline.models import ClassifiedItem, MergedResults, ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter


# ---------------------------------------------------------------------------
# TRADE_CSI_PREFIX mapping tests
# ---------------------------------------------------------------------------

class TestTradeCsiPrefix:
    def test_concrete_mapped_to_03(self):
        assert TRADE_CSI_PREFIX["Concrete"] == ["03"]

    def test_electrical_mapped_to_26_27(self):
        assert TRADE_CSI_PREFIX["Electrical"] == ["26", "27"]

    def test_sitework_has_multiple_prefixes(self):
        assert TRADE_CSI_PREFIX["Sitework"] == ["31", "32", "33"]

    def test_all_values_are_two_digit_strings(self):
        for trade, prefixes in TRADE_CSI_PREFIX.items():
            for prefix in prefixes:
                assert len(prefix) == 2, f"{trade} has non-2-digit prefix: {prefix}"
                assert prefix.isdigit(), f"{trade} has non-numeric prefix: {prefix}"


# ---------------------------------------------------------------------------
# _filter_csi_for_trade unit tests
# ---------------------------------------------------------------------------

class TestFilterCsiForTrade:
    def test_empty_trade_returns_all(self):
        source = {"03 30 00", "26 05 00", "22 10 00"}
        result = _filter_csi_for_trade(source, "")
        assert result == source

    def test_unknown_trade_returns_all(self):
        source = {"03 30 00", "26 05 00"}
        result = _filter_csi_for_trade(source, "UnknownTrade")
        assert result == source

    def test_concrete_filters_to_03_only(self):
        source = {"03 30 00", "03 11 00", "26 05 00", "22 10 00"}
        result = _filter_csi_for_trade(source, "Concrete")
        assert result == {"03 30 00", "03 11 00"}

    def test_electrical_keeps_26_and_27(self):
        source = {"26 05 00", "27 10 00", "03 30 00"}
        result = _filter_csi_for_trade(source, "Electrical")
        assert result == {"26 05 00", "27 10 00"}

    def test_no_matching_codes_returns_empty(self):
        source = {"26 05 00", "22 10 00"}
        result = _filter_csi_for_trade(source, "Concrete")
        assert result == set()

    def test_returns_new_set_not_mutating_input(self):
        source = {"03 30 00", "26 05 00"}
        original = set(source)
        _ = _filter_csi_for_trade(source, "Concrete")
        assert source == original


# ---------------------------------------------------------------------------
# New weights integration tests
# ---------------------------------------------------------------------------

def _make_merged(
    drawing_names: list[str],
    csi_codes: list[str],
    trade: str = "Electrical",
) -> MergedResults:
    """Build a MergedResults with the given drawings and CSI codes."""
    items = [
        ScopeItem(
            text=f"item for {d}",
            drawing_name=d,
            page=1,
            source_snippet="snippet",
        )
        for d in drawing_names
    ]
    classified = [
        ClassifiedItem(
            text=f"classified {c}",
            drawing_name=drawing_names[i % len(drawing_names)] if drawing_names else "X-000",
            page=1,
            source_snippet="snippet",
            trade=trade,
            csi_code=c,
            csi_division=f"{c[:2]} - {trade}",
            classification_confidence=0.9,
            classification_reason="test",
        )
        for i, c in enumerate(csi_codes)
    ]
    return MergedResults(items=items, classified_items=classified)


class TestNewWeights:
    @pytest.mark.asyncio
    async def test_perfect_score_uses_new_weights(self):
        """100% on all dimensions should still yield 100.0 overall."""
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        merged = _make_merged(
            drawing_names=["E-101", "E-102"],
            csi_codes=["26 05 00", "26 24 16"],
            trade="Electrical",
        )

        result = await agent.run(
            merged, emitter,
            source_drawings={"E-101", "E-102"},
            source_csi={"26 05 00", "26 24 16"},
            trade="Electrical",
            attempt=1,
            threshold=95.0,
        )

        report = result.data
        assert report.drawing_coverage_pct == 100.0
        assert report.csi_coverage_pct == 100.0
        assert report.overall_pct == 100.0
        assert report.is_complete is True

    @pytest.mark.asyncio
    async def test_weights_are_065_015_020(self):
        """Verify the exact weighted formula: 0.65 * drawing + 0.15 * csi + 0.2 * no_hallucination.

        Scenario: 50% drawings, 100% CSI, 100% no-hallucination
        Expected: 50*0.65 + 100*0.15 + 100*0.2 = 32.5 + 15 + 20 = 67.5
        """
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        merged = _make_merged(
            drawing_names=["E-101"],
            csi_codes=["26 05 00"],
            trade="Electrical",
        )

        result = await agent.run(
            merged, emitter,
            source_drawings={"E-101", "E-102"},
            source_csi={"26 05 00"},
            trade="Electrical",
            attempt=1,
            threshold=95.0,
        )

        report = result.data
        assert report.drawing_coverage_pct == 50.0
        assert report.csi_coverage_pct == 100.0
        assert report.overall_pct == pytest.approx(67.5, abs=0.1)
        assert report.is_complete is False

    @pytest.mark.asyncio
    async def test_trade_filters_irrelevant_csi(self):
        """Concrete trade should ignore electrical CSI codes in coverage calc.

        source_csi has concrete ("03 30 00") and electrical ("26 05 00").
        With trade="Concrete", only "03 30 00" is relevant.
        Extracted CSI has "03 30 00" -> 100% CSI coverage.
        """
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        merged = _make_merged(
            drawing_names=["S-101"],
            csi_codes=["03 30 00"],
            trade="Concrete",
        )

        result = await agent.run(
            merged, emitter,
            source_drawings={"S-101"},
            source_csi={"03 30 00", "26 05 00"},
            trade="Concrete",
            attempt=1,
            threshold=95.0,
        )

        report = result.data
        # Only "03 30 00" is relevant for Concrete; "26 05 00" is ignored
        assert report.csi_coverage_pct == 100.0
        # Missing CSI should only list relevant codes that are missing
        assert "26 05 00" not in report.missing_csi_codes

    @pytest.mark.asyncio
    async def test_no_trade_uses_all_csi(self):
        """Without a trade kwarg, all source CSI codes are used."""
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        merged = _make_merged(
            drawing_names=["S-101"],
            csi_codes=["03 30 00"],
            trade="Concrete",
        )

        result = await agent.run(
            merged, emitter,
            source_drawings={"S-101"},
            source_csi={"03 30 00", "26 05 00"},
            # No trade kwarg
            attempt=1,
            threshold=95.0,
        )

        report = result.data
        # Without trade filter, 1 of 2 CSI matched = 50%
        assert report.csi_coverage_pct == 50.0

    @pytest.mark.asyncio
    async def test_trade_with_no_relevant_csi_gives_100(self):
        """If trade filter removes all source CSI, score defaults to 100%."""
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        merged = _make_merged(
            drawing_names=["S-101"],
            csi_codes=["26 05 00"],
            trade="Electrical",
        )

        result = await agent.run(
            merged, emitter,
            source_drawings={"S-101"},
            source_csi={"03 30 00"},  # No electrical codes in source
            trade="Electrical",
            attempt=1,
            threshold=95.0,
        )

        report = result.data
        # relevant_csi is empty -> defaults to 100%
        assert report.csi_coverage_pct == 100.0
