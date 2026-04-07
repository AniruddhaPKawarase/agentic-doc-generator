"""
SSE streaming progress with ETA helper.

Stage weights and agent display names are re-exported here for use by
api/scope_gap.py (which owns the streaming logic). This module adds the
ETA formatting utility.
"""
from api.scope_gap import _AGENT_DISPLAY, _STAGE_WEIGHTS  # noqa: F401 — re-export


def format_eta(elapsed_seconds: float, progress: float) -> str:
    """Estimate remaining time based on elapsed time and fractional progress.

    Returns a human-readable string like '~23s remaining' or '~2 min remaining',
    or an empty string when progress is zero or negative.
    """
    if progress <= 0:
        return ""
    remaining = (elapsed_seconds / progress) * (1 - progress)
    if remaining < 60:
        return f"~{int(remaining)}s remaining"
    return f"~{int(remaining / 60)} min remaining"
