"""
routers/chat.py  —  Main conversational chat endpoints.

POST /api/chat
  Run the full pipeline and return a ChatResponse.

POST /api/chat/stream
  Streaming variant — Server-Sent Events (SSE). Each SSE event is:
    data: {"type": "token", "delta": "..."}
  A final event carries:
    data: {"type": "done", "response": <ChatResponse JSON>}

GET /api/sessions/{session_id}/history
  Return the conversation history for a session.

GET /api/sessions/{session_id}/tokens
  Return token usage summary for a session.

DELETE /api/sessions/{session_id}
  Clear a session's conversation history.
"""

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def get_agent(request: Request):
    return request.app.state.generation_agent


def get_sessions(request: Request):
    return request.app.state.session_service


def get_token_tracker(request: Request):
    return request.app.state.token_tracker


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    agent=Depends(get_agent),
):
    """
    Main endpoint. Runs the full intent → data → LLM → doc pipeline.

    Request body:
    ```json
    {
      "project_id": 7276,
      "query": "Create a scope for plumbing",
      "session_id": null,
      "generate_document": true
    }
    ```

    Response includes:
    - `answer`: Markdown-formatted LLM output
    - `document`: Download link for the generated Word file
    - `token_usage`: Input / output token counts and estimated cost
    - `needs_clarification`: True if the model is uncertain
    - `clarification_questions`: Follow-up questions to ask the user
    - `pipeline_ms`: End-to-end latency in milliseconds
    - `cached`: True if served from cache
    """
    try:
        response = await agent.process(body)
        return response
    except Exception as exc:
        logger.exception("Chat pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    agent=Depends(get_agent),
):
    """
    Streaming endpoint — SSE (text/event-stream).

    Token deltas are sent as they arrive:
      data: {"type": "token", "delta": "...text..."}

    When generation is complete, the full ChatResponse is sent:
      data: {"type": "done", "response": {...}}

    If an error occurs:
      data: {"type": "error", "detail": "..."}

    Example fetch:
    ```js
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({project_id: 7276, query: 'Create scope for electrical'})
    });
    const reader = res.body.getReader();
    // read chunks and parse SSE lines
    ```
    """
    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in agent.process_stream(body):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("Streaming pipeline error: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    sessions=Depends(get_sessions),
):
    """Return the conversation history for a session (cache → S3 fallback)."""
    data = await sessions.get_history(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@router.get("/sessions/{session_id}/tokens")
async def get_token_usage(
    session_id: str,
    sessions=Depends(get_sessions),
):
    """Return cumulative token usage for a session (cache → S3 fallback)."""
    totals = await sessions.get_token_totals(session_id)
    if not totals:
        raise HTTPException(status_code=404, detail="No token data for this session")
    return totals


@router.delete("/sessions/{session_id}", status_code=204)
async def clear_session(
    session_id: str,
    sessions=Depends(get_sessions),
):
    """Delete a session's conversation history."""
    await sessions.delete(session_id)
    return None
