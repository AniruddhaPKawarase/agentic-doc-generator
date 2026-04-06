"""tests/scope_pipeline/test_base_agent.py"""

import pytest
import asyncio
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_base_agent_returns_result_with_timing():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    class FakeAgent(BaseAgent):
        name = "fake"
        requires_llm = False

        async def _execute(self, input_data, emitter, **kwargs):
            return {"items": [1, 2, 3]}

    emitter = ProgressEmitter()
    agent = FakeAgent()
    result = await agent.run({"test": True}, emitter)

    assert result.agent == "fake"
    assert result.data == {"items": [1, 2, 3]}
    assert result.elapsed_ms >= 0
    assert result.attempt == 1


@pytest.mark.asyncio
async def test_base_agent_retries_on_failure():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter

    call_count = 0

    class FailOnceAgent(BaseAgent):
        name = "flaky"
        requires_llm = True
        max_retries = 2

        async def _execute(self, input_data, emitter, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("LLM timeout")
            return {"ok": True}

    emitter = ProgressEmitter()
    agent = FailOnceAgent()
    result = await agent.run({}, emitter)

    assert result.data == {"ok": True}
    assert result.attempt == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_base_agent_raises_after_max_retries():
    from scope_pipeline.agents.base_agent import BaseAgent
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    from scope_pipeline.models import AgentError

    class AlwaysFailAgent(BaseAgent):
        name = "broken"
        requires_llm = True
        max_retries = 1

        async def _execute(self, input_data, emitter, **kwargs):
            raise RuntimeError("Permanent failure")

    emitter = ProgressEmitter()
    agent = AlwaysFailAgent()

    with pytest.raises(AgentError, match="broken"):
        await agent.run({}, emitter)
