"""
Scope item rendering with inline citations, source references, and drawing extraction.
"""
import streamlit as st


def _build_source_ref(item: dict) -> list[dict]:
    """Build source reference list from a ClassifiedItem dict.

    ClassifiedItem has: drawing_name, drawing_title, drawing_refs, page,
    source_snippet, source_type, source_record_id.
    """
    refs = []
    drawing_name = item.get("drawing_name", "")
    drawing_title = item.get("drawing_title", "")
    page = item.get("page")
    snippet = item.get("source_snippet", "")
    source_type = item.get("source_type", "drawing")
    record_id = item.get("source_record_id", "")

    # Primary source: the item's own drawing
    if drawing_name:
        refs.append({
            "drawing_name": drawing_name,
            "drawing_title": drawing_title or "",
            "page": str(page) if page else "",
            "source_snippet": snippet,
            "source_type": source_type,
            "record_id": record_id,
        })

    # Additional cross-references from drawing_refs
    for ref_name in item.get("drawing_refs", []):
        if ref_name and ref_name != drawing_name:
            refs.append({
                "drawing_name": ref_name,
                "drawing_title": "",
                "page": "",
                "source_snippet": "",
                "source_type": "cross-reference",
                "record_id": "",
            })

    return refs


def _extract_source_drawings(result: dict) -> list[dict]:
    """Extract unique source drawings from all items in the result.

    Returns a sorted list of dicts with drawing_name, drawing_title,
    item_count, and source_type.
    """
    drawing_map: dict[str, dict] = {}

    for item in result.get("items", []):
        if not isinstance(item, dict):
            continue
        dn = item.get("drawing_name", "")
        if not dn:
            continue
        if dn not in drawing_map:
            drawing_map[dn] = {
                "drawing_name": dn,
                "drawing_title": item.get("drawing_title", "") or "",
                "item_count": 0,
                "source_type": item.get("source_type", "drawing"),
                "pages": set(),
            }
        drawing_map[dn]["item_count"] += 1
        page = item.get("page")
        if page:
            drawing_map[dn]["pages"].add(str(page))

    # Convert sets to sorted lists for display
    drawings = []
    for d in sorted(drawing_map.values(), key=lambda x: x["drawing_name"]):
        d["pages"] = sorted(d["pages"])
        drawings.append(d)
    return drawings


def _render_scope_items(result: dict, trade: str):
    """Render grouped scope items with inline citations."""
    scope_items = result.get("items", result.get("scope_items", []))
    ambiguities = result.get("ambiguities", [])
    gotchas = result.get("gotchas", [])

    # ── Job Specific Items ──
    st.markdown(
        f'<div class="section-header">'
        f'<span class="section-title">Job Specific Items</span>'
        f'<span class="text-muted">{len(scope_items)} items</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    if not scope_items:
        st.markdown(
            '<div class="banner-info">No scope items found for this trade.</div>',
            unsafe_allow_html=True,
        )
    else:
        # Group items by drawing_name for clarity
        grouped: dict[str, list] = {}
        for item in scope_items:
            if isinstance(item, dict):
                dn = item.get("drawing_name", "Unknown")
            else:
                dn = "Unknown"
            grouped.setdefault(dn, []).append(item)

        for drawing_name, items_in_drawing in grouped.items():
            drawing_title = ""
            if items_in_drawing and isinstance(items_in_drawing[0], dict):
                drawing_title = items_in_drawing[0].get("drawing_title", "") or ""

            header_text = f"📄 {drawing_name}"
            if drawing_title:
                header_text += f" — {drawing_title}"

            with st.expander(f"{header_text} ({len(items_in_drawing)} items)", expanded=True):
                for i, item in enumerate(items_in_drawing):
                    text = item if isinstance(item, str) else item.get("text", str(item))
                    # Build source reference from ClassifiedItem fields
                    source_ref = _build_source_ref(item) if isinstance(item, dict) else []

                    col_text, col_meta, col_link = st.columns([6, 2.5, 0.5])
                    with col_text:
                        st.markdown(
                            f'<div class="scope-item-text">{text}</div>',
                            unsafe_allow_html=True,
                        )
                        # Inline citation: drawing name + page
                        if isinstance(item, dict):
                            _dn = item.get("drawing_name", "")
                            _pg = item.get("page", "")
                            _snip = item.get("source_snippet", "")
                            if _dn:
                                cite_text = f"[Source: {_dn}"
                                if _pg:
                                    cite_text += f", p.{_pg}"
                                cite_text += "]"
                                tooltip = f'title="{_snip[:200]}"' if _snip else ""
                                st.markdown(
                                    f'<div style="font-size:11px;font-style:italic;'
                                    f'color:#475569;margin-top:2px;" {tooltip}>'
                                    f'{cite_text}</div>',
                                    unsafe_allow_html=True,
                                )
                    with col_meta:
                        if isinstance(item, dict):
                            csi = item.get("csi_code", "") or item.get("csi_division", "")
                            conf = item.get("confidence", 0)
                            meta_parts = []
                            if csi:
                                meta_parts.append(f'<span style="background:#EFF6FF;color:#1E40AF;'
                                                  f'border-radius:4px;padding:2px 6px;font-size:10px;'
                                                  f'font-weight:600;">{csi}</span>')
                            if conf:
                                pct = conf * 100 if conf <= 1 else conf
                                meta_parts.append(f'<span style="color:#64748B;font-size:10px;">'
                                                  f'{pct:.0f}%</span>')
                            page = item.get("page")
                            if page:
                                meta_parts.append(f'<span style="color:#94A3B8;font-size:10px;">'
                                                  f'p.{page}</span>')
                            if meta_parts:
                                st.markdown(
                                    f'<div style="display:flex;gap:6px;align-items:center;'
                                    f'padding-top:4px;">{"".join(meta_parts)}</div>',
                                    unsafe_allow_html=True,
                                )
                    with col_link:
                        if st.button("🔗", key=f"ref_{trade}_{drawing_name}_{i}",
                                     help="View source references"):
                            st.session_state.ref_panel_open = True
                            st.session_state.ref_panel_items = source_ref
                            st.rerun()

                    st.markdown(
                        '<div style="height:1px;background:#F1F5F9;margin:2px 0;"></div>',
                        unsafe_allow_html=True,
                    )

    # ── Ambiguities ──
    if ambiguities:
        with st.expander(f"⚠️ Trade Ambiguities ({len(ambiguities)})", expanded=False):
            for amb in ambiguities:
                if isinstance(amb, dict):
                    text = amb.get("text", str(amb))
                    competing = amb.get("competing_trades", [])
                    severity = amb.get("severity", "medium")
                    sev_color = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#DBEAFE"}.get(severity, "#FEF3C7")
                    refs = amb.get("drawing_refs", [])
                    st.markdown(
                        f'<div style="background:{sev_color};border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">'
                        f'<b>{text}</b>'
                        f'{"<br><span style=color:#64748B;>Competing trades: " + ", ".join(competing) + "</span>" if competing else ""}'
                        f'{"<br><span style=color:#94A3B8;font-size:10px;>Drawings: " + ", ".join(refs) + "</span>" if refs else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="banner-warn" style="margin-bottom:6px;">{amb}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Gotchas ──
    if gotchas:
        with st.expander(f"🎯 Hidden Risks / Gotchas ({len(gotchas)})", expanded=False):
            for g in gotchas:
                if isinstance(g, dict):
                    risk_type = g.get("risk_type", "")
                    desc = g.get("description", g.get("text", str(g)))
                    severity = g.get("severity", "medium")
                    recommendation = g.get("recommendation", "")
                    affected = g.get("affected_trades", [])
                    refs = g.get("drawing_refs", [])
                    sev_color = {"high": "#FEE2E2", "medium": "#FEF3C7", "low": "#DBEAFE"}.get(severity, "#FEF3C7")
                    st.markdown(
                        f'<div style="background:{sev_color};border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">'
                        f'{"<b>[" + risk_type.upper() + "]</b> " if risk_type else ""}'
                        f'{desc}'
                        f'{"<br><span style=color:#166534;font-size:11px;>💡 " + recommendation + "</span>" if recommendation else ""}'
                        f'{"<br><span style=color:#64748B;font-size:10px;>Affected: " + ", ".join(affected) + "</span>" if affected else ""}'
                        f'{"<br><span style=color:#94A3B8;font-size:10px;>Drawings: " + ", ".join(refs) + "</span>" if refs else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="background:#FEF3C7;border-radius:8px;padding:10px 12px;'
                        f'margin-bottom:6px;font-size:12px;">{g}</div>',
                        unsafe_allow_html=True,
                    )

    # ── Raw response preview ──
    with st.expander("🔧 Raw API Response", expanded=False):
        st.json(result)
