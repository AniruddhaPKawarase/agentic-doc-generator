"""tests/scope_pipeline/test_progress_emitter.py"""

import pytest
import asyncio
import json


@pytest.mark.asyncio
async def test_emitter_sends_and_receives():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()

    emitter.emit("agent_start", {"agent": "extraction", "message": "Starting..."})
    emitter.emit("agent_complete", {"agent": "extraction", "elapsed_ms": 62000})
    emitter.emit("pipeline_complete", {"total_ms": 267000})

    events = []
    async for event in emitter.stream():
        events.append(event)

    assert len(events) == 3
    assert events[0]["type"] == "agent_start"
    assert events[0]["data"]["agent"] == "extraction"
    assert events[2]["type"] == "pipeline_complete"


@pytest.mark.asyncio
async def test_emitter_stream_stops_on_terminal_event():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()

    emitter.emit("agent_start", {"agent": "extraction"})
    emitter.emit("pipeline_complete", {"total_ms": 100})
    emitter.emit("agent_start", {"agent": "should_not_appear"})

    events = []
    async for event in emitter.stream():
        events.append(event)

    assert len(events) == 2


def test_emitter_to_sse_format():
    from scope_pipeline.services.progress_emitter import ProgressEmitter
    emitter = ProgressEmitter()

    sse = emitter.format_sse("agent_start", {"agent": "extraction"})
    assert "event: agent_start" in sse
    assert '"agent": "extraction"' in sse
