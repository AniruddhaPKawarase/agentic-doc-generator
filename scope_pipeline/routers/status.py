"""
scope_pipeline/routers/status.py -- System health and metrics endpoints.
"""
import time

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/scope-gap", tags=["scope-gap-status"])

_start_time = time.time()


@router.get("/status")
async def pipeline_status(request: Request):
    """System health: agent status, S3, Redis connectivity."""
    cache = request.app.state.cache
    redis_ok = cache.is_connected if hasattr(cache, "is_connected") else False

    s3_ok = False
    try:
        from s3_utils.client import get_s3_client

        s3_ok = get_s3_client() is not None
    except Exception:
        pass

    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "redis_connected": redis_ok,
        "s3_connected": s3_ok,
    }


@router.get("/metrics")
async def pipeline_metrics(request: Request):
    """Pipeline performance metrics -- token usage, job counts."""
    token_tracker = getattr(request.app.state, "token_tracker", None)
    job_manager = getattr(request.app.state, "scope_job_manager", None)

    token_stats = {}
    if token_tracker and hasattr(token_tracker, "get_totals"):
        token_stats = token_tracker.get_totals()

    active_jobs = 0
    if job_manager and hasattr(job_manager, "active_count"):
        active_jobs = job_manager.active_count()

    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "active_jobs": active_jobs,
        "token_usage": token_stats,
    }
