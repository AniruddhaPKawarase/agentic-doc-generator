"""
scope_pipeline/routers/scope_gap.py — API endpoints for scope gap pipeline.

Endpoints:
  - Pipeline execution: /generate, /stream, /submit
  - Job management: /jobs, /jobs/{id}/status, /jobs/{id}/result, /jobs/{id}/continue, DELETE /jobs/{id}
  - Session management: /sessions, /sessions/{id}, DELETE /sessions/{id}
  - User decisions: resolve-ambiguity, acknowledge-gotcha, ignore-item, restore-item
  - Follow-up chat: /sessions/{id}/chat
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from scope_pipeline.models import ScopeGapRequest
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap", tags=["scope-gap"])


# ---------------------------------------------------------------------------
# Request bodies for user-decision endpoints
# ---------------------------------------------------------------------------

class ResolveAmbiguityBody(BaseModel):
    ambiguity_id: str
    assigned_trade: str


class AcknowledgeGotchaBody(BaseModel):
    gotcha_id: str


class ItemActionBody(BaseModel):
    item_id: str


class ChatBody(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Dependency helpers (access app.state objects)
# ---------------------------------------------------------------------------

def _get_pipeline(request: Request):
    return request.app.state.scope_pipeline


def _get_job_manager(request: Request):
    return request.app.state.scope_job_manager


def _get_session_manager(request: Request):
    return request.app.state.scope_session_manager


def _get_chat_handler(request: Request):
    return request.app.state.scope_chat_handler


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate(body: ScopeGapRequest, request: Request) -> Any:
    """Synchronous pipeline execution.

    Runs the full pipeline inline and returns the result.
    For very large datasets, use /submit for background execution.
    """
    pipeline = _get_pipeline(request)

    try:
        emitter = ProgressEmitter()
        result = await pipeline.run(body, emitter, project_name="")
        return result.model_dump()
    except Exception as exc:
        logger.exception("Pipeline execution failed for project=%s trade=%s", body.project_id, body.trade)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stream")
async def stream(body: ScopeGapRequest, request: Request):
    """SSE streaming pipeline execution.

    Returns a text/event-stream with progress events during execution,
    followed by the final result event.
    """
    pipeline = _get_pipeline(request)

    async def event_generator():
        emitter = ProgressEmitter()
        task = asyncio.create_task(pipeline.run(body, emitter, project_name=""))

        async for event in emitter.stream():
            yield {
                "event": event["type"],
                "data": json.dumps(event["data"], default=str),
            }

        try:
            result = await task
            yield {
                "event": "result",
                "data": result.model_dump_json(),
            }
        except Exception as exc:
            logger.exception("Streaming pipeline failed")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)}),
            }

    return EventSourceResponse(event_generator())


@router.post("/submit")
async def submit(body: ScopeGapRequest, request: Request):
    """Submit pipeline as a background job.

    Returns immediately with a job_id for polling via /jobs/{id}/status.
    """
    job_mgr = _get_job_manager(request)

    try:
        job = await job_mgr.submit(body)
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job["job_id"],
                "status": job["status"],
                "poll_url": f"/api/scope-gap/jobs/{job['job_id']}/status",
            },
        )
    except Exception as exc:
        logger.exception("Job submission failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------

@router.get("/jobs")
async def list_jobs(
    request: Request,
    project_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
) -> list[dict[str, Any]]:
    """List pipeline jobs with optional filters."""
    job_mgr = _get_job_manager(request)
    return job_mgr.list_jobs(project_id=project_id, status=status)


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str, request: Request) -> dict[str, Any]:
    """Get current status and progress for a job."""
    job_mgr = _get_job_manager(request)
    job = job_mgr.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/jobs/{job_id}/result")
async def job_result(job_id: str, request: Request) -> Any:
    """Retrieve the result of a completed job.

    Only available when job status is 'completed' or 'partial'.
    """
    job_mgr = _get_job_manager(request)
    job = job_mgr.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job["status"] not in ("completed", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is '{job['status']}' -- result not yet available",
        )

    # The job manager stores result on the session via the pipeline.
    # For v1, direct the client to the session endpoint for full results.
    return {"job_id": job_id, "status": job["status"], "message": "Use session endpoint for full result."}


@router.post("/jobs/{job_id}/continue")
async def continue_job(job_id: str, request: Request):
    """Continue a partial extraction by re-submitting for the same parameters.

    Creates a new background job targeting missing drawings.
    """
    job_mgr = _get_job_manager(request)
    job = job_mgr.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job["status"] != "partial":
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is '{job['status']}' -- can only continue partial jobs",
        )

    # Re-submit with the same parameters
    new_request = ScopeGapRequest(
        project_id=job["project_id"],
        trade=job["trade"],
    )
    new_job = await job_mgr.submit(new_request)
    return JSONResponse(
        status_code=202,
        content={
            "job_id": new_job["job_id"],
            "status": new_job["status"],
            "continued_from": job_id,
            "poll_url": f"/api/scope-gap/jobs/{new_job['job_id']}/status",
        },
    )


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    """Cancel a queued or running job."""
    job_mgr = _get_job_manager(request)
    cancelled = await job_mgr.cancel(job_id)
    if not cancelled:
        job = job_mgr.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is '{job['status']}' -- cannot cancel",
        )
    return {"cancelled": True, "job_id": job_id}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(
    request: Request,
    project_id: Optional[int] = Query(None),
    trade: Optional[str] = Query(None),
) -> list[dict[str, Any]]:
    """List scope gap sessions with optional filters."""
    session_mgr = _get_session_manager(request)
    sessions = session_mgr.list_sessions(project_id=project_id, trade=trade)
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "trade": s.trade,
            "set_ids": s.set_ids,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "runs_count": len(s.runs),
            "has_result": s.latest_result is not None,
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    """Get full session detail including runs, resolutions, and messages."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session.model_dump()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict[str, Any]:
    """Delete a session and all its data."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    await session_mgr.delete(session)
    return {"deleted": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# User decisions
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/resolve-ambiguity")
async def resolve_ambiguity(
    session_id: str, body: ResolveAmbiguityBody, request: Request,
) -> dict[str, Any]:
    """Assign a trade to an ambiguous scope item."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    session.ambiguity_resolutions[body.ambiguity_id] = body.assigned_trade
    await session_mgr.update(session)
    return {
        "resolved": True,
        "ambiguity_id": body.ambiguity_id,
        "assigned_trade": body.assigned_trade,
    }


@router.post("/sessions/{session_id}/acknowledge-gotcha")
async def acknowledge_gotcha(
    session_id: str, body: AcknowledgeGotchaBody, request: Request,
) -> dict[str, Any]:
    """Acknowledge a gotcha/hidden risk item."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if body.gotcha_id not in session.gotcha_acknowledgments:
        session.gotcha_acknowledgments.append(body.gotcha_id)
        await session_mgr.update(session)
    return {"acknowledged": True, "gotcha_id": body.gotcha_id}


@router.post("/sessions/{session_id}/ignore-item")
async def ignore_item(
    session_id: str, body: ItemActionBody, request: Request,
) -> dict[str, Any]:
    """Mark a scope item as ignored (excluded from reports)."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if body.item_id not in session.ignored_items:
        session.ignored_items.append(body.item_id)
        await session_mgr.update(session)
    return {"ignored": True, "item_id": body.item_id}


@router.post("/sessions/{session_id}/restore-item")
async def restore_item(
    session_id: str, body: ItemActionBody, request: Request,
) -> dict[str, Any]:
    """Restore a previously ignored scope item."""
    session_mgr = _get_session_manager(request)
    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    new_ignored = [iid for iid in session.ignored_items if iid != body.item_id]
    restored = len(new_ignored) < len(session.ignored_items)
    session.ignored_items = new_ignored
    if restored:
        await session_mgr.update(session)
    return {"restored": restored, "item_id": body.item_id}


# ---------------------------------------------------------------------------
# Follow-up chat
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str, body: ChatBody, request: Request,
) -> dict[str, Any]:
    """Ask a follow-up question about the scope gap report."""
    session_mgr = _get_session_manager(request)
    chat_handler = _get_chat_handler(request)

    session = session_mgr.get_session_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        response = await chat_handler.handle(session, body.message)
        await session_mgr.update(session)
        return response
    except Exception as exc:
        logger.exception("Chat handler failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
