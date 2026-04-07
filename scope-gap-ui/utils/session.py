"""
Session state helpers and shared utility functions.
"""
import streamlit as st


def init_session():
    """Initialise session-state keys with sensible defaults."""
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


def nav(page: str):
    """Navigate to a page and trigger a rerun."""
    st.session_state.page = page
    st.rerun()


def score_bar_html(value: float, color: str = "#3B82F6") -> str:
    """Return HTML for a small horizontal progress bar."""
    pct = min(max(value * 100, 0), 100)
    return (
        f'<div style="background:#E2E8F0;border-radius:4px;height:8px;width:100%;">'
        f'<div style="background:{color};width:{pct:.1f}%;height:8px;border-radius:4px;"></div>'
        f"</div>"
    )
