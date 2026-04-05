"""tests/scope_pipeline/test_extraction_agent.py"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock


MOCK_LLM_RESPONSE = json.dumps([
    {
        "text": "Install 200A panel board, 42-circuit",
        "drawing_name": "E-103",
        "page": 3,
        "source_snippet": "200A panel board, 42-circuit, surface mounted",
        "confidence": 0.95,
        "csi_hint": "26 24 16"
    },
    {
        "text": "Furnish VRF-CU-C02 electrical connection",
        "drawing_name": "E-103",
        "page": 3,
        "source_snippet": "VRF-CU-C02, 5-ton outdoor unit, provide 208V",
        "confidence": 0.88,
        "csi_hint": "26 05 19"
    },
])


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 5000
    mock_resp.usage.completion_tokens = 500
    return mock_resp


@pytest.mark.asyncio
async def test_extraction_agent_parses_llm_json():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_LLM_RESPONSE)
    )
    agent._client = mock_client

    input_data = {
        "drawing_records": [
            {"drawing_name": "E-103", "drawing_title": "Power Plan", "text": "200A panel board, 42-circuit, surface mounted. VRF-CU-C02, 5-ton outdoor unit, provide 208V."},
        ],
        "trade": "Electrical",
        "drawing_list": ["E-103"],
    }

    result = await agent.run(input_data, emitter)
    items = result.data

    assert len(items) == 2
    assert items[0].text == "Install 200A panel board, 42-circuit"
    assert items[0].drawing_name == "E-103"
    assert items[0].source_snippet == "200A panel board, 42-circuit, surface mounted"
    assert items[0].confidence == 0.95


@pytest.mark.asyncio
async def test_extraction_agent_handles_markdown_fenced_json():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    fenced = f"```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(fenced)
    )
    agent._client = mock_client

    result = await agent.run(
        {"drawing_records": [], "trade": "Electrical", "drawing_list": []},
        emitter,
    )
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_extraction_agent_returns_empty_on_invalid_json():
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response("This is not JSON at all")
    )
    agent._client = mock_client

    result = await agent.run(
        {"drawing_records": [], "trade": "Electrical", "drawing_list": []},
        emitter,
    )
    assert result.data == []
