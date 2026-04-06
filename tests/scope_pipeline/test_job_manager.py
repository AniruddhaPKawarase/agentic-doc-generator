"""tests/scope_pipeline/test_job_manager.py — Job Manager tests."""

import asyncio

import pytest

from scope_pipeline.models import (
    ScopeGapRequest,
    ScopeGapResult,
    CompletenessReport,
    QualityReport,
    PipelineStats,
)


class MockPipeline:
    """Simulates a slow pipeline run returning a minimal result."""

    async def run(self, request, emitter, project_name=""):
        await asyncio.sleep(0.5)
        return ScopeGapResult(
            project_id=request.project_id,
            project_name=project_name or "Test",
            trade=request.trade,
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
            documents=None,
            pipeline_stats=PipelineStats(
                total_ms=500,
                attempts=1,
                tokens_used=0,
                estimated_cost_usd=0.0,
                per_agent_timing={},
                records_processed=0,
                items_extracted=0,
            ),
        )


@pytest.mark.asyncio
async def test_submit_creates_job():
    """Submitting a request returns a job_id with queued status."""
    from scope_pipeline.services.job_manager import JobManager

    mgr = JobManager(pipeline=MockPipeline(), max_concurrent=3)
    request = ScopeGapRequest(project_id=7166, trade="Electrical")

    result = await mgr.submit(request)

    assert "job_id" in result
    assert result["status"] in ("queued", "running")
    assert result["job_id"].startswith("job_")

    # Clean up background task
    await mgr.cancel(result["job_id"])
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_list_jobs_filters():
    """Submitting 2 jobs for different projects, filtering by project_id returns 1."""
    from scope_pipeline.services.job_manager import JobManager

    mgr = JobManager(pipeline=MockPipeline(), max_concurrent=3)

    req1 = ScopeGapRequest(project_id=7166, trade="Electrical")
    req2 = ScopeGapRequest(project_id=7201, trade="Plumbing")

    r1 = await mgr.submit(req1)
    r2 = await mgr.submit(req2)

    filtered = mgr.list_jobs(project_id=7166)
    assert len(filtered) == 1
    assert filtered[0]["job_id"] == r1["job_id"]

    all_jobs = mgr.list_jobs()
    assert len(all_jobs) == 2

    # Clean up
    await mgr.cancel(r1["job_id"])
    await mgr.cancel(r2["job_id"])
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_cancel_job():
    """Cancelling a running job sets status to cancelled."""
    from scope_pipeline.services.job_manager import JobManager

    mgr = JobManager(pipeline=MockPipeline(), max_concurrent=3)
    request = ScopeGapRequest(project_id=7166, trade="Electrical")

    result = await mgr.submit(request)
    job_id = result["job_id"]

    cancelled = await mgr.cancel(job_id)
    assert cancelled is True

    await asyncio.sleep(0.1)
    job = mgr.get_job(job_id)
    assert job is not None
    assert job["status"] == "cancelled"
