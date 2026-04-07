"""
Chat message rendering and send helper.
"""
import time

import streamlit as st

from api.client import _post


def render_chat_messages(messages: list[dict]):
    """Render the chat history."""
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


def _send_chat(pid: int, text: str):
    """Send a chat message and append both user and agent messages to session."""
    ts = time.strftime("%H:%M")
    st.session_state.chat_messages.append({
        "role": "user", "content": text, "time": ts
    })

    with st.spinner("AI Agent is thinking…"):
        payload = {"project_id": pid, "query": text}
        if st.session_state.chat_session_id:
            payload["session_id"] = st.session_state.chat_session_id
        resp = _post("/api/chat", payload)

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
