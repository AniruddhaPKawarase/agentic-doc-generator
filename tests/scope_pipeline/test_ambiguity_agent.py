"""tests/scope_pipeline/test_ambiguity_agent.py"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import ScopeItem


MOCK_SCOPE_ITEMS = [
    ScopeItem(
        id="itm_abc",
        text="Flashing and waterproofing at roof penetrations",
        drawing_name="A-201",
        page=2,
        source_snippet="flashing and waterproofing at all roof penetrations",
        confidence=0.90,
    ),
    ScopeItem(
        id="itm_def",
        text="Fire stopping at all wall penetrations",
        drawing_name="A-301",
        page=5,
        source_snippet="fire stopping at all wall penetrations per code",
        confidence=0.85,
    ),
]

MOCK_LLM_RESPONSE = json.dumps([
    {
        "scope_text": "Flashing and waterproofing at roof penetrations",
        "competing_trades": ["Roofing", "Sheet Metal"],
        "severity": "high",
        "recommendation": "Assign to Roofing per CSI 07 62 00",
        "source_items": ["itm_abc"],
        "drawing_refs": ["A-201"],
    },
    {
        "scope_text": "Fire stopping at all wall penetrations",
        "competing_trades": ["Fire Protection", "General Trades"],
        "severity": "medium",
        "recommendation": "Assign to Fire Protection per CSI 07 84 00",
        "source_items": ["itm_def"],
        "drawing_refs": ["A-301"],
    },
])


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 3000
    mock_resp.usage.completion_tokens = 400
    return mock_resp


@pytest.mark.asyncio
async def test_ambiguity_agent_parses_ambiguities():
    from scope_pipeline.agents.ambiguity_agent import AmbiguityAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = AmbiguityAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_LLM_RESPONSE)
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter)
    items = result.data

    assert len(items) == 2
    assert items[0].scope_text == "Flashing and waterproofing at roof penetrations"
    assert items[0].competing_trades == ["Roofing", "Sheet Metal"]
    assert items[0].severity == "high"
    assert items[0].recommendation == "Assign to Roofing per CSI 07 62 00"
    assert items[0].drawing_refs == ["A-201"]

    assert items[1].severity == "medium"
    assert items[1].competing_trades == ["Fire Protection", "General Trades"]


@pytest.mark.asyncio
async def test_ambiguity_agent_returns_empty_when_no_ambiguities():
    from scope_pipeline.agents.ambiguity_agent import AmbiguityAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = AmbiguityAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response("[]")
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter)
    assert result.data == []


@pytest.mark.asyncio
async def test_ambiguity_agent_handles_markdown_fenced_json():
    from scope_pipeline.agents.ambiguity_agent import AmbiguityAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = AmbiguityAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    fenced = f"```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(fenced)
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter)
    assert len(result.data) == 2
    assert result.data[0].scope_text == "Flashing and waterproofing at roof penetrations"
