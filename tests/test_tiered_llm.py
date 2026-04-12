"""Tests for tiered LLM model routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = MagicMock()
    mock_resp.usage.prompt_tokens = 100
    mock_resp.usage.completion_tokens = 50
    return mock_resp


@pytest.mark.asyncio
async def test_intent_agent_uses_intent_model():
    """IntentAgent._llm_detect() uses settings.intent_model, not openai_model."""
    from agents.intent_agent import IntentAgent

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(
            '{"trade": "Electrical", "csi_divisions": ["26"], "document_type": "scope", "intent": "generate", "confidence": 0.9}'
        )
    )

    agent = IntentAgent(openai_client=mock_client)

    with patch("agents.intent_agent.settings") as mock_settings:
        mock_settings.intent_model = "gpt-4.1-nano"
        mock_settings.openai_model = "gpt-4.1-mini"
        mock_settings.intent_max_tokens = 500

        await agent._llm_detect("generate electrical scope", ["Electrical", "Plumbing"])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4.1-nano"


@pytest.mark.asyncio
async def test_followup_uses_followup_model():
    """_generate_follow_up_questions() uses settings.followup_model."""
    from agents.generation_agent import GenerationAgent

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(
            '["What trades are included?", "Any exclusions?"]'
        )
    )

    # Minimal agent construction — just set _client directly
    agent = GenerationAgent.__new__(GenerationAgent)
    agent._client = mock_client

    with patch("agents.generation_agent.settings") as mock_settings:
        mock_settings.followup_model = "gpt-4.1-nano"
        mock_settings.openai_model = "gpt-4.1-mini"
        mock_settings.follow_up_questions_enabled = True
        mock_settings.follow_up_questions_count = 2
        mock_settings.follow_up_max_tokens = 400

        questions = await agent._generate_follow_up_questions(
            answer="Electrical scope includes...",
            query="generate electrical scope",
            trade="Electrical",
            document_type="scope",
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4.1-nano"
