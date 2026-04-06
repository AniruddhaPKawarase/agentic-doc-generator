"""tests/scope_pipeline/test_classification_agent.py"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import ScopeItem


MOCK_SCOPE_ITEMS = [
    ScopeItem(
        id="itm_abc",
        text="Install 200A panel board, 42-circuit",
        drawing_name="E-103",
        page=3,
        source_snippet="200A panel board, 42-circuit, surface mounted",
        confidence=0.95,
        csi_hint="26 24 16",
    ),
    ScopeItem(
        id="itm_def",
        text="Furnish VRF outdoor unit electrical connection",
        drawing_name="E-103",
        page=3,
        source_snippet="VRF-CU-C02, 5-ton outdoor unit, provide 208V",
        confidence=0.88,
        csi_hint="26 05 19",
    ),
]

MOCK_LLM_RESPONSE = json.dumps([
    {
        "item_id": "itm_abc",
        "trade": "Electrical",
        "csi_code": "26 24 16",
        "csi_division": "26 - Electrical",
        "classification_confidence": 0.92,
        "classification_reason": "Panel boards under Division 26",
    },
    {
        "item_id": "itm_def",
        "trade": "Electrical",
        "csi_code": "26 05 19",
        "csi_division": "26 - Electrical",
        "classification_confidence": 0.87,
        "classification_reason": "Electrical connections for mechanical equipment",
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
async def test_classification_agent_parses_llm_response():
    from scope_pipeline.agents.classification_agent import ClassificationAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ClassificationAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(MOCK_LLM_RESPONSE)
    )
    agent._client = mock_client

    result = await agent.run(
        MOCK_SCOPE_ITEMS,
        emitter,
        trade="Electrical",
        available_trades=["Electrical", "Mechanical", "Plumbing"],
    )
    items = result.data

    assert len(items) == 2
    assert items[0].trade == "Electrical"
    assert items[0].csi_code == "26 24 16"
    assert items[0].csi_division == "26 - Electrical"
    assert items[0].classification_confidence == 0.92
    assert items[0].classification_reason == "Panel boards under Division 26"
    # Verify original ScopeItem fields are preserved
    assert items[0].text == "Install 200A panel board, 42-circuit"
    assert items[0].drawing_name == "E-103"


@pytest.mark.asyncio
async def test_classification_agent_handles_markdown_fenced_json():
    from scope_pipeline.agents.classification_agent import ClassificationAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ClassificationAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    fenced = f"```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(fenced)
    )
    agent._client = mock_client

    result = await agent.run(
        MOCK_SCOPE_ITEMS,
        emitter,
        trade="Electrical",
        available_trades=["Electrical", "Mechanical"],
    )
    assert len(result.data) == 2
    assert result.data[0].csi_code == "26 24 16"


@pytest.mark.asyncio
async def test_classification_agent_defaults_for_unmatched_items():
    from scope_pipeline.agents.classification_agent import ClassificationAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    agent = ClassificationAgent(api_key="test-key", model="gpt-4.1")
    emitter = ProgressEmitter()

    # LLM only classifies one of two items
    partial_response = json.dumps([
        {
            "item_id": "itm_abc",
            "trade": "Electrical",
            "csi_code": "26 24 16",
            "csi_division": "26 - Electrical",
            "classification_confidence": 0.92,
            "classification_reason": "Panel boards under Division 26",
        },
    ])
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(partial_response)
    )
    agent._client = mock_client

    result = await agent.run(
        MOCK_SCOPE_ITEMS,
        emitter,
        trade="Electrical",
        available_trades=["Electrical"],
    )
    items = result.data

    # Both items should be returned: one classified, one with defaults
    assert len(items) == 2
    classified_ids = {item.id for item in items}
    assert "itm_abc" in classified_ids
    assert "itm_def" in classified_ids

    # The unmatched item should have default classification values
    default_item = next(i for i in items if i.id == "itm_def")
    assert default_item.trade == "Electrical"
    assert default_item.csi_code == ""
    assert default_item.classification_confidence == 0.0
