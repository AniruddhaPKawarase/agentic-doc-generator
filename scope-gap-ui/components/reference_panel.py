"""
Source documents sidebar and inline reference panel.
"""
import streamlit as st


def _render_source_documents_sidebar(source_drawings: list[dict], result: dict):
    """Render the source documents sidebar showing all drawings referenced."""
    st.markdown(
        '<div style="font-size:14px;font-weight:700;color:#0F172A;'
        'margin-bottom:12px;">📎 Source Documents</div>',
        unsafe_allow_html=True,
    )

    if not source_drawings:
        st.markdown(
            '<div style="font-size:12px;color:#94A3B8;">No source documents found.</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="font-size:11px;color:#64748B;margin-bottom:8px;">'
        f'{len(source_drawings)} drawing(s) referenced</div>',
        unsafe_allow_html=True,
    )

    for d in source_drawings:
        title = d.get("drawing_title", "")
        pages = d.get("pages", [])
        count = d.get("item_count", 0)
        src_type = d.get("source_type", "drawing")
        icon = "📐" if src_type == "drawing" else "📄"

        page_text = f"p.{', '.join(pages)}" if pages else ""
        subtitle_parts = []
        if page_text:
            subtitle_parts.append(page_text)
        subtitle_parts.append(f"{count} item{'s' if count != 1 else ''}")
        subtitle = " · ".join(subtitle_parts)

        st.markdown(
            f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:8px;'
            f'padding:10px 12px;margin-bottom:6px;">'
            f'<div style="font-size:12px;font-weight:600;color:#0F172A;">'
            f'{icon} {d["drawing_name"]}</div>'
            f'{"<div style=font-size:11px;color:#64748B;>" + title + "</div>" if title else ""}'
            f'<div style="font-size:10px;color:#94A3B8;margin-top:2px;">{subtitle}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Show pipeline stats summary at bottom
    stats = result.get("pipeline_stats", {})
    if isinstance(stats, dict):
        total_ms = stats.get("total_ms", 0)
        tokens = stats.get("tokens_used", 0)
        cost = stats.get("estimated_cost_usd", 0)
        records = stats.get("records_processed", 0)

        st.markdown('<div style="height:1px;background:#E2E8F0;margin:12px 0;"></div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;font-weight:600;color:#64748B;margin-bottom:6px;">'
            '⚡ Pipeline Stats</div>',
            unsafe_allow_html=True,
        )
        stat_lines = []
        if total_ms:
            stat_lines.append(f"⏱ {total_ms / 1000:.1f}s")
        if records:
            stat_lines.append(f"📊 {records} records")
        if tokens:
            stat_lines.append(f"🔤 {tokens:,} tokens")
        if cost:
            stat_lines.append(f"💰 ${cost:.4f}")
        st.markdown(
            '<div style="font-size:10px;color:#94A3B8;">' +
            "<br>".join(stat_lines) + '</div>',
            unsafe_allow_html=True,
        )


def _render_reference_panel_inline():
    """Render item-level references inline (inside an expander, not replacing sidebar)."""
    items = st.session_state.ref_panel_items

    if st.button("✕ Close References", key="close_ref_inline"):
        st.session_state.ref_panel_open = False
        st.session_state.ref_panel_items = []
        st.rerun()

    if not items:
        st.markdown(
            '<div style="font-size:12px;color:#475569;">No source references for this item.</div>',
            unsafe_allow_html=True,
        )
        return

    for src in items:
        if isinstance(src, dict):
            name = src.get("drawing_name", "Unknown")
            title = src.get("drawing_title", "")
            page_ref = src.get("page", "")
            snippet = src.get("source_snippet", "")
            src_type = src.get("source_type", "drawing")
        else:
            name = str(src)
            title = page_ref = snippet = ""
            src_type = "drawing"

        icon = "📐" if src_type == "drawing" else ("🔀" if src_type == "cross-reference" else "📄")

        st.markdown(
            f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;'
            f'padding:10px 12px;margin-bottom:6px;">'
            f'<div style="font-size:12px;font-weight:600;color:#1E293B;">{icon} {name}</div>'
            f'{"<div style=font-size:11px;color:#475569;>" + title + "</div>" if title else ""}'
            f'{"<div style=font-size:10px;color:#475569;>Page: " + str(page_ref) + "</div>" if page_ref else ""}'
            f'{"<div style=font-size:10px;color:#475569;margin-top:4px;font-style:italic;>" + snippet[:200] + "</div>" if snippet else ""}'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_source_references(source_refs: dict):
    """Render clickable source reference links."""
    if not source_refs:
        st.info("Source references not available.")
        return

    with st.expander("Source References", expanded=True):
        for name, ref in sorted(source_refs.items()):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{name}** -- {ref.get('drawing_title', '')}")
            with col2:
                s3_url = ref.get("s3_url")
                if s3_url:
                    st.markdown(f"[Open PDF]({s3_url})")
                else:
                    st.caption("No PDF link")
