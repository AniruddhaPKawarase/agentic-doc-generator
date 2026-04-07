"""
iFieldSmart ScopeAI — Streamlit UI
Construction Intelligence Agent frontend

Usage:
    pip install -r requirements.txt
    streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="iFieldSmart ScopeAI",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from utils.session import init_session
from styles.theme import inject_css
from components.navbar import render_navbar
from pages.projects import page_projects
from pages.agents import page_agents
from pages.workspace import page_workspace
from pages.chat import page_chat
from api.client import health as api_health
from config import API_BASE

init_session()


def render_api_status():
    h = api_health()
    if h is None:
        st.markdown(
            f'<div class="banner-warn" style="margin:8px 0;">API unreachable at {API_BASE}</div>',
            unsafe_allow_html=True,
        )


def main():
    inject_css()
    render_navbar()
    st.markdown('<div style="max-width:1400px;margin:0 auto;padding:16px 24px;">',
                unsafe_allow_html=True)
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
    st.markdown(
        f'<div style="text-align:center;font-size:11px;color:#475569;padding:24px 0 12px;">'
        f'iFieldSmart ScopeAI v3.1 | {API_BASE}</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
