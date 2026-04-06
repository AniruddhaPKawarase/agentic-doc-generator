"""
iFieldSmart ScopeAI — Streamlit UI
Construction Intelligence Agent frontend
"""
import json
import time
import uuid
from typing import Optional

import requests
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
API_BASE = "http://54.197.189.113:8003"
REQUEST_TIMEOUT = 300          # 5 min — 7-agent pipeline can take 200-300s
GENERATE_TIMEOUT = 600         # 10 min — max for large datasets with backprop

PROJECTS = [
    {"id": "PRJ-001", "project_id": 7276, "name": "450-460 JR PKWY Phase II",
     "loc": "Nashville, TN", "pm": "Smith Gee Studio", "status": "Active",
     "type": "Residential & Garage", "prog": 62},
    {"id": "PRJ-002", "project_id": 7298, "name": "AVE Horsham Multi-Family",
     "loc": "Horsham, PA", "pm": "Bernardon Design", "status": "Active",
     "type": "Multi-Family", "prog": 38},
    {"id": "PRJ-003", "project_id": 7212, "name": "HSB Potomac Senior Living",
     "loc": "Potomac, MD", "pm": "Vessel Architecture", "status": "Active",
     "type": "Senior Living", "prog": 45},
    {"id": "PRJ-004", "project_id": 7222, "name": "Metro Transit Hub",
     "loc": "Chicago, IL", "pm": "James Wilson", "status": "On-Hold",
     "type": "Infrastructure", "prog": 15},
    {"id": "PRJ-005", "project_id": 7223, "name": "Greenfield Data Center",
     "loc": "Phoenix, AZ", "pm": "Tom Davis", "status": "Completed",
     "type": "Industrial", "prog": 100},
]

TRADE_COLOR_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
    "#14B8A6", "#D97706", "#DC2626", "#7C3AED", "#DB2777",
    "#0891B2", "#65A30D", "#EA580C", "#4F46E5", "#0D9488",
    "#B45309", "#BE123C", "#6D28D9",
]

STATUS_CONFIG = {
    "Active":    {"bg": "#DCFCE7", "text": "#166534", "dot": "#22C55E"},
    "On-Hold":   {"bg": "#FEF3C7", "text": "#92400E", "dot": "#F59E0B"},
    "Completed": {"bg": "#F1F5F9", "text": "#475569", "dot": "#94A3B8"},
}

AGENTS = [
    {"name": "RFI Agent",       "icon": "❓", "desc": "Manage RFIs and queries",          "page": None},
    {"name": "Submittal Agent", "icon": "📋", "desc": "Track submittal packages",          "page": None},
    {"name": "Drawings Agent",  "icon": "📐", "desc": "Scope gap analysis on drawings",   "page": "workspace"},
    {"name": "Spec Agent",      "icon": "📄", "desc": "Specification review & gaps",       "page": None},
    {"name": "BIM Planner",     "icon": "🏗️", "desc": "BIM coordination & clash detection","page": None},
    {"name": "Meeting Agent",   "icon": "🗓️", "desc": "Meeting summaries & action items",  "page": None},
]

MOCK_TRADES = [
    "Electrical", "Plumbing", "HVAC", "Structural", "Concrete",
    "Fire Sprinkler", "Roofing & Waterproofing", "Framing Drywall & Insulation",
    "Glass & Glazing", "Painting & Coatings",
]

MOCK_DRAWINGS = {
    "Architectural": ["A-001 Site Plan", "A-101 Floor Plan L1", "A-201 Elevations"],
    "Structural":    ["S-001 Foundation Plan", "S-101 Framing Plan"],
    "Electrical":    ["E-001 Power Plan", "E-101 Lighting Plan"],
    "Plumbing":      ["P-001 Plumbing Plan", "P-101 Riser Diagram"],
    "Mechanical":    ["M-001 HVAC Layout", "M-101 Ductwork Plan"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="iFieldSmart ScopeAI",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─────────────────────────────────────────────────────────────────────────────
# Session-state initialisation
# ─────────────────────────────────────────────────────────────────────────────
def _init_session():
    defaults = {
        "page": "projects",
        "selected_project": None,
        "workspace_view": "export",
        "selected_trade": None,
        "trades_data": {},
        "scope_results": {},
        "chat_messages": [],
        "chat_session_id": None,
        "ref_panel_open": False,
        "ref_panel_items": [],
        "drawing_filter": "",
        "search_filter": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_session()


# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get(path: str, params: dict = None) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {REQUEST_TIMEOUT}s"}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def _post(path: str, payload: dict, timeout: int = 0) -> Optional[dict]:
    effective_timeout = timeout or REQUEST_TIMEOUT
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload,
                          timeout=effective_timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {effective_timeout}s. The pipeline may still be running — check status before retrying."}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def api_health():
    return _get("/health")


def api_get_trades(project_id: int, set_id=None):
    params = {"set_id": set_id} if set_id else {}
    return _get(f"/api/scope-gap/projects/{project_id}/trades", params)


def api_get_trade_colors(project_id: int):
    return _get(f"/api/scope-gap/projects/{project_id}/trade-colors")


def api_get_drawings(project_id: int):
    return _get(f"/api/scope-gap/projects/{project_id}/drawings")


def api_run_scope_gap(project_id: int, trade: str):
    """Fallback synchronous call (no progress). Used only if streaming fails."""
    return _post("/api/scope-gap/generate", {"project_id": project_id, "trade": trade},
                 timeout=GENERATE_TIMEOUT)


# ── Pipeline stage weights for the progress bar ──
# Weights reflect approximate time each stage takes relative to total.
# The pipeline runs: data_fetch → extraction → (classification|ambiguity|gotcha) → completeness → quality → documents
# Backpropagation can repeat extraction→completeness up to 3 times.
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


def api_run_scope_gap_streaming(project_id: int, trade: str, progress_bar, status_text):
    """Stream the pipeline via SSE, updating a Streamlit progress bar in real time.

    Returns the final result dict, or an error dict.
    """
    payload = json.dumps({"project_id": project_id, "trade": trade})
    url = f"{API_BASE}/api/scope-gap/stream"

    progress = 0.0
    completed_agents = set()
    current_attempt = 1
    final_result = None

    try:
        with requests.post(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            stream=True,
            timeout=None,  # No timeout — we rely on SSE events to know when done
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
                    # End of event — process it
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

    # If we exit the loop without a result, stream ended unexpectedly
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
        status_text.markdown(f"📡 **Fetching drawing records** from API…")

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
        # Reset progress partially for retry
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
        # This is the final result payload
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


def api_run_all(project_id: int, force: bool = False):
    return _post(f"/api/scope-gap/projects/{project_id}/run-all",
                 {"force_rerun": force})


def api_chat(project_id: int, query: str, session_id=None):
    payload = {"project_id": project_id, "query": query}
    if session_id:
        payload["session_id"] = session_id
    return _post("/api/chat", payload)


def api_get_status(project_id: int):
    return _get(f"/api/scope-gap/projects/{project_id}/status")


def api_create_highlight(project_id: int, user_id: str, data: dict):
    try:
        r = requests.post(
            f"{API_BASE}/api/scope-gap/highlights",
            json={**data, "project_id": project_id},
            headers={"X-User-Id": user_id},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def api_get_highlights(project_id: int, user_id: str, drawing_name: str):
    try:
        r = requests.get(
            f"{API_BASE}/api/scope-gap/highlights",
            params={"project_id": project_id, "drawing_name": drawing_name},
            headers={"X-User-Id": user_id},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────
def trade_color(index: int) -> str:
    return TRADE_COLOR_PALETTE[index % len(TRADE_COLOR_PALETTE)]


def project_by_id(pid: int):
    return next((p for p in PROJECTS if p["project_id"] == pid), None)


def nav(page: str):
    st.session_state.page = page
    st.rerun()


def score_bar_html(value: float, color: str = "#3B82F6") -> str:
    pct = min(max(value * 100, 0), 100)
    return (
        f'<div style="background:#E2E8F0;border-radius:4px;height:8px;width:100%;">'
        f'<div style="background:{color};width:{pct:.1f}%;height:8px;border-radius:4px;"></div>'
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown(
        """
<style>
/* ── Reset & base ── */
* { box-sizing: border-box; }
[data-testid="stAppViewContainer"] { background: #F1F5F9; }
[data-testid="stHeader"] { display: none; }
[data-testid="stSidebar"] { background: #1E293B !important; color: #E2E8F0; }
[data-testid="stSidebar"] * { color: #E2E8F0 !important; }
[data-testid="stSidebarContent"] { padding: 0; }

/* ── Hide default Streamlit decorations ── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* ── Global font ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Top nav bar ── */
.ifs-navbar {
    background: #1E293B;
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    border-bottom: 1px solid #334155;
    position: sticky;
    top: 0;
    z-index: 100;
}
.ifs-logo { display: flex; align-items: center; gap: 10px; }
.ifs-logo-mark {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #C4841D, #E8A842);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 800; color: #fff;
}
.ifs-logo-text { font-size: 15px; font-weight: 700; color: #fff; }
.ifs-logo-sub  { font-size: 11px; color: #94A3B8; }
.ifs-nav-links { display: flex; gap: 4px; }
.ifs-nav-link {
    padding: 6px 12px; border-radius: 6px;
    font-size: 13px; font-weight: 500; color: #94A3B8;
    cursor: pointer; transition: all 0.15s;
    border: none; background: transparent;
}
.ifs-nav-link:hover { background: #334155; color: #fff; }
.ifs-nav-link.active { background: #334155; color: #fff; }

/* ── Hero ── */
.ifs-hero {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    padding: 48px 24px 36px;
    text-align: center;
    border-bottom: 1px solid #334155;
}
.ifs-hero h1 {
    font-size: 28px; font-weight: 800; color: #fff; margin: 0 0 8px;
}
.ifs-hero p {
    font-size: 15px; color: #94A3B8; margin: 0 0 24px;
}

/* ── Project cards ── */
.proj-card {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px;
    transition: all 0.2s ease;
    cursor: pointer;
    position: relative;
    overflow: hidden;
}
.proj-card:hover {
    border-color: #3B82F6;
    box-shadow: 0 4px 16px rgba(59,130,246,0.15);
    transform: translateY(-2px);
}
.proj-card-accent {
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #C4841D, #E8A842);
}
.proj-card-name {
    font-size: 15px; font-weight: 700; color: #0F172A; margin: 12px 0 4px;
}
.proj-card-meta {
    font-size: 12px; color: #64748B; display: flex; align-items: center; gap: 6px;
}
.proj-card-type {
    font-size: 11px; color: #94A3B8; background: #F8FAFC;
    border: 1px solid #E2E8F0; border-radius: 4px; padding: 2px 6px; margin-top: 8px;
    display: inline-block;
}
.proj-progress-label {
    font-size: 11px; color: #64748B; margin: 10px 0 4px;
    display: flex; justify-content: space-between;
}

/* ── Badges ── */
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 9999px;
    font-size: 11px; font-weight: 600;
}
.badge-active   { background: #DCFCE7; color: #166534; }
.badge-onhold   { background: #FEF3C7; color: #92400E; }
.badge-completed{ background: #F1F5F9; color: #475569; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; }
.badge-dot-active   { background: #22C55E; }
.badge-dot-onhold   { background: #F59E0B; }
.badge-dot-completed{ background: #94A3B8; }

/* ── Agent cards ── */
.agent-card {
    background: #fff;
    border: 1.5px solid #E2E8F0;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
}
.agent-card:hover {
    border-color: #3B82F6;
    box-shadow: 0 4px 16px rgba(59,130,246,0.12);
    transform: translateY(-2px);
}
.agent-card.active-agent {
    border-color: #C4841D;
    background: linear-gradient(135deg, #FFFBEB, #fff);
    box-shadow: 0 4px 16px rgba(196,132,29,0.15);
}
.agent-icon {
    font-size: 32px; margin-bottom: 10px; display: block;
}
.agent-name { font-size: 14px; font-weight: 700; color: #0F172A; margin: 0 0 6px; }
.agent-desc { font-size: 12px; color: #64748B; }
.agent-arrow {
    position: absolute; top: 12px; right: 12px;
    font-size: 14px; color: #94A3B8;
}

/* ── Breadcrumb ── */
.breadcrumb {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: #64748B; padding: 12px 0;
}
.breadcrumb a {
    color: #3B82F6; text-decoration: none; font-weight: 500;
}
.breadcrumb-sep { color: #CBD5E1; }
.breadcrumb-current { color: #0F172A; font-weight: 600; }

/* ── Section header ── */
.section-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 1px solid #E2E8F0;
}
.section-title { font-size: 16px; font-weight: 700; color: #0F172A; }

/* ── Trade rows ── */
.trade-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; border-radius: 8px;
    background: #fff; border: 1px solid #E2E8F0;
    margin-bottom: 8px; cursor: pointer;
    transition: all 0.15s;
}
.trade-row:hover {
    border-color: #3B82F6;
    background: #EFF6FF;
}
.trade-dot-name { display: flex; align-items: center; gap: 10px; }
.trade-color-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.trade-name { font-size: 13px; font-weight: 600; color: #0F172A; }

/* ── Scope item ── */
.scope-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px; border-radius: 8px;
    background: #F8FAFC; border: 1px solid #E2E8F0;
    margin-bottom: 6px;
    transition: background 0.15s;
}
.scope-item:hover { background: #EFF6FF; }
.scope-item-text { font-size: 13px; color: #0F172A; flex: 1; line-height: 1.5; }
.scope-item-link {
    font-size: 18px; cursor: pointer; color: #64748B; flex-shrink: 0;
    transition: color 0.15s;
}
.scope-item-link:hover { color: #3B82F6; }

/* ── Score cards ── */
.score-card {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 10px; padding: 14px 16px;
}
.score-label {
    font-size: 11px; font-weight: 600; color: #64748B;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;
}
.score-value { font-size: 22px; font-weight: 800; color: #0F172A; }
.score-sub   { font-size: 11px; color: #94A3B8; margin-top: 2px; }

/* ── Reference panel ── */
.ref-panel {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 12px; padding: 16px;
    position: relative;
}
.ref-panel-title {
    font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 12px;
    padding-bottom: 8px; border-bottom: 1px solid #E2E8F0;
}
.ref-card {
    background: #F8FAFC; border: 1px solid #E2E8F0;
    border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;
}
.ref-card-name { font-size: 12px; font-weight: 600; color: #0F172A; }
.ref-card-meta { font-size: 11px; color: #64748B; margin-top: 2px; }

/* ── Sidebar (workspace) ── */
.sidebar-header {
    background: #0F172A; padding: 16px;
    border-bottom: 1px solid #1E293B;
}
.sidebar-title {
    font-size: 13px; font-weight: 700; color: #F8FAFC; margin-bottom: 4px;
}
.sidebar-sub { font-size: 11px; color: #64748B; }

/* ── Drawing canvas placeholder ── */
.drawing-canvas {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 12px; min-height: 500px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: #94A3B8; gap: 8px;
}

/* ── Chat messages ── */
.chat-msg-user {
    background: #3B82F6; color: #fff;
    border-radius: 12px 12px 2px 12px;
    padding: 10px 14px; font-size: 13px;
    max-width: 72%; margin-left: auto; margin-bottom: 8px;
}
.chat-msg-agent {
    background: #fff; color: #0F172A;
    border: 1px solid #E2E8F0;
    border-radius: 12px 12px 12px 2px;
    padding: 10px 14px; font-size: 13px;
    max-width: 85%; margin-right: auto; margin-bottom: 8px;
}
.chat-msg-time {
    font-size: 10px; opacity: 0.6; margin-top: 4px;
}

/* ── Warning / info banners ── */
.banner-warn {
    background: #FEF3C7; border: 1px solid #FDE68A;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #92400E; margin-bottom: 12px;
}
.banner-info {
    background: #DBEAFE; border: 1px solid #BFDBFE;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #1E40AF; margin-bottom: 12px;
}
.banner-error {
    background: #FEE2E2; border: 1px solid #FECACA;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #991B1B; margin-bottom: 12px;
}

/* ── Button override helpers ── */
div[data-testid="stButton"] > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stButton"] > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}

/* ── Progress bar override ── */
[data-testid="stProgress"] > div {
    height: 6px !important;
    border-radius: 3px !important;
}

/* ── Utility ── */
.text-muted { color: #64748B; font-size: 12px; }
.text-sm    { font-size: 12px; }
.text-xs    { font-size: 11px; }
.fw-bold    { font-weight: 700; }
.mt-1       { margin-top: 8px; }
.mt-2       { margin-top: 16px; }
.gap-1      { gap: 8px; }
.flex-row   { display: flex; align-items: center; gap: 8px; }
</style>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shared: navbar
# ─────────────────────────────────────────────────────────────────────────────
def render_navbar():
    proj = st.session_state.selected_project
    page = st.session_state.page

    st.markdown(
        """
<div class="ifs-navbar">
  <div class="ifs-logo">
    <div class="ifs-logo-mark">iF</div>
    <div>
      <div class="ifs-logo-text">iFieldSmart</div>
      <div class="ifs-logo-sub">ScopeAI Platform</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Navigation pills as columns
    col1, col2, col3, col4, col_spacer = st.columns([1, 1, 1, 1, 6])
    with col1:
        if st.button("🏠 Projects", key="nav_projects",
                     type="primary" if page == "projects" else "secondary"):
            nav("projects")
    with col2:
        if proj and st.button("🤖 Agents", key="nav_agents",
                              type="primary" if page == "agents" else "secondary"):
            nav("agents")
    with col3:
        if proj and st.button("📐 Workspace", key="nav_workspace",
                              type="primary" if page == "workspace" else "secondary"):
            nav("workspace")
    with col4:
        if proj and st.button("💬 Chat", key="nav_chat",
                              type="primary" if page == "chat" else "secondary"):
            nav("chat")


# ─────────────────────────────────────────────────────────────────────────────
# Page 1: Project Selection
# ─────────────────────────────────────────────────────────────────────────────
def page_projects():
    # Hero
    st.markdown(
        """
<div class="ifs-hero">
  <h1>🏗️ iFieldSmart ScopeAI</h1>
  <p>AI-powered scope gap analysis for construction projects</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Search bar
    search = st.text_input(
        "Search projects", placeholder="Search by name, location, or PM…",
        key="proj_search", label_visibility="collapsed"
    )

    # Status filter
    col_f1, col_f2, col_f3, col_spacer = st.columns([1.2, 1.2, 1.2, 6])
    with col_f1:
        show_active = st.checkbox("Active", value=True, key="f_active")
    with col_f2:
        show_onhold = st.checkbox("On-Hold", value=True, key="f_onhold")
    with col_f3:
        show_completed = st.checkbox("Completed", value=True, key="f_completed")

    filtered = [
        p for p in PROJECTS
        if (search.lower() in p["name"].lower()
            or search.lower() in p["loc"].lower()
            or search.lower() in p["pm"].lower()
            or search == "")
        and (
            (p["status"] == "Active" and show_active)
            or (p["status"] == "On-Hold" and show_onhold)
            or (p["status"] == "Completed" and show_completed)
        )
    ]

    st.markdown(
        f'<div class="text-muted" style="margin-bottom:12px;">'
        f'{len(filtered)} project(s) found</div>',
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("No projects match the current filters.")
        return

    # Project cards: 3 per row
    for row_start in range(0, len(filtered), 3):
        cols = st.columns(3)
        for ci, proj in enumerate(filtered[row_start: row_start + 3]):
            with cols[ci]:
                _render_project_card(proj)


def _render_project_card(proj: dict):
    cfg = STATUS_CONFIG.get(proj["status"], STATUS_CONFIG["Active"])
    dot_cls = {
        "Active": "badge-dot-active",
        "On-Hold": "badge-dot-onhold",
        "Completed": "badge-dot-completed",
    }.get(proj["status"], "badge-dot-completed")
    badge_cls = {
        "Active": "badge-active",
        "On-Hold": "badge-onhold",
        "Completed": "badge-completed",
    }.get(proj["status"], "badge-completed")

    pct = proj["prog"]
    bar_color = "#22C55E" if pct == 100 else "#3B82F6" if pct > 50 else "#F59E0B"

    st.markdown(
        f"""
<div class="proj-card">
  <div class="proj-card-accent"></div>
  <span class="badge {badge_cls}">
    <span class="badge-dot {dot_cls}"></span>{proj["status"]}
  </span>
  <div class="proj-card-name">{proj["name"]}</div>
  <div class="proj-card-meta">📍 {proj["loc"]}</div>
  <div class="proj-card-meta" style="margin-top:4px;">👤 {proj["pm"]}</div>
  <span class="proj-card-type">{proj["type"]}</span>
  <div class="proj-progress-label">
    <span>Progress</span><span>{pct}%</span>
  </div>
  <div style="background:#E2E8F0;border-radius:4px;height:6px;">
    <div style="background:{bar_color};width:{pct}%;height:6px;border-radius:4px;"></div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(f"Open Project →", key=f"open_{proj['id']}",
                 use_container_width=True):
        st.session_state.selected_project = proj
        st.session_state.page = "agents"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page 2: Agent Selection
# ─────────────────────────────────────────────────────────────────────────────
def page_agents():
    proj = st.session_state.selected_project
    if not proj:
        st.warning("No project selected. Please choose a project first.")
        if st.button("← Back to Projects"):
            nav("projects")
        return

    # Breadcrumb
    st.markdown(
        f"""
<div class="breadcrumb">
  <a href="#">iFieldSmart</a>
  <span class="breadcrumb-sep">›</span>
  <a href="#">Projects</a>
  <span class="breadcrumb-sep">›</span>
  <span class="breadcrumb-current">{proj["name"]}</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Project summary strip
    cfg = STATUS_CONFIG.get(proj["status"], STATUS_CONFIG["Active"])
    st.markdown(
        f"""
<div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;
            padding:14px 18px;display:flex;align-items:center;gap:16px;margin-bottom:24px;">
  <div style="font-size:28px;">🏗️</div>
  <div style="flex:1;">
    <div style="font-size:15px;font-weight:700;color:#0F172A;">{proj["name"]}</div>
    <div style="font-size:12px;color:#64748B;">{proj["loc"]} · {proj["type"]} · PM: {proj["pm"]}</div>
  </div>
  <div style="font-size:13px;font-weight:700;color:#0F172A;">{proj["prog"]}%</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title" style="margin-bottom:16px;">Choose an Agent</div>',
        unsafe_allow_html=True,
    )

    # Agent grid: 3 columns
    for row_start in range(0, len(AGENTS), 3):
        cols = st.columns(3)
        for ci, agent in enumerate(AGENTS[row_start: row_start + 3]):
            with cols[ci]:
                _render_agent_card(agent)

    # Bottom chat input (cosmetic placeholder)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="banner-info">💬 Use the Chat tab to converse with the AI agent '
        "about any aspect of this project.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Open Chat Interface →", key="open_chat_from_agents"):
        nav("chat")


def _render_agent_card(agent: dict):
    is_drawings = agent["page"] == "workspace"
    st.markdown(
        f"""
<div class="agent-card {'active-agent' if is_drawings else ''}">
  <span class="agent-arrow">{'→' if is_drawings else ''}</span>
  <span class="agent-icon">{agent["icon"]}</span>
  <div class="agent-name">{agent["name"]}</div>
  <div class="agent-desc">{agent["desc"]}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    label = "Open Agent →" if is_drawings else "Coming Soon"
    disabled = not is_drawings
    if st.button(label, key=f"agent_{agent['name']}", disabled=disabled,
                 use_container_width=True,
                 type="primary" if is_drawings else "secondary"):
        if agent["page"]:
            st.session_state.page = agent["page"]
            st.session_state.workspace_view = "export"
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Page 3: Scope Workspace
# ─────────────────────────────────────────────────────────────────────────────
def page_workspace():
    proj = st.session_state.selected_project
    if not proj:
        st.warning("No project selected.")
        if st.button("← Back to Projects"):
            nav("projects")
        return

    pid = proj["project_id"]

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"""
<div class="sidebar-header">
  <div class="sidebar-title">{proj["name"]}</div>
  <div class="sidebar-sub">{proj["loc"]}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        tab_draw, tab_spec, tab_find = st.tabs(["📐 Drawings", "📄 Specs", "🔍 Findings"])

        with tab_draw:
            st.markdown(
                '<div style="font-size:11px;color:#94A3B8;margin-bottom:8px;">'
                "Drawing Sets</div>",
                unsafe_allow_html=True,
            )
            with st.spinner("Loading drawings…"):
                drawings_resp = api_get_drawings(pid)

            if drawings_resp and "error" not in drawings_resp:
                # API returns {"categories": {discipline: {drawings: [...], specs: [...]}}, ...}
                raw_cats = drawings_resp.get("categories", {})
                tree = {}
                for discipline, data in raw_cats.items():
                    names = []
                    if isinstance(data, dict):
                        for d in data.get("drawings", []):
                            names.append(d if isinstance(d, str) else d.get("drawingName", str(d)))
                        for s in data.get("specs", []):
                            names.append(s if isinstance(s, str) else s.get("drawingName", str(s)))
                    elif isinstance(data, list):
                        names = [x if isinstance(x, str) else str(x) for x in data]
                    if names:
                        tree[discipline] = names
                if not tree:
                    tree = MOCK_DRAWINGS
            else:
                tree = MOCK_DRAWINGS

            filter_text = st.text_input(
                "Filter", placeholder="Filter drawings…",
                key="draw_filter", label_visibility="collapsed"
            )
            for discipline, sheets in tree.items():
                filtered_sheets = [
                    s for s in sheets
                    if filter_text.lower() in s.lower() or filter_text == ""
                ]
                if filtered_sheets:
                    with st.expander(f"**{discipline}** ({len(filtered_sheets)})",
                                     expanded=False):
                        for sheet in filtered_sheets:
                            if st.button(sheet, key=f"sheet_{sheet}",
                                         use_container_width=True):
                                st.session_state.workspace_view = "drawing"
                                st.session_state.selected_drawing = sheet
                                st.rerun()

        with tab_spec:
            st.markdown(
                '<div style="font-size:12px;color:#94A3B8;padding:8px 0;">'
                "No spec sets loaded yet.</div>",
                unsafe_allow_html=True,
            )

        with tab_find:
            results = st.session_state.scope_results
            if results:
                for trade, res in list(results.items())[:10]:
                    items = res.get("scope_items", []) if isinstance(res, dict) else []
                    st.markdown(
                        f'<div style="font-size:12px;font-weight:600;color:#E2E8F0;'
                        f'margin-top:8px;">{trade} — {len(items)} items</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div style="font-size:12px;color:#94A3B8;padding:8px 0;">'
                    "Run scope gap analysis to see findings.</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown(
            '<div style="font-size:11px;color:#64748B;">👤 Field Engineer</div>',
            unsafe_allow_html=True,
        )

    # ── Main area ─────────────────────────────────────────────────────────────
    view = st.session_state.workspace_view

    # View toggle
    col_e, col_r, col_d, col_spacer = st.columns([1, 1.2, 1.2, 6])
    with col_e:
        if st.button("📊 Export", type="primary" if view == "export" else "secondary",
                     key="view_export"):
            st.session_state.workspace_view = "export"
            st.rerun()
    with col_r:
        if st.button("📋 Report", type="primary" if view == "report" else "secondary",
                     key="view_report"):
            st.session_state.workspace_view = "report"
            st.rerun()
    with col_d:
        if st.button("📐 Drawing", type="primary" if view == "drawing" else "secondary",
                     key="view_drawing"):
            st.session_state.workspace_view = "drawing"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if view == "export":
        _workspace_export_view(proj)
    elif view == "report":
        _workspace_report_view(proj)
    elif view == "drawing":
        _workspace_drawing_view(proj)


def _workspace_export_view(proj: dict):
    pid = proj["project_id"]

    col_h1, col_h2 = st.columns([6, 1])
    with col_h1:
        st.markdown(
            '<div class="section-title">📊 Export — Scope Gap Reports</div>',
            unsafe_allow_html=True,
        )
    with col_h2:
        if st.button("🔄 Refresh All", key="refresh_all"):
            st.session_state.trades_data = {}

    st.markdown(
        f'<div style="display:inline-block;background:#F1F5F9;border:1px solid #E2E8F0;'
        f'border-radius:6px;padding:4px 12px;font-size:12px;font-weight:600;color:#0F172A;'
        f'margin-bottom:16px;">{proj["name"]}</div>',
        unsafe_allow_html=True,
    )

    # Fetch trades
    if pid not in st.session_state.trades_data:
        with st.spinner("Loading trades…"):
            resp = api_get_trades(pid)
        if resp and "error" not in resp:
            raw_trades = resp.get("trades", resp) if isinstance(resp, dict) else resp
            # Normalize: API returns [{"trade": "Electrical", ...}] → ["Electrical", ...]
            if isinstance(raw_trades, list) and raw_trades and isinstance(raw_trades[0], dict):
                trades_list = [t.get("trade", str(t)) for t in raw_trades if t.get("trade")]
            else:
                trades_list = raw_trades
            st.session_state.trades_data[pid] = trades_list
        else:
            st.session_state.trades_data[pid] = MOCK_TRADES
            if resp is None:
                st.markdown(
                    '<div class="banner-warn">⚠️ Could not connect to the API. '
                    "Showing sample trade list.</div>",
                    unsafe_allow_html=True,
                )

    trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
    if isinstance(trades_list, dict):
        trades_list = list(trades_list.keys())

    # "Export All" and "Run All" buttons
    col_a, col_b, col_spacer = st.columns([1.2, 1.2, 8])
    with col_a:
        if st.button("⬇️ Export All", key="export_all"):
            with st.spinner("Preparing export…"):
                resp = _get(f"/api/scope-gap/projects/{pid}/export")
            if resp and "error" not in resp:
                st.success("Export prepared — check your downloads.")
            else:
                st.warning("Export endpoint not available. Please generate reports first.")
    with col_b:
        if st.button("🚀 Run All Trades", key="run_all"):
            with st.spinner("Queuing all trades…"):
                resp = api_run_all(pid)
            if resp and "error" not in resp:
                st.success(f"Queued {len(trades_list)} trades for processing.")
            else:
                st.warning("Could not connect to API. Please try again.")

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:12px;color:#64748B;margin-bottom:8px;">'
        f'{len(trades_list)} trade(s)</div>',
        unsafe_allow_html=True,
    )

    # Trade table
    for i, trade in enumerate(trades_list):
        has_result = trade in st.session_state.scope_results
        color = trade_color(i)

        col_dot, col_name, col_status, col_btn = st.columns([0.3, 4, 1.5, 1.5])
        with col_dot:
            st.markdown(
                f'<div style="width:12px;height:12px;border-radius:50%;'
                f'background:{color};margin-top:10px;"></div>',
                unsafe_allow_html=True,
            )
        with col_name:
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#0F172A;'
                f'padding-top:8px;">{trade}</div>',
                unsafe_allow_html=True,
            )
        with col_status:
            if has_result:
                st.markdown(
                    '<span style="background:#DCFCE7;color:#166534;font-size:11px;'
                    'font-weight:600;padding:3px 10px;border-radius:9999px;">'
                    "✓ Ready</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="background:#F1F5F9;color:#64748B;font-size:11px;'
                    'font-weight:600;padding:3px 10px;border-radius:9999px;">'
                    "— Pending</span>",
                    unsafe_allow_html=True,
                )
        with col_btn:
            if has_result:
                if st.button("View Report →", key=f"view_{trade}_{i}"):
                    st.session_state.selected_trade = trade
                    st.session_state.workspace_view = "report"
                    st.rerun()
            else:
                gen_lock_key = f"gen_lock_{trade}"
                is_generating = st.session_state.get(gen_lock_key, False)
                if st.button(
                    "Generating…" if is_generating else "Generate",
                    key=f"gen_{trade}_{i}",
                    disabled=is_generating,
                ):
                    # Quick health check before expensive pipeline call
                    health = api_health()
                    if health is None:
                        st.error("API server unreachable. Please check server status.")
                    elif "error" in (health or {}):
                        st.error(f"API unhealthy: {health.get('error')}")
                    else:
                        st.session_state[gen_lock_key] = True

                        # --- Progress bar UI ---
                        progress_bar = st.progress(0.0, text="Starting pipeline…")
                        status_text = st.empty()
                        status_text.markdown("🚀 **Connecting to pipeline…**")

                        result = api_run_scope_gap_streaming(
                            pid, trade, progress_bar, status_text,
                        )

                        st.session_state[gen_lock_key] = False

                        if result and "error" not in result:
                            st.session_state.scope_results[trade] = result
                            st.session_state.selected_trade = trade
                            progress_bar.progress(1.0, text="Complete!")
                            status_text.empty()
                            st.success(f"{trade} analysis complete!")
                            time.sleep(1)
                            st.rerun()
                        elif result is None:
                            progress_bar.empty()
                            st.error("Cannot connect to API. Please check server status.")
                        else:
                            progress_bar.empty()
                            st.error(f"Error: {result.get('error', 'Unknown error')}")

        st.markdown(
            '<div style="height:1px;background:#F1F5F9;margin:4px 0;"></div>',
            unsafe_allow_html=True,
        )


def _workspace_report_view(proj: dict):
    pid = proj["project_id"]
    trade = st.session_state.selected_trade

    # Back button + header
    col_back, col_title, col_export = st.columns([1, 5, 1.5])
    with col_back:
        if st.button("← Back", key="back_to_export"):
            st.session_state.workspace_view = "export"
            st.rerun()
    with col_title:
        if trade:
            st.markdown(
                f'<div class="section-title">📋 {trade} — Scope of Work</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="section-title">📋 Scope Report</div>',
                unsafe_allow_html=True,
            )
    with col_export:
        st.button("⬇️ Export DOCX", key="export_docx")

    if not trade:
        # Trade selector
        trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
        if isinstance(trades_list, dict):
            trades_list = list(trades_list.keys())
        selected = st.selectbox("Select trade", trades_list, key="report_trade_sel")
        if st.button("Load Report", key="load_report"):
            st.session_state.selected_trade = selected
            # Fetch if not cached
            if selected not in st.session_state.scope_results:
                with st.spinner(f"Generating {selected} scope gap…"):
                    result = api_run_scope_gap(pid, selected)
                if result and "error" not in result:
                    st.session_state.scope_results[selected] = result
                elif result is None:
                    st.error("Cannot connect to API.")
                    return
                else:
                    st.error(result.get("error", "Unknown error"))
                    return
            st.rerun()
        return

    # Load / generate result
    if trade not in st.session_state.scope_results:
        with st.spinner(f"Generating {trade} scope gap analysis…"):
            result = api_run_scope_gap(pid, trade)
        if result and "error" not in result:
            st.session_state.scope_results[trade] = result
        elif result is None:
            st.markdown(
                '<div class="banner-error">Cannot connect to API. '
                "Please check server status.</div>",
                unsafe_allow_html=True,
            )
            return
        else:
            st.error(result.get("error", "Unknown error"))
            return

    result = st.session_state.scope_results[trade]
    if not isinstance(result, dict):
        st.error("Unexpected result format from API.")
        return

    # ── Score cards ──────────────────────────────────────────────────────────
    # Pipeline returns: completeness: {overall_pct, drawing_coverage_pct, csi_coverage_pct}
    #                   quality: {accuracy_score, ...}
    #                   pipeline_stats: {attempts, tokens_used, total_ms, ...}
    completeness_data = result.get("completeness", {})
    quality_data = result.get("quality", {})
    stats_data = result.get("pipeline_stats", {})

    completeness_pct = completeness_data.get("overall_pct", 0) if isinstance(completeness_data, dict) else 0
    quality_score = quality_data.get("accuracy_score", 0) if isinstance(quality_data, dict) else 0
    drawing_cov = completeness_data.get("drawing_coverage_pct", 0) if isinstance(completeness_data, dict) else 0
    attempts_count = stats_data.get("attempts", 1) if isinstance(stats_data, dict) else 1
    items_count = len(result.get("items", []))

    s1, s2, s3, s4 = st.columns(4)
    def _score_card(col, label, value, color):
        pct = value * 100 if value <= 1 else value
        with col:
            st.markdown(
                f'<div class="score-card">'
                f'<div class="score-label">{label}</div>'
                f'<div class="score-value">{pct:.0f}%</div>'
                f'{score_bar_html(value if value <= 1 else value / 100, color)}'
                f"</div>",
                unsafe_allow_html=True,
            )

    _score_card(s1, "Completeness", completeness_pct, "#22C55E")
    _score_card(s2, "Quality", quality_score, "#3B82F6")
    _score_card(s3, "Drawing Coverage", drawing_cov, "#8B5CF6")
    with s4:
        st.markdown(
            f'<div class="score-card">'
            f'<div class="score-label">Items / Attempts</div>'
            f'<div class="score-value">{items_count} / {attempts_count}</div>'
            f'<div class="score-sub">Scope items extracted</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Document downloads ───────────────────────────────────────────────────
    documents = result.get("documents", {})
    if isinstance(documents, dict) and any(documents.get(k) for k in ("word_path", "pdf_path", "csv_path", "json_path")):
        st.markdown(
            '<div style="display:flex;gap:8px;margin:8px 0 16px;">',
            unsafe_allow_html=True,
        )
        doc_cols = st.columns(4)
        doc_labels = [
            ("word_path", "📄 Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("pdf_path", "📕 PDF", "application/pdf"),
            ("csv_path", "📊 CSV", "text/csv"),
            ("json_path", "📋 JSON", "application/json"),
        ]
        for col, (key, label, _mime) in zip(doc_cols, doc_labels):
            doc_path = documents.get(key)
            if doc_path:
                with col:
                    st.markdown(
                        f'<div style="background:#F0F9FF;border:1px solid #BAE6FD;'
                        f'border-radius:8px;padding:8px 12px;text-align:center;'
                        f'font-size:12px;font-weight:600;color:#0369A1;">'
                        f'{label}</div>',
                        unsafe_allow_html=True,
                    )
    else:
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Source documents sidebar ──────────────────────────────────────────────
    # Collect unique source drawings from all items
    all_source_drawings = _extract_source_drawings(result)

    col_main, col_ref = st.columns([3, 1.2])

    with col_main:
        _render_scope_items(result, trade)

    with col_ref:
        if st.session_state.ref_panel_open:
            _render_reference_panel()
        else:
            _render_source_documents_sidebar(all_source_drawings, result)


def _render_scope_items(result: dict, trade: str):
    scope_items = result.get("items", result.get("scope_items", []))
    ambiguities = result.get("ambiguities", [])
    gotchas = result.get("gotchas", [])

    # ── Job Specific Items ──
    st.markdown(
        f'<div class="section-header">'
        f'<span class="section-title">Job Specific Items</span>'
        f'<span class="text-muted">{len(scope_items)} items</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    if not scope_items:
        st.markdown(
            '<div class="banner-info">No scope items found for this trade.</div>',
            unsafe_allow_html=True,
        )
    else:
        # Group items by drawing_name for clarity
        grouped: dict[str, list] = {}
        for item in scope_items:
            if isinstance(item, dict):
                dn = item.get("drawing_name", "Unknown")
            else:
                dn = "Unknown"
            grouped.setdefault(dn, []).append(item)

        for drawing_name, items_in_drawing in grouped.items():
            drawing_title = ""
            if items_in_drawing and isinstance(items_in_drawing[0], dict):
                drawing_title = items_in_drawing[0].get("drawing_title", "") or ""

            header_text = f"📄 {drawing_name}"
            if drawing_title:
                header_text += f" — {drawing_title}"

            with st.expander(f"{header_text} ({len(items_in_drawing)} items)", expanded=True):
                for i, item in enumerate(items_in_drawing):
                    text = item if isinstance(item, str) else item.get("text", str(item))
                    # Build source reference from ClassifiedItem fields
                    source_ref = _build_source_ref(item) if isinstance(item, dict) else []

                    col_text, col_meta, col_link = st.columns([6, 2.5, 0.5])
                    with col_text:
                        st.markdown(
                            f'<div class="scope-item-text">{text}</div>',
                            unsafe_allow_html=True,
                        )
                    with col_meta:
                        if isinstance(item, dict):
                            csi = item.get("csi_code", "") or item.get("csi_division", "")
                            conf = item.get("confidence", 0)
                            meta_parts = []
                            if csi:
                                meta_parts.append(f'<span style="background:#EFF6FF;color:#1E40AF;'
                                                  f'border-radius:4px;padding:2px 6px;font-size:10px;'
                                                  f'font-weight:600;">{csi}</span>')
                            if conf:
                                pct = conf * 100 if conf <= 1 else conf
                                meta_parts.append(f'<span style="color:#64748B;font-size:10px;">'
                                                  f'{pct:.0f}%</span>')
                            page = item.get("page")
                            if page:
                                meta_parts.append(f'<span style="color:#94A3B8;font-size:10px;">'
                                                  f'p.{page}</span>')
                            if meta_parts:
                                st.markdown(
                                    f'<div style="display:flex;gap:6px;align-items:center;'
                                    f'padding-top:4px;">{"".join(meta_parts)}</div>',
                                    unsafe_allow_html=True,
                                )
                    with col_link:
                        if st.button("🔗", key=f"ref_{trade}_{drawing_name}_{i}",
                                     help="View source references"):
                            st.session_state.ref_panel_open = True
                            st.session_state.ref_panel_items = source_ref
                            st.rerun()

                    st.markdown(
                        '<div style="height:1px;background:#F1F5F9;margin:2px 0;"></div>',
                        unsafe_allow_html=True,
                    )

    # ── Ambiguities ──
    if ambiguities:
        with st.expander(f"⚠️ Trade Ambiguities ({len(ambiguities)})", expanded=False):
            for amb in ambiguities:
                if isinstance(amb, dict):
                    text = amb.get("text", str(amb))
                    competing = amb.get("competing_trades", [])
                    severity = amb.get("severity", "medium")
                    sev_color = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#DBEAFE"}.get(severity, "#FEF3C7")
                    refs = amb.get("drawing_refs", [])
                    st.markdown(
                        f'<div style="background:{sev_color};border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">'
                        f'<b>{text}</b>'
                        f'{"<br><span style=color:#64748B;>Competing trades: " + ", ".join(competing) + "</span>" if competing else ""}'
                        f'{"<br><span style=color:#94A3B8;font-size:10px;>Drawings: " + ", ".join(refs) + "</span>" if refs else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="banner-warn" style="margin-bottom:6px;">{amb}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Gotchas ──
    if gotchas:
        with st.expander(f"🎯 Hidden Risks / Gotchas ({len(gotchas)})", expanded=False):
            for g in gotchas:
                if isinstance(g, dict):
                    risk_type = g.get("risk_type", "")
                    desc = g.get("description", g.get("text", str(g)))
                    severity = g.get("severity", "medium")
                    recommendation = g.get("recommendation", "")
                    affected = g.get("affected_trades", [])
                    refs = g.get("drawing_refs", [])
                    sev_color = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#DBEAFE"}.get(severity, "#FEF3C7")
                    st.markdown(
                        f'<div style="background:{sev_color};border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">'
                        f'{"<b>[" + risk_type.upper() + "]</b> " if risk_type else ""}'
                        f'{desc}'
                        f'{"<br><span style=color:#166534;font-size:11px;>💡 " + recommendation + "</span>" if recommendation else ""}'
                        f'{"<br><span style=color:#64748B;font-size:10px;>Affected: " + ", ".join(affected) + "</span>" if affected else ""}'
                        f'{"<br><span style=color:#94A3B8;font-size:10px;>Drawings: " + ", ".join(refs) + "</span>" if refs else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="background:#FEF3C7;border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">{g}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Raw response preview ──
    with st.expander("🔧 Raw API Response", expanded=False):
        st.json(result)


def _build_source_ref(item: dict) -> list[dict]:
    """Build source reference list from a ClassifiedItem dict.

    ClassifiedItem has: drawing_name, drawing_title, drawing_refs, page,
    source_snippet, source_type, source_record_id.
    """
    refs = []
    drawing_name = item.get("drawing_name", "")
    drawing_title = item.get("drawing_title", "")
    page = item.get("page")
    snippet = item.get("source_snippet", "")
    source_type = item.get("source_type", "drawing")
    record_id = item.get("source_record_id", "")

    # Primary source: the item's own drawing
    if drawing_name:
        refs.append({
            "drawing_name": drawing_name,
            "drawing_title": drawing_title or "",
            "page": str(page) if page else "",
            "source_snippet": snippet,
            "source_type": source_type,
            "record_id": record_id,
        })

    # Additional cross-references from drawing_refs
    for ref_name in item.get("drawing_refs", []):
        if ref_name and ref_name != drawing_name:
            refs.append({
                "drawing_name": ref_name,
                "drawing_title": "",
                "page": "",
                "source_snippet": "",
                "source_type": "cross-reference",
                "record_id": "",
            })

    return refs


def _extract_source_drawings(result: dict) -> list[dict]:
    """Extract unique source drawings from all items in the result.

    Returns a sorted list of dicts with drawing_name, drawing_title,
    item_count, and source_type.
    """
    drawing_map: dict[str, dict] = {}

    for item in result.get("items", []):
        if not isinstance(item, dict):
            continue
        dn = item.get("drawing_name", "")
        if not dn:
            continue
        if dn not in drawing_map:
            drawing_map[dn] = {
                "drawing_name": dn,
                "drawing_title": item.get("drawing_title", "") or "",
                "item_count": 0,
                "source_type": item.get("source_type", "drawing"),
                "pages": set(),
            }
        drawing_map[dn]["item_count"] += 1
        page = item.get("page")
        if page:
            drawing_map[dn]["pages"].add(str(page))

    # Convert sets to sorted lists for display
    drawings = []
    for d in sorted(drawing_map.values(), key=lambda x: x["drawing_name"]):
        d["pages"] = sorted(d["pages"])
        drawings.append(d)
    return drawings


def _render_source_documents_sidebar(source_drawings: list[dict], result: dict):
    """Render the source documents sidebar showing all drawings referenced."""
    st.markdown(
        '<div style="font-size:14px;font-weight:700;color:#0F172A;'
        'margin-bottom:12px;">📎 Source Documents</div>',
        unsafe_allow_html=True,
    )

    if not source_drawings:
        st.markdown(
            '<div style="font-size:12px;color:#94A3B8;">No source documents found.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="font-size:11px;color:#64748B;margin-bottom:8px;">'
        f'{len(source_drawings)} drawing(s) referenced</div>',
        unsafe_allow_html=True,
    )

    for d in source_drawings:
        title = d.get("drawing_title", "")
        pages = d.get("pages", [])
        count = d.get("item_count", 0)
        src_type = d.get("source_type", "drawing")
        icon = "📐" if src_type == "drawing" else "📄"

        page_text = f"p.{', '.join(pages)}" if pages else ""
        subtitle_parts = []
        if page_text:
            subtitle_parts.append(page_text)
        subtitle_parts.append(f"{count} item{'s' if count != 1 else ''}")
        subtitle = " · ".join(subtitle_parts)

        st.markdown(
            f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:8px;'
            f'padding:10px 12px;margin-bottom:6px;">'
            f'<div style="font-size:12px;font-weight:600;color:#0F172A;">'
            f'{icon} {d["drawing_name"]}</div>'
            f'{"<div style=font-size:11px;color:#64748B;>" + title + "</div>" if title else ""}'
            f'<div style="font-size:10px;color:#94A3B8;margin-top:2px;">{subtitle}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Show pipeline stats summary at bottom
    stats = result.get("pipeline_stats", {})
    if isinstance(stats, dict):
        total_ms = stats.get("total_ms", 0)
        tokens = stats.get("tokens_used", 0)
        cost = stats.get("estimated_cost_usd", 0)
        records = stats.get("records_processed", 0)

        st.markdown('<div style="height:1px;background:#E2E8F0;margin:12px 0;"></div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;font-weight:600;color:#64748B;margin-bottom:6px;">'
            '⚡ Pipeline Stats</div>',
            unsafe_allow_html=True,
        )
        stat_lines = []
        if total_ms:
            stat_lines.append(f"⏱ {total_ms / 1000:.1f}s")
        if records:
            stat_lines.append(f"📊 {records} records")
        if tokens:
            stat_lines.append(f"🔤 {tokens:,} tokens")
        if cost:
            stat_lines.append(f"💰 ${cost:.4f}")
        st.markdown(
            '<div style="font-size:10px;color:#94A3B8;">' +
            "<br>".join(stat_lines) + '</div>',
            unsafe_allow_html=True,
        )


def _render_reference_panel():
    """Render the item-level source reference panel (opened by clicking 🔗)."""
    items = st.session_state.ref_panel_items

    st.markdown(
        '<div style="font-size:14px;font-weight:700;color:#0F172A;'
        'margin-bottom:12px;">📎 Item References</div>',
        unsafe_allow_html=True,
    )

    if st.button("✕ Close", key="close_ref_panel"):
        st.session_state.ref_panel_open = False
        st.session_state.ref_panel_items = []
        st.rerun()

    if not items:
        st.markdown(
            '<div style="font-size:12px;color:#94A3B8;">No source references attached to this item.</div>',
            unsafe_allow_html=True,
        )
        return

    for src in items:
        if isinstance(src, dict):
            name = src.get("drawing_name", "Unknown")
            title = src.get("drawing_title", "")
            page_ref = src.get("page", "")
            snippet = src.get("source_snippet", "")
            src_type = src.get("source_type", "drawing")
        else:
            name = str(src)
            title = ""
            page_ref = ""
            snippet = ""
            src_type = "drawing"

        icon = "📐" if src_type == "drawing" else ("🔀" if src_type == "cross-reference" else "📄")

        st.markdown(
            f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:8px;'
            f'padding:10px 12px;margin-bottom:6px;">'
            f'<div style="font-size:12px;font-weight:600;color:#0F172A;">{icon} {name}</div>'
            f'{"<div style=font-size:11px;color:#64748B;>" + title + "</div>" if title else ""}'
            f'{"<div style=font-size:10px;color:#94A3B8;>Page: " + str(page_ref) + "</div>" if page_ref else ""}'
            f'{"<div style=font-size:10px;color:#64748B;margin-top:4px;font-style:italic;>" + snippet[:200] + "</div>" if snippet else ""}'
            f"</div>",
            unsafe_allow_html=True,
        )


def _workspace_drawing_view(proj: dict):
    pid = proj["project_id"]
    drawing = st.session_state.get("selected_drawing", "A-001 Site Plan")

    # Toolbar
    st.markdown(
        f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;'
        f'padding:10px 16px;display:flex;align-items:center;gap:16px;margin-bottom:16px;">'
        f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{drawing}</span>'
        f'<span style="color:#E2E8F0;">|</span>'
        f'<span style="font-size:11px;color:#64748B;">Toolbar:</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">↖ Select</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">✋ Move</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">🔍 Zoom</span>'
        f'<span style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">🖊 Highlight</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    col_canvas, col_findings = st.columns([3, 1])

    with col_canvas:
        st.markdown(
            f"""
<div class="drawing-canvas">
  <div style="font-size:48px;opacity:0.15;">📐</div>
  <div style="font-size:14px;font-weight:700;color:#94A3B8;">{drawing}</div>
  <div style="font-size:12px;color:#CBD5E1;">Project {pid} · Drawing Viewer</div>
  <div style="font-size:11px;color:#E2E8F0;margin-top:8px;">
    PDF rendering requires a CAD/PDF integration
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🖊 Draw a Highlight", key="draw_highlight"):
            st.info("Highlight drawing tools require PDF.js integration. "
                    "Use the API to save highlight coordinates.")

    with col_findings:
        st.markdown(
            '<div style="background:#1E293B;border-radius:10px;padding:12px;'
            'min-height:400px;">',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:#F8FAFC;margin-bottom:10px;">'
            "🔍 Findings</div>",
            unsafe_allow_html=True,
        )

        # Show findings from scope results if available
        findings_shown = 0
        for trade, res in list(st.session_state.scope_results.items())[:3]:
            items = res.get("scope_items", []) if isinstance(res, dict) else []
            for it in items[:3]:
                text = it if isinstance(it, str) else it.get("text", str(it))
                st.checkbox(
                    text[:60] + ("…" if len(text) > 60 else ""),
                    key=f"find_{trade}_{text[:20]}",
                )
                findings_shown += 1

        if findings_shown == 0:
            st.markdown(
                '<div style="font-size:11px;color:#64748B;margin-top:8px;">'
                "Generate scope gap reports to see findings here.</div>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

        # Trade dropdown
        trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
        if isinstance(trades_list, dict):
            trades_list = list(trades_list.keys())
        st.selectbox("Trade Filter", ["All"] + list(trades_list),
                     key="drawing_trade_filter")


# ─────────────────────────────────────────────────────────────────────────────
# Page 4: Chat Interface
# ─────────────────────────────────────────────────────────────────────────────
def page_chat():
    proj = st.session_state.selected_project
    if not proj:
        st.warning("No project selected.")
        if st.button("← Back to Projects"):
            nav("projects")
        return

    pid = proj["project_id"]

    # Header
    st.markdown(
        f"""
<div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;
            padding:14px 18px;display:flex;align-items:center;gap:12px;margin-bottom:16px;">
  <div style="font-size:24px;">💬</div>
  <div>
    <div style="font-size:14px;font-weight:700;color:#0F172A;">
      Construction AI Agent</div>
    <div style="font-size:12px;color:#64748B;">{proj["name"]} · Ask anything about scope, trades, or documents</div>
  </div>
  <div style="margin-left:auto;">
    <span style="background:#DCFCE7;color:#166534;font-size:11px;font-weight:600;
                 padding:3px 10px;border-radius:9999px;">● Online</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Chat history
    messages = st.session_state.chat_messages
    if not messages:
        st.markdown(
            '<div style="text-align:center;padding:32px;color:#94A3B8;">'
            '<div style="font-size:32px;margin-bottom:8px;">💬</div>'
            '<div style="font-size:13px;font-weight:600;">Start a conversation</div>'
            '<div style="font-size:12px;margin-top:4px;">Ask about scope gaps, trades, drawings, or any project detail.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            ts = msg.get("time", "")
            if role == "user":
                st.markdown(
                    f'<div style="display:flex;justify-content:flex-end;margin-bottom:8px;">'
                    f'<div class="chat-msg-user">{content}'
                    f'<div class="chat-msg-time">{ts}</div></div></div>',
                    unsafe_allow_html=True,
                )
            else:
                # Check for document links
                doc_url = msg.get("doc_url")
                doc_name = msg.get("doc_name")
                doc_html = ""
                if doc_url:
                    doc_html = (
                        f'<div style="margin-top:8px;background:#F1F5F9;border-radius:6px;'
                        f'padding:8px 10px;font-size:11px;">'
                        f'📄 <a href="{doc_url}" target="_blank" style="color:#3B82F6;">'
                        f"{doc_name or 'Download Document'}</a></div>"
                    )
                st.markdown(
                    f'<div style="display:flex;justify-content:flex-start;margin-bottom:8px;">'
                    f'<div class="chat-msg-agent">'
                    f'<div style="font-size:10px;font-weight:600;color:#C4841D;margin-bottom:4px;">AI Agent</div>'
                    f"{content}{doc_html}"
                    f'<div class="chat-msg-time">{ts}</div></div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("---")

    # Quick prompts
    st.markdown(
        '<div style="font-size:11px;color:#64748B;margin-bottom:8px;">Quick prompts:</div>',
        unsafe_allow_html=True,
    )
    qp_col1, qp_col2, qp_col3, qp_col4 = st.columns(4)
    quick_prompts = [
        "What are the main electrical scope gaps?",
        "Summarize plumbing requirements",
        "List HVAC ambiguities",
        "Generate scope document",
    ]
    for qi, (col, qp) in enumerate(zip([qp_col1, qp_col2, qp_col3, qp_col4], quick_prompts)):
        with col:
            if st.button(qp, key=f"qp_{qi}", use_container_width=True):
                _send_chat(pid, qp)

    # Chat input
    with st.form("chat_form", clear_on_submit=True):
        col_inp, col_send = st.columns([8, 1])
        with col_inp:
            user_input = st.text_input(
                "Message", placeholder="Ask about scope gaps, drawings, trades…",
                key="chat_input", label_visibility="collapsed"
            )
        with col_send:
            submitted = st.form_submit_button("Send →", use_container_width=True,
                                              type="primary")

    if submitted and user_input.strip():
        _send_chat(pid, user_input.strip())

    # Clear history
    if messages and st.button("🗑️ Clear History", key="clear_chat"):
        st.session_state.chat_messages = []
        st.session_state.chat_session_id = None
        st.rerun()


def _send_chat(pid: int, text: str):
    ts = time.strftime("%H:%M")
    st.session_state.chat_messages.append({
        "role": "user", "content": text, "time": ts
    })

    with st.spinner("AI Agent is thinking…"):
        resp = api_chat(
            pid, text, st.session_state.chat_session_id
        )

    if resp is None:
        reply = ("Sorry, I cannot connect to the API right now. "
                 "Please check the server status and try again.")
        doc_url = None
        doc_name = None
    elif "error" in resp:
        reply = f"Error: {resp['error']}"
        doc_url = None
        doc_name = None
    else:
        reply = (
            resp.get("answer")
            or resp.get("response")
            or resp.get("message")
            or str(resp)
        )
        session_id = resp.get("session_id")
        if session_id:
            st.session_state.chat_session_id = session_id
        doc_url = resp.get("document_url") or resp.get("download_url")
        doc_name = resp.get("document_name") or resp.get("filename")

    msg = {"role": "agent", "content": reply, "time": time.strftime("%H:%M")}
    if doc_url:
        msg["doc_url"] = doc_url
        msg["doc_name"] = doc_name
    st.session_state.chat_messages.append(msg)
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# API Status Banner
# ─────────────────────────────────────────────────────────────────────────────
def render_api_status():
    health = api_health()
    if health is None:
        st.markdown(
            '<div class="banner-warn" style="margin:8px 0;">⚠️ API server unreachable at '
            f'{API_BASE} — showing cached/sample data</div>',
            unsafe_allow_html=True,
        )
    elif isinstance(health, dict) and health.get("status") == "ok":
        pass  # healthy — no banner
    else:
        st.markdown(
            '<div class="banner-info">ℹ️ API responded but status is unclear. '
            "Some features may be limited.</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
def main():
    inject_css()
    render_navbar()

    st.markdown('<div style="max-width:1400px;margin:0 auto;padding:16px 24px;">', unsafe_allow_html=True)

    render_api_status()

    page = st.session_state.page

    if page == "projects":
        page_projects()
    elif page == "agents":
        page_agents()
    elif page == "workspace":
        page_workspace()
    elif page == "chat":
        page_chat()
    else:
        page_projects()

    st.markdown("</div>", unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div style="text-align:center;font-size:11px;color:#CBD5E1;padding:24px 0 12px;">'
        "iFieldSmart ScopeAI · Construction Intelligence Platform · "
        f"v3.0 · {API_BASE}</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
