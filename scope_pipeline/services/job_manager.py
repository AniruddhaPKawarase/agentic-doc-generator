"""
scope_pipeline/services/job_manager.py — Background pipeline job management.

Tracks in-memory job state, limits concurrency via semaphore,
and provides SSE progress streaming per job.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from scope_pipeline.models import ScopeGapRequest
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

_JOB_STATES = frozenset({"queued", "running", "completed", "partial", "failed", "cancelled"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _job_id() -> str:
    return f"job_{uuid4().hex[:12]}"


class JobManager:
    """In-memory background job tracker with concurrency limiting."""

    def __init__(self, pipeline: Any, max_concurrent: int = 3) -> None:
        self._pipeline = pipeline
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(self, request: ScopeGapRequest) -> dict[str, Any]:
        """Submit a pipeline run as a background job. Returns immediately."""
        jid = _job_id()
        now = _now()

        self._jobs[jid] = {
            "job_id": jid,
            "status": "queued",
            "project_id": request.project_id,
            "trade": request.trade,
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": 0.0,
            "error": None,
        }
        self._queues[jid] = asyncio.Queue()

        task = asyncio.create_task(self._run_job(jid, request))
        self._tasks[jid] = task

        return {"job_id": jid, "status": self._jobs[jid]["status"]}

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        """Return job status dict or None."""
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering."""
        results = list(self._jobs.values())
        if project_id is not None:
            results = [j for j in results if j["project_id"] == project_id]
        if status is not None:
            results = [j for j in results if j["status"] == status]
        return results

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running or queued job. Returns True if cancelled."""
        job = self._jobs.get(job_id)
        if job is None:
            return False

        if job["status"] in ("completed", "failed", "cancelled"):
            return False

        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()

        job["status"] = "cancelled"
        job["completed_at"] = _now().isoformat()
        return True

    async def stream_progress(self, job_id: str):
        """Async generator yielding progress events for a job."""
        queue = self._queues.get(job_id)
        if queue is None:
            return

        while True:
            try:
                event = queue.get_nowait()
            except asyncio.QueueEmpty:
                job = self._jobs.get(job_id)
                if job and job["status"] in ("completed", "partial", "failed", "cancelled"):
                    return
                await asyncio.sleep(0.05)
                continue
            yield event
            if event.get("type") in ("pipeline_complete", "pipeline_failed", "pipeline_partial"):
                return

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _run_job(self, job_id: str, request: ScopeGapRequest) -> None:
        """Execute pipeline within semaphore, updating job state."""
        job = self._jobs[job_id]

        try:
            async with self._semaphore:
                job["status"] = "running"
                job["started_at"] = _now().isoformat()

                emitter = ProgressEmitter()
                result = await self._pipeline.run(request, emitter, project_name="")

                if job["status"] == "cancelled":
                    return

                job["status"] = "completed"
                job["completed_at"] = _now().isoformat()
                job["progress"] = 100.0

                self._queues[job_id].put_nowait(
                    {"type": "pipeline_complete", "data": {"job_id": job_id}}
                )

        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["completed_at"] = _now().isoformat()

        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            job["status"] = "failed"
            job["completed_at"] = _now().isoformat()
            job["error"] = str(exc)

            self._queues[job_id].put_nowait(
                {"type": "pipeline_failed", "data": {"job_id": job_id, "error": str(exc)}}
            )
