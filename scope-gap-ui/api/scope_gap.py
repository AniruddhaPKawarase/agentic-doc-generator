"""
Scope-gap pipeline API calls — streaming (SSE) and synchronous.
"""
import json
from typing import Optional

import requests

from api.client import _get, _post
from config import API_BASE, GENERATE_TIMEOUT, REQUEST_TIMEOUT


# ── Pipeline stage weights for the progress bar ──
_STAGE_WEIGHTS = {
    "data_fetch":     0.10,
    "extraction":     0.25,
    "classification": 0.15,
    "ambiguity":      0.10,
    "gotcha":         0.10,
    "completeness":   0.05,
    "quality":        0.10,
    "documents":      0.10,
    "finalize":       0.05,
}

_AGENT_DISPLAY = {
    "extraction":     ("📄", "Extracting scope items from drawings"),
    "classification": ("🏷️", "Classifying items by trade & CSI code"),
    "ambiguity":      ("⚠️", "Detecting trade ambiguities & overlaps"),
    "gotcha":         ("🔍", "Identifying hidden risks & gotchas"),
    "completeness":   ("✅", "Checking coverage completeness"),
    "quality":        ("⭐", "Running quality review"),
    "document":       ("📝", "Generating reports & documents"),
}


def api_get_trades(project_id: int, set_id=None) -> Optional[dict]:
    params = {"set_id": set_id} if set_id else {}
    return _get(f"/api/scope-gap/projects/{project_id}/trades", params)


def api_get_trade_colors(project_id: int) -> Optional[dict]:
    return _get(f"/api/scope-gap/projects/{project_id}/trade-colors")


def api_get_drawings(project_id: int) -> Optional[dict]:
    return _get(f"/api/scope-gap/projects/{project_id}/drawings")


def api_run_scope_gap(project_id: int, trade: str) -> Optional[dict]:
    """Fallback synchronous call (no progress). Used only if streaming fails."""
    return _post("/api/scope-gap/generate",
                 {"project_id": project_id, "trade": trade},
                 timeout=GENERATE_TIMEOUT)


def api_run_scope_gap_streaming(project_id: int, trade: str, progress_bar, status_text):
    """Stream the pipeline via SSE, updating a Streamlit progress bar in real time.

    Returns the final result dict, or an error dict.
    """
    payload = json.dumps({"project_id": project_id, "trade": trade})
    url = f"{API_BASE}/api/scope-gap/stream"

    progress = 0.0
    completed_agents: set = set()
    current_attempt = 1
    final_result = None

    try:
        with requests.post(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            stream=True,
            timeout=None,
        ) as resp:
            if resp.status_code != 200:
                return {"error": f"Stream failed with status {resp.status_code}: {resp.text[:200]}"}

            event_type = ""
            event_data = ""

            for line in resp.iter_lines(decode_unicode=True):
                if line is None:
                    continue
                line = line.strip() if isinstance(line, str) else line.decode().strip()

                if line.startswith("event:"):
                    event_type = line[len("event:"):].strip()
                    continue
                elif line.startswith("data:"):
                    event_data = line[len("data:"):].strip()
                elif line == "" and event_type:
                    progress, final_result = _process_sse_event(
                        event_type, event_data,
                        progress, completed_agents, current_attempt,
                        progress_bar, status_text,
                    )
                    if event_type == "backpropagation":
                        try:
                            bp_data = json.loads(event_data)
                            current_attempt = bp_data.get("attempt", current_attempt) + 1
                        except (json.JSONDecodeError, TypeError):
                            current_attempt += 1
                    event_type = ""
                    event_data = ""

                    if final_result is not None:
                        progress_bar.progress(1.0)
                        return final_result

    except requests.exceptions.ConnectionError:
        return None
    except Exception as exc:
        return {"error": f"Streaming error: {str(exc)[:200]}"}

    if final_result is not None:
        return final_result
    return {"error": "Stream ended without a result. The pipeline may have failed — check server logs."}


def _process_sse_event(
    event_type: str, event_data: str,
    progress: float, completed_agents: set, current_attempt: int,
    progress_bar, status_text,
) -> tuple[float, dict | None]:
    """Process a single SSE event and update the progress bar.

    Returns (new_progress, final_result_or_None).
    """
    try:
        data = json.loads(event_data) if event_data else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    final_result = None

    if event_type == "data_fetch":
        progress = _STAGE_WEIGHTS["data_fetch"]
        status_text.markdown("📡 **Fetching drawing records** from API…")

    elif event_type == "agent_start":
        agent = data.get("agent", "")
        icon, label = _AGENT_DISPLAY.get(agent, ("⚙️", f"Running {agent}"))
        attempt_label = f" (attempt {current_attempt})" if current_attempt > 1 else ""
        status_text.markdown(f"{icon} **{label}**{attempt_label}")

    elif event_type == "agent_complete":
        agent = data.get("agent", "")
        elapsed = data.get("elapsed_ms", 0)
        completed_agents.add(agent)
        weight = _STAGE_WEIGHTS.get(agent, 0.05)
        progress = min(progress + weight, 0.95)
        progress_bar.progress(progress)
        icon, label = _AGENT_DISPLAY.get(agent, ("✓", agent))
        secs = elapsed / 1000.0
        status_text.markdown(f"✓ **{agent.title()}** done in {secs:.1f}s")

    elif event_type == "agent_progress":
        msg = data.get("message", "")
        if msg:
            status_text.markdown(f"⏳ {msg}")

    elif event_type == "completeness":
        pct = data.get("overall_pct", 0)
        is_complete = data.get("is_complete", False)
        progress = min(progress + _STAGE_WEIGHTS["completeness"], 0.95)
        progress_bar.progress(progress)
        if is_complete:
            status_text.markdown(f"✅ **Completeness: {pct:.0f}%** — threshold met!")
        else:
            status_text.markdown(f"⚠️ **Completeness: {pct:.0f}%** — below threshold, retrying…")

    elif event_type == "backpropagation":
        attempt = data.get("attempt", 1)
        missing = data.get("missing_drawings", [])
        progress = max(progress - 0.25, _STAGE_WEIGHTS["data_fetch"])
        progress_bar.progress(progress)
        status_text.markdown(
            f"🔄 **Backpropagation** — attempt {attempt} incomplete, "
            f"retrying {len(missing)} missing drawing(s)…"
        )

    elif event_type in ("pipeline_complete", "pipeline_partial"):
        items = data.get("items_count", 0)
        attempts = data.get("attempts", 1)
        pct = data.get("completeness_pct", 0)
        progress = 0.95
        progress_bar.progress(progress)
        if event_type == "pipeline_complete":
            status_text.markdown(
                f"✅ **Pipeline complete** — {items} items, {pct:.0f}% coverage, "
                f"{attempts} attempt(s)"
            )
        else:
            status_text.markdown(
                f"⚠️ **Pipeline partial** — {items} items, {pct:.0f}% coverage, "
                f"{attempts} attempt(s)"
            )

    elif event_type == "result":
        final_result = data
        progress_bar.progress(1.0)
        status_text.markdown("🎉 **Done!** Generating report…")

    elif event_type == "error":
        error_msg = data.get("error", "Unknown pipeline error")
        final_result = {"error": error_msg}

    elif event_type == "agent_failed":
        agent = data.get("agent", "")
        error = data.get("error", "")
        status_text.markdown(f"❌ **{agent.title()}** failed: {error[:100]}")

    return progress, final_result


def api_run_all(project_id: int, force: bool = False) -> Optional[dict]:
    return _post(f"/api/scope-gap/projects/{project_id}/run-all",
                 {"force_rerun": force})


def api_get_status(project_id: int) -> Optional[dict]:
    return _get(f"/api/scope-gap/projects/{project_id}/status")
