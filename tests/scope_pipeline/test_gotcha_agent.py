"""tests/scope_pipeline/test_gotcha_agent.py"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import ScopeItem


MOCK_SCOPE_ITEMS = [
    ScopeItem(
        id="itm_abc",
        text="Install 200A panel board, 42-circuit",
        drawing_name="E-101",
        page=1,
        source_snippet="200A panel board, 42-circuit, surface mounted",
        confidence=0.95,
    ),
    ScopeItem(
        id="itm_def",
        text="Provide conduit and wiring for HVAC units",
        drawing_name="E-102",
        page=2,
        source_snippet="conduit and wiring for all rooftop HVAC units",
        confidence=0.90,
    ),
]

MOCK_LLM_RESPONSE = json.dumps([
    {
        "risk_type": "hidden_cost",
        "description": "Temporary power not explicitly scoped",
        "severity": "high",
        "affected_trades": ["Electrical", "General Trades"],
        "recommendation": "Add temporary power to Electrical scope",
        "drawing_refs": ["E-101"],
    },
    {
        "risk_type": "coordination",
        "description": "HVAC electrical connections require coordination with Mechanical",
        "severity": "medium",
        "affected_trades": ["Electrical", "Mechanical"],
        "recommendation": "Add coordination meeting requirement for HVAC electrical",
        "drawing_refs": ["E-102"],
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
async def test_gotcha_agent_parses_risks():
    from scope_pipeline.agents.gotcha_agent import GotchaAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = GotchaAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_LLM_RESPONSE)
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter, trade="Electrical")
    items = result.data

    assert len(items) == 2
    assert items[0].risk_type == "hidden_cost"
    assert items[0].description == "Temporary power not explicitly scoped"
    assert items[0].severity == "high"
    assert items[0].affected_trades == ["Electrical", "General Trades"]
    assert items[0].recommendation == "Add temporary power to Electrical scope"
    assert items[0].drawing_refs == ["E-101"]

    assert items[1].risk_type == "coordination"
    assert items[1].severity == "medium"


@pytest.mark.asyncio
async def test_gotcha_agent_returns_empty_when_no_risks():
    from scope_pipeline.agents.gotcha_agent import GotchaAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = GotchaAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response("[]")
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter, trade="Electrical")
    assert result.data == []


@pytest.mark.asyncio
async def test_gotcha_agent_handles_markdown_fenced_json():
    from scope_pipeline.agents.gotcha_agent import GotchaAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = GotchaAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    fenced = f"```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(fenced)
    )
    agent._client = mock_client

    result = await agent.run(MOCK_SCOPE_ITEMS, emitter, trade="Electrical")
    assert len(result.data) == 2
    assert result.data[0].risk_type == "hidden_cost"
