"""
Top navigation bar.
"""
import streamlit as st

from utils.session import nav


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
