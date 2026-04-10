"""
Page 4: Chat Interface.
"""
import streamlit as st

from components.chat import _send_chat, render_chat_messages, render_document_history
from utils.session import nav


def page_chat():
    proj = st.session_state.selected_project
    if not proj:
        st.warning("No project selected.")
        if st.button("← Back to Projects"):
            nav("projects")
        return

    pid = proj["project_id"]

    # Sidebar: Document History
    with st.sidebar:
        st.markdown("### Document History")
        render_document_history(
            api_base_url=st.session_state.get("api_base_url", "http://localhost:8003"),
            project_id=st.session_state.get("project_id"),
        )

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
    render_chat_messages(messages)

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
