"""
Page 2: Agent Selection.
"""
import streamlit as st

from config import AGENTS
from utils.session import nav


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
