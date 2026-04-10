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

                # Warnings/fallback alert banner
                api_warnings = msg.get("warnings", [])
                api_version = msg.get("api_version", "")

                if api_warnings:
                    for w in api_warnings:
                        st.warning(w)
                if api_version.startswith("summary"):
                    st.error(
                        "Using fallback API -- source references may be unavailable. "
                        "Contact support if this persists."
                    )

                # Raw API data expander
                raw_data = msg.get("raw_records")
                if raw_data:
                    with st.expander("Raw API Data", expanded=False):
                        import pandas as pd
                        all_cols = list(raw_data[0].keys()) if raw_data else []
                        visible_cols = st.multiselect(
                            "Visible columns",
                            all_cols,
                            default=all_cols,
                            key=f"cols_{msg.get('time', '')}_{id(msg)}",
                        )
                        if visible_cols:
                            df = pd.DataFrame(raw_data)[visible_cols]
                            st.dataframe(df, use_container_width=True, height=400)
                            csv = df.to_csv(index=False)
                            st.download_button(
                                "Download CSV", csv, "raw_data.csv", "text/csv",
                                key=f"csv_{msg.get('time', '')}_{id(msg)}",
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


def render_document_history(api_base_url: str, project_id: int = None):
    """Render a document history panel showing all generated documents."""
    import requests

    try:
        params = {}
        if project_id:
            params["project_id"] = project_id
        resp = requests.get(f"{api_base_url}/api/documents/list", params=params, timeout=10)
        if resp.status_code != 200:
            st.warning("Could not load document history.")
            return

        data = resp.json().get("data", {})
        documents = data.get("documents", [])

        if not documents:
            st.info("No documents generated yet.")
            return

        st.markdown(f"**Generated Documents** ({len(documents)})")
        for doc in documents:
            col1, col2 = st.columns([4, 1])
            with col1:
                trade = doc.get("trade", "")
                filename = doc.get("filename", "")
                size_kb = doc.get("size_kb", 0)
                st.markdown(f"**{trade}** — `{filename}` ({size_kb} KB)")
            with col2:
                download_url = doc.get("download_url", "")
                if download_url:
                    st.markdown(f"[Download]({download_url})")
    except Exception as e:
        st.error(f"Error loading documents: {e}")
