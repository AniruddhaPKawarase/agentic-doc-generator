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
REQUEST_TIMEOUT = 60

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
        return {"error": "Request timed out"}
    except Exception as exc:
        return {"error": str(exc)}


def _post(path: str, payload: dict) -> Optional[dict]:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload,
                          timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except Exception as exc:
        return {"error": str(exc)}


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
    return _post("/api/scope-gap/generate", {"project_id": project_id, "trade": trade})


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
                tree = drawings_resp
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
            trades_list = resp.get("trades", resp) if isinstance(resp, dict) else resp
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
                if st.button(f"Generate", key=f"gen_{trade}_{i}"):
                    with st.spinner(f"Generating {trade} scope gap…"):
                        result = api_run_scope_gap(pid, trade)
                    if result and "error" not in result:
                        st.session_state.scope_results[trade] = result
                        st.session_state.selected_trade = trade
                        st.success(f"{trade} analysis complete!")
                        st.rerun()
                    elif result is None:
                        st.error("Cannot connect to API. Please check server status.")
                    else:
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
    scores = result.get("scores", {})
    completeness = result.get("completeness_score", scores.get("completeness", 0))
    quality = result.get("quality_score", scores.get("quality", 0))
    confidence = result.get("confidence", scores.get("confidence", 0))
    attempts_count = result.get("attempts", 1)

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

    _score_card(s1, "Completeness", completeness, "#22C55E")
    _score_card(s2, "Quality", quality, "#3B82F6")
    _score_card(s3, "Confidence", confidence, "#8B5CF6")
    with s4:
        st.markdown(
            f'<div class="score-card">'
            f'<div class="score-label">Attempts</div>'
            f'<div class="score-value">{attempts_count}</div>'
            f'<div class="score-sub">Backpropagation loops</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Reference panel toggle ────────────────────────────────────────────────
    col_main, col_ref = (
        st.columns([3, 1]) if st.session_state.ref_panel_open else (st, None)
    )
    if col_ref is None:
        _render_scope_items(result, trade)
    else:
        with col_main:
            _render_scope_items(result, trade)
        with col_ref:
            _render_reference_panel()


def _render_scope_items(result: dict, trade: str):
    scope_items = result.get("scope_items", result.get("items", []))
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
        for i, item in enumerate(scope_items):
            text = item if isinstance(item, str) else item.get("text", item.get("description", str(item)))
            sources = item.get("sources", []) if isinstance(item, dict) else []

            col_chk, col_text, col_link = st.columns([0.3, 8, 0.5])
            with col_chk:
                st.checkbox("", key=f"scope_chk_{trade}_{i}", label_visibility="collapsed")
            with col_text:
                st.markdown(
                    f'<div class="scope-item-text">{text}</div>',
                    unsafe_allow_html=True,
                )
            with col_link:
                if st.button("🔗", key=f"ref_{trade}_{i}",
                             help="View source references"):
                    st.session_state.ref_panel_open = True
                    st.session_state.ref_panel_items = sources
                    st.rerun()

            st.markdown(
                '<div style="height:1px;background:#F8FAFC;margin:2px 0;"></div>',
                unsafe_allow_html=True,
            )

    # ── Ambiguities ──
    if ambiguities:
        with st.expander(f"⚠️ Ambiguities ({len(ambiguities)})", expanded=False):
            for amb in ambiguities:
                text = amb if isinstance(amb, str) else amb.get("text", str(amb))
                st.markdown(
                    f'<div class="banner-warn" style="margin-bottom:6px;">{text}</div>',
                    unsafe_allow_html=True,
                )

    # ── Gotchas ──
    if gotchas:
        with st.expander(f"🎯 Gotchas ({len(gotchas)})", expanded=False):
            for g in gotchas:
                text = g if isinstance(g, str) else g.get("text", str(g))
                severity = g.get("severity", "medium") if isinstance(g, dict) else "medium"
                color_map = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#DBEAFE"}
                bg = color_map.get(severity, "#FEF3C7")
                st.markdown(
                    f'<div style="background:{bg};border-radius:8px;padding:10px 12px;'
                    f'margin-bottom:6px;font-size:12px;">{text}</div>',
                    unsafe_allow_html=True,
                )

    # ── Raw response preview ──
    with st.expander("🔧 Raw API Response", expanded=False):
        st.json(result)


def _render_reference_panel():
    items = st.session_state.ref_panel_items

    st.markdown(
        '<div class="ref-panel-title">📎 Source References</div>',
        unsafe_allow_html=True,
    )

    if st.button("✕ Close", key="close_ref_panel"):
        st.session_state.ref_panel_open = False
        st.session_state.ref_panel_items = []
        st.rerun()

    if not items:
        st.markdown(
            '<div class="text-muted">No source references attached to this item.</div>',
            unsafe_allow_html=True,
        )
        return

    for src in items:
        name = src.get("name", src.get("drawing_name", "Unknown")) if isinstance(src, dict) else str(src)
        page_ref = src.get("page", src.get("sheet", "")) if isinstance(src, dict) else ""
        s3_path = src.get("s3_path", "") if isinstance(src, dict) else ""

        st.markdown(
            f'<div class="ref-card">'
            f'<div class="ref-card-name">📄 {name}</div>'
            f'{"<div class=ref-card-meta>Sheet: " + page_ref + "</div>" if page_ref else ""}'
            f'{"<div class=ref-card-meta style=word-break:break-all;>" + s3_path + "</div>" if s3_path else ""}'
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
