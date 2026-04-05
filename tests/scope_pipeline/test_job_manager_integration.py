"""tests/scope_pipeline/test_job_manager_integration.py — Job manager integration tests.

Tests exercise job state transitions, concurrency semaphore, stream_progress,
and failure handling with fast mock pipelines.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import (
    CompletenessReport,
    DocumentSet,
    PipelineStats,
    QualityReport,
    ScopeGapRequest,
    ScopeGapResult,
)
from scope_pipeline.services.job_manager import JobManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(project_id: int = 7166, trade: str = "Electrical") -> ScopeGapResult:
    return ScopeGapResult(
        project_id=project_id,
        project_name="Test",
        trade=trade,
        items=[],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100,
            csi_coverage_pct=100,
            hallucination_count=0,
            overall_pct=100,
            missing_drawings=[],
            missing_csi_codes=[],
            hallucinated_items=[],
            is_complete=True,
            attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=1.0,
            corrections=[],
            validated_items=[],
            removed_items=[],
            summary="ok",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=100,
            attempts=1,
            tokens_used=0,
            estimated_cost_usd=0.0,
            per_agent_timing={},
            records_processed=0,
            items_extracted=0,
        ),
    )


class FastPipeline:
    """Pipeline mock that completes in ~50ms."""

    def __init__(self, delay: float = 0.05, fail: bool = False):
        self._delay = delay
        self._fail = fail

    async def run(self, request, emitter, project_name=""):
        await asyncio.sleep(self._delay)
        if self._fail:
            raise RuntimeError("Pipeline exploded")
        return _make_result(request.project_id, request.trade)


class SlowPipeline:
    """Pipeline mock that takes longer -- used for concurrency tests."""

    def __init__(self, delay: float = 0.3):
        self._delay = delay
        self.running_count = 0
        self.max_concurrent = 0
        self._lock = asyncio.Lock()

    async def run(self, request, emitter, project_name=""):
        async with self._lock:
            self.running_count += 1
            self.max_concurrent = max(self.max_concurrent, self.running_count)
        try:
            await asyncio.sleep(self._delay)
            return _make_result(request.project_id, request.trade)
        finally:
            async with self._lock:
                self.running_count -= 1


# ---------------------------------------------------------------------------
# Job state transitions
# ---------------------------------------------------------------------------


class TestJobTransitions:
    """Verify queued -> running -> completed/failed transitions."""

    @pytest.mark.asyncio
    async def test_job_completes_successfully(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")

        result = await mgr.submit(req)
        job_id = result["job_id"]

        # Wait for completion
        await asyncio.sleep(0.2)

        job = mgr.get_job(job_id)
        assert job is not None
        assert job["status"] == "completed"
        assert job["progress"] == 100.0
        assert job["started_at"] is not None
        assert job["completed_at"] is not None
        assert job["error"] is None

    @pytest.mark.asyncio
    async def test_job_fails_sets_error(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05, fail=True), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")

        result = await mgr.submit(req)
        job_id = result["job_id"]

        await asyncio.sleep(0.2)

        job = mgr.get_job(job_id)
        assert job is not None
        assert job["status"] == "failed"
        assert job["error"] is not None
        assert "Pipeline exploded" in job["error"]
        assert job["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_job_starts_as_queued(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.5), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")

        result = await mgr.submit(req)
        # Immediately after submit, status is queued (before task runs)
        assert result["status"] in ("queued", "running")

        # Cleanup
        await mgr.cancel(result["job_id"])
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancel:
    """Cancel semantics for different job states."""

    @pytest.mark.asyncio
    async def test_cancel_queued_or_running(self):
        mgr = JobManager(pipeline=FastPipeline(delay=1.0), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)

        ok = await mgr.cancel(result["job_id"])
        assert ok is True

        job = mgr.get_job(result["job_id"])
        assert job["status"] == "cancelled"
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_cancel_completed_job_returns_false(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)
        await asyncio.sleep(0.2)

        ok = await mgr.cancel(result["job_id"])
        assert ok is False

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self):
        mgr = JobManager(pipeline=FastPipeline(), max_concurrent=3)
        ok = await mgr.cancel("nonexistent_job")
        assert ok is False

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_returns_false(self):
        mgr = JobManager(pipeline=FastPipeline(delay=1.0), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)

        await mgr.cancel(result["job_id"])
        # Second cancel
        ok = await mgr.cancel(result["job_id"])
        assert ok is False
        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Concurrency semaphore
# ---------------------------------------------------------------------------


class TestConcurrency:
    """Verify semaphore limits concurrent pipeline runs."""

    @pytest.mark.asyncio
    async def test_max_concurrent_respected(self):
        pipeline = SlowPipeline(delay=0.2)
        mgr = JobManager(pipeline=pipeline, max_concurrent=2)

        reqs = [
            ScopeGapRequest(project_id=i, trade="Electrical")
            for i in range(4)
        ]

        jobs = []
        for req in reqs:
            result = await mgr.submit(req)
            jobs.append(result["job_id"])

        # Let them run for a bit
        await asyncio.sleep(0.15)

        # At any point, max 2 should be running concurrently
        assert pipeline.max_concurrent <= 2

        # Wait for all to finish
        await asyncio.sleep(1.0)

        for jid in jobs:
            job = mgr.get_job(jid)
            assert job["status"] in ("completed", "cancelled")


# ---------------------------------------------------------------------------
# List and filter
# ---------------------------------------------------------------------------


class TestListJobs:
    """Test list_jobs with filtering."""

    @pytest.mark.asyncio
    async def test_list_all(self):
        mgr = JobManager(pipeline=FastPipeline(delay=1.0), max_concurrent=3)
        r1 = await mgr.submit(ScopeGapRequest(project_id=7166, trade="Electrical"))
        r2 = await mgr.submit(ScopeGapRequest(project_id=7201, trade="Plumbing"))

        all_jobs = mgr.list_jobs()
        assert len(all_jobs) == 2

        await mgr.cancel(r1["job_id"])
        await mgr.cancel(r2["job_id"])
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05), max_concurrent=3)
        r1 = await mgr.submit(ScopeGapRequest(project_id=7166, trade="Electrical"))
        await asyncio.sleep(0.2)

        completed = mgr.list_jobs(status="completed")
        assert len(completed) >= 1

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        mgr = JobManager(pipeline=FastPipeline(), max_concurrent=3)
        assert mgr.get_job("nonexistent") is None


# ---------------------------------------------------------------------------
# Stream progress
# ---------------------------------------------------------------------------


class TestStreamProgress:
    """Test stream_progress async generator."""

    @pytest.mark.asyncio
    async def test_stream_yields_complete_event(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)
        job_id = result["job_id"]

        events = []
        async for event in mgr.stream_progress(job_id):
            events.append(event)

        # Should get at least pipeline_complete event
        assert len(events) >= 1
        assert events[-1]["type"] == "pipeline_complete"

    @pytest.mark.asyncio
    async def test_stream_yields_failed_event_on_error(self):
        mgr = JobManager(pipeline=FastPipeline(delay=0.05, fail=True), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)
        job_id = result["job_id"]

        events = []
        async for event in mgr.stream_progress(job_id):
            events.append(event)

        assert len(events) >= 1
        assert events[-1]["type"] == "pipeline_failed"
        assert "error" in events[-1]["data"]

    @pytest.mark.asyncio
    async def test_stream_nonexistent_job_returns_immediately(self):
        mgr = JobManager(pipeline=FastPipeline(), max_concurrent=3)
        events = []
        async for event in mgr.stream_progress("nonexistent"):
            events.append(event)
        assert events == []

    @pytest.mark.asyncio
    async def test_stream_cancelled_job_exits(self):
        mgr = JobManager(pipeline=FastPipeline(delay=1.0), max_concurrent=3)
        req = ScopeGapRequest(project_id=7166, trade="Electrical")
        result = await mgr.submit(req)
        job_id = result["job_id"]

        # Cancel quickly
        await asyncio.sleep(0.05)
        await mgr.cancel(job_id)

        events = []
        async for event in mgr.stream_progress(job_id):
            events.append(event)

        # Stream should exit because job is cancelled
        # (may or may not have events depending on timing)
        job = mgr.get_job(job_id)
        assert job["status"] == "cancelled"
