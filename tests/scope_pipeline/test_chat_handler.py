"""tests/scope_pipeline/test_chat_handler.py — Chat Handler tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import (
    DocumentSet,
    ScopeGapSession,
    ScopeGapResult,
    CompletenessReport,
    QualityReport,
    PipelineStats,
)


def _make_result() -> ScopeGapResult:
    """Minimal ScopeGapResult for chat context."""
    return ScopeGapResult(
        project_id=7166,
        project_name="Test Project",
        trade="Electrical",
        items=[],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100,
            csi_coverage_pct=100,
            hallucination_count=0,
            overall_pct=100,
            missing_drawings=[],
            missing_csi_codes=[],
            hallucinated_items=[],
            is_complete=True,
            attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=1.0,
            corrections=[],
            validated_items=[],
            removed_items=[],
            summary="ok",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=500,
            attempts=1,
            tokens_used=1000,
            estimated_cost_usd=0.01,
            per_agent_timing={},
            records_processed=10,
            items_extracted=5,
        ),
    )


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 200
    mock_resp.usage.completion_tokens = 100
    return mock_resp


@pytest.mark.asyncio
async def test_chat_returns_answer():
    """Chat handler returns an answer when session has a latest_result."""
    from scope_pipeline.services.chat_handler import ScopeGapChatHandler

    handler = ScopeGapChatHandler(api_key="test-key", model="gpt-4.1")

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response("The report covers 5 items for Electrical trade.")
    )
    handler._client = mock_client

    session = ScopeGapSession(project_id=7166, trade="Electrical")
    session.latest_result = _make_result()

    result = await handler.handle(session, "How many items were found?")

    assert "answer" in result
    assert result["answer"] == "The report covers 5 items for Electrical trade."
    # Message history should be updated
    assert len(session.messages) == 2  # user + assistant
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"


@pytest.mark.asyncio
async def test_chat_no_result_returns_error():
    """Chat handler returns error when session has no latest_result."""
    from scope_pipeline.services.chat_handler import ScopeGapChatHandler

    handler = ScopeGapChatHandler(api_key="test-key", model="gpt-4.1")

    session = ScopeGapSession(project_id=7166, trade="Electrical")
    session.latest_result = None

    result = await handler.handle(session, "What items were found?")

    assert "answer" in result
    assert "error" in result["answer"].lower() or "no" in result["answer"].lower()
