"""
Document download buttons using st.download_button.
"""
import streamlit as st

from api.client import fetch_document_bytes


def render_export_documents(documents: dict, trade: str):
    """Render document download buttons for Word, PDF, CSV, JSON."""
    if not isinstance(documents, dict):
        return
    if not any(documents.get(k) for k in ("word_path", "pdf_path", "csv_path", "json_path")):
        st.markdown("<br>", unsafe_allow_html=True)
        return

    st.markdown(
        '<div style="font-size:12px;font-weight:600;color:#1E293B;margin:8px 0 8px;">'
        '⬇️ Export Documents</div>',
        unsafe_allow_html=True,
    )
    doc_cols = st.columns(4)
    doc_formats = [
        ("word_path", "📄 Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
        ("pdf_path", "📕 PDF", "application/pdf", ".pdf"),
        ("csv_path", "📊 CSV", "text/csv", ".csv"),
        ("json_path", "📋 JSON", "application/json", ".json"),
    ]
    for col, (key, label, mime, ext) in zip(doc_cols, doc_formats):
        doc_path = documents.get(key)
        if doc_path:
            with col:
                file_bytes, fname = fetch_document_bytes(doc_path)
                if file_bytes:
                    st.download_button(
                        label=label,
                        data=file_bytes,
                        file_name=fname or f"scope_export{ext}",
                        mime=mime,
                        key=f"dl_{trade}_{key}",
                        use_container_width=True,
                    )
                else:
                    st.markdown(
                        f'<div style="background:#FEF3C7;border:1px solid #FDE68A;'
                        f'border-radius:8px;padding:8px 12px;text-align:center;'
                        f'font-size:11px;color:#92400E;">'
                        f'{label} (unavailable)</div>',
                        unsafe_allow_html=True,
                    )
        else:
            with col:
                st.markdown(
                    f'<div style="background:#F1F5F9;border:1px solid #E2E8F0;'
                    f'border-radius:8px;padding:8px 12px;text-align:center;'
                    f'font-size:11px;color:#94A3B8;">{label} —</div>',
                    unsafe_allow_html=True,
                )
