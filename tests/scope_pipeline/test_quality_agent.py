"""tests/scope_pipeline/test_quality_agent.py — Agent 6: Quality review."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import (
    ClassifiedItem,
    MergedResults,
    QualityCorrection,
    ScopeItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_classified_items() -> list[ClassifiedItem]:
    return [
        ClassifiedItem(
            id="itm_abc",
            text="Install 200A panel board",
            drawing_name="E-103",
            page=3,
            source_snippet="200A panel board, 42-circuit",
            confidence=0.95,
            trade="Electrical",
            csi_code="26 00 00",
            csi_division="Electrical",
            classification_confidence=0.90,
            classification_reason="Electrical panel installation",
        ),
        ClassifiedItem(
            id="itm_def",
            text="Furnish conduit runs",
            drawing_name="E-103",
            page=3,
            source_snippet="EMT conduit runs per plan",
            confidence=0.88,
            trade="Electrical",
            csi_code="26 05 33",
            csi_division="Electrical",
            classification_confidence=0.85,
            classification_reason="Conduit and raceways",
        ),
        ClassifiedItem(
            id="itm_hallucinated",
            text="Phantom item not in drawings",
            drawing_name="E-999",
            page=1,
            source_snippet="does not exist",
            confidence=0.30,
            trade="Electrical",
            csi_code="26 00 00",
            csi_division="Electrical",
            classification_confidence=0.40,
            classification_reason="Uncertain",
        ),
    ]


def _make_merged_results() -> MergedResults:
    items = _make_classified_items()
    return MergedResults(
        items=[ScopeItem(text=i.text, drawing_name=i.drawing_name) for i in items],
        classified_items=items,
        ambiguities=[],
        gotchas=[],
    )


MOCK_QUALITY_RESPONSE = json.dumps({
    "accuracy_score": 0.97,
    "corrections": [
        {
            "item_id": "itm_abc",
            "field": "csi_code",
            "old_value": "26 00 00",
            "new_value": "26 24 16",
            "reason": "More specific CSI",
        }
    ],
    "removed_item_ids": ["itm_hallucinated"],
    "summary": "97% accuracy. 1 CSI correction. 1 hallucinated item removed.",
})


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 3000
    mock_resp.usage.completion_tokens = 300
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quality_agent_parses_corrections():
    """QA agent parses LLM response, applies corrections, removes hallucinated items."""
    from scope_pipeline.agents.quality_agent import QualityAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = QualityAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_QUALITY_RESPONSE)
    )
    agent._client = mock_client

    merged = _make_merged_results()
    result = await agent.run(merged, emitter)
    report = result.data

    # Accuracy parsed correctly
    assert report.accuracy_score == 0.97

    # One correction found
    assert len(report.corrections) == 1
    assert report.corrections[0].item_id == "itm_abc"
    assert report.corrections[0].new_value == "26 24 16"

    # Hallucinated item removed
    assert "itm_hallucinated" in report.removed_items

    # Validated items exclude removed ones
    assert "itm_hallucinated" not in report.validated_items
    assert "itm_abc" in report.validated_items
    assert "itm_def" in report.validated_items

    # Summary present
    assert "97%" in report.summary


@pytest.mark.asyncio
async def test_quality_agent_returns_default_on_invalid_response():
    """QA agent returns high-accuracy default report when LLM returns garbage."""
    from scope_pipeline.agents.quality_agent import QualityAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = QualityAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response("This is not valid JSON at all")
    )
    agent._client = mock_client

    merged = _make_merged_results()
    result = await agent.run(merged, emitter)
    report = result.data

    # Parse failure: flag for manual review with 0.0 accuracy (not a false 1.0)
    assert report.accuracy_score == 0.0
    assert report.corrections == []
    assert report.removed_items == []
    assert len(report.validated_items) == 3  # items preserved for manual review
    assert "manual review" in report.summary.lower()
