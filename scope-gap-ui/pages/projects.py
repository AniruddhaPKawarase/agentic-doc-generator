"""
Page 1: Project Selection.
"""
import streamlit as st

from config import PROJECTS, STATUS_CONFIG


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
