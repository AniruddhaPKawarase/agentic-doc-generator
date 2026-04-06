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
