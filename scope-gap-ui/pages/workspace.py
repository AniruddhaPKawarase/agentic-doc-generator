"""
Page 3: Scope Workspace — export, report, and drawing views.
"""
import time

import streamlit as st

from api.client import _get, fetch_document_bytes
from api.scope_gap import (
    api_get_drawings,
    api_get_trades,
    api_run_all,
    api_run_scope_gap,
    api_run_scope_gap_streaming,
)
from api.client import health as api_health
from components.export_panel import render_export_documents
from components.reference_panel import (
    _render_reference_panel_inline,
    _render_source_documents_sidebar,
)
from components.scope_items import _extract_source_drawings, _render_scope_items
from components.score_cards import render_score_cards
from config import MOCK_DRAWINGS, MOCK_TRADES, TRADE_COLOR_PALETTE
from utils.session import nav


def _trade_color(index: int) -> str:
    return TRADE_COLOR_PALETTE[index % len(TRADE_COLOR_PALETTE)]


def page_workspace():
    proj = st.session_state.selected_project
    if not proj:
        st.warning("No project selected.")
        if st.button("← Back to Projects"):
            nav("projects")
        return

    pid = proj["project_id"]

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            f"""
<div class="sidebar-header">
  <div class="sidebar-title">{proj["name"]}</div>
  <div class="sidebar-sub">{proj["loc"]}</div>
</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        tab_draw, tab_spec, tab_find = st.tabs(["📐 Drawings", "📄 Specs", "🔍 Findings"])

        with tab_draw:
            st.markdown(
                '<div style="font-size:11px;color:#94A3B8;margin-bottom:8px;">'
                "Drawing Sets</div>",
                unsafe_allow_html=True,
            )
            with st.spinner("Loading drawings…"):
                drawings_resp = api_get_drawings(pid)

            if drawings_resp and "error" not in drawings_resp:
                raw_cats = drawings_resp.get("categories", {})
                tree = {}
                for discipline, data in raw_cats.items():
                    names = []
                    if isinstance(data, dict):
                        for d in data.get("drawings", []):
                            names.append(d if isinstance(d, str) else d.get("drawingName", str(d)))
                        for s in data.get("specs", []):
                            names.append(s if isinstance(s, str) else s.get("drawingName", str(s)))
                    elif isinstance(data, list):
                        names = [x if isinstance(x, str) else str(x) for x in data]
                    if names:
                        tree[discipline] = names
                if not tree:
                    tree = MOCK_DRAWINGS
            else:
                tree = MOCK_DRAWINGS

            filter_text = st.text_input(
                "Filter", placeholder="Filter drawings…",
                key="draw_filter", label_visibility="collapsed"
            )
            for discipline, sheets in tree.items():
                filtered_sheets = [
                    s for s in sheets
                    if filter_text.lower() in s.lower() or filter_text == ""
                ]
                if filtered_sheets:
                    with st.expander(f"**{discipline}** ({len(filtered_sheets)})",
                                     expanded=False):
                        for sheet in filtered_sheets:
                            if st.button(sheet, key=f"sheet_{sheet}",
                                         use_container_width=True):
                                st.session_state.workspace_view = "drawing"
                                st.session_state.selected_drawing = sheet
                                st.rerun()

        with tab_spec:
            st.markdown(
                '<div style="font-size:12px;color:#94A3B8;padding:8px 0;">'
                "No spec sets loaded yet.</div>",
                unsafe_allow_html=True,
            )

        with tab_find:
            results = st.session_state.scope_results
            if results:
                for trade, res in list(results.items())[:10]:
                    items = res.get("scope_items", []) if isinstance(res, dict) else []
                    st.markdown(
                        f'<div style="font-size:12px;font-weight:600;color:#E2E8F0;'
                        f'margin-top:8px;">{trade} — {len(items)} items</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div style="font-size:12px;color:#94A3B8;padding:8px 0;">'
                    "Run scope gap analysis to see findings.</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown(
            '<div style="font-size:11px;color:#64748B;">👤 Field Engineer</div>',
            unsafe_allow_html=True,
        )

    # ── Main area ──
    view = st.session_state.workspace_view

    # View toggle
    col_e, col_r, col_d, col_spacer = st.columns([1, 1.2, 1.2, 6])
    with col_e:
        if st.button("📊 Export", type="primary" if view == "export" else "secondary",
                     key="view_export"):
            st.session_state.workspace_view = "export"
            st.rerun()
    with col_r:
        if st.button("📋 Report", type="primary" if view == "report" else "secondary",
                     key="view_report"):
            st.session_state.workspace_view = "report"
            st.rerun()
    with col_d:
        if st.button("📐 Drawing", type="primary" if view == "drawing" else "secondary",
                     key="view_drawing"):
            st.session_state.workspace_view = "drawing"
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if view == "export":
        _workspace_export_view(proj)
    elif view == "report":
        _workspace_report_view(proj)
    elif view == "drawing":
        _workspace_drawing_view(proj)


# ─────────────────────────────────────────────────────────────────────────────
# Export view
# ─────────────────────────────────────────────────────────────────────────────
def _workspace_export_view(proj: dict):
    pid = proj["project_id"]

    col_h1, col_h2 = st.columns([6, 1])
    with col_h1:
        st.markdown(
            '<div class="section-title">📊 Export — Scope Gap Reports</div>',
            unsafe_allow_html=True,
        )
    with col_h2:
        if st.button("🔄 Refresh All", key="refresh_all"):
            st.session_state.trades_data = {}

    st.markdown(
        f'<div style="display:inline-block;background:#F1F5F9;border:1px solid #E2E8F0;'
        f'border-radius:6px;padding:4px 12px;font-size:12px;font-weight:600;color:#0F172A;'
        f'margin-bottom:16px;">{proj["name"]}</div>',
        unsafe_allow_html=True,
    )

    # Fetch trades
    if pid not in st.session_state.trades_data:
        with st.spinner("Loading trades…"):
            resp = api_get_trades(pid)
        if resp and "error" not in resp:
            raw_trades = resp.get("trades", resp) if isinstance(resp, dict) else resp
            if isinstance(raw_trades, list) and raw_trades and isinstance(raw_trades[0], dict):
                trades_list = [t.get("trade", str(t)) for t in raw_trades if t.get("trade")]
            else:
                trades_list = raw_trades
            st.session_state.trades_data[pid] = trades_list
        else:
            st.session_state.trades_data[pid] = MOCK_TRADES
            if resp is None:
                st.markdown(
                    '<div class="banner-warn">⚠️ Could not connect to the API. '
                    "Showing sample trade list.</div>",
                    unsafe_allow_html=True,
                )

    trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
    if isinstance(trades_list, dict):
        trades_list = list(trades_list.keys())

    # "Export All" and "Run All" buttons
    col_a, col_b, col_spacer = st.columns([1.2, 1.2, 8])
    with col_a:
        if st.button("⬇️ Export All", key="export_all"):
            with st.spinner("Preparing export…"):
                resp = _get(f"/api/scope-gap/projects/{pid}/export")
            if resp and "error" not in resp:
                st.success("Export prepared — check your downloads.")
            else:
                st.warning("Export endpoint not available. Please generate reports first.")
    with col_b:
        if st.button("🚀 Run All Trades", key="run_all"):
            with st.spinner("Queuing all trades…"):
                resp = api_run_all(pid)
            if resp and "error" not in resp:
                st.success(f"Queued {len(trades_list)} trades for processing.")
            else:
                st.warning("Could not connect to API. Please try again.")

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:12px;color:#64748B;margin-bottom:8px;">'
        f'{len(trades_list)} trade(s)</div>',
        unsafe_allow_html=True,
    )

    # Trade table
    for i, trade in enumerate(trades_list):
        has_result = trade in st.session_state.scope_results
        color = _trade_color(i)

        col_dot, col_name, col_status, col_btn = st.columns([0.3, 4, 1.5, 1.5])
        with col_dot:
            st.markdown(
                f'<div style="width:12px;height:12px;border-radius:50%;'
                f'background:{color};margin-top:10px;"></div>',
                unsafe_allow_html=True,
            )
        with col_name:
            st.markdown(
                f'<div style="font-size:13px;font-weight:600;color:#0F172A;'
                f'padding-top:8px;">{trade}</div>',
                unsafe_allow_html=True,
            )
        with col_status:
            if has_result:
                st.markdown(
                    '<span style="background:#DCFCE7;color:#166534;font-size:11px;'
                    'font-weight:600;padding:3px 10px;border-radius:9999px;">'
                    "✓ Ready</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="background:#F1F5F9;color:#64748B;font-size:11px;'
                    'font-weight:600;padding:3px 10px;border-radius:9999px;">'
                    "— Pending</span>",
                    unsafe_allow_html=True,
                )
        with col_btn:
            if has_result:
                if st.button("View Report →", key=f"view_{trade}_{i}"):
                    st.session_state.selected_trade = trade
                    st.session_state.workspace_view = "report"
                    st.rerun()
            else:
                gen_lock_key = f"gen_lock_{trade}"
                is_generating = st.session_state.get(gen_lock_key, False)
                if st.button(
                    "Generating…" if is_generating else "Generate",
                    key=f"gen_{trade}_{i}",
                    disabled=is_generating,
                ):
                    health_resp = api_health()
                    if health_resp is None:
                        st.error("API server unreachable. Please check server status.")
                    elif "error" in (health_resp or {}):
                        st.error(f"API unhealthy: {health_resp.get('error')}")
                    else:
                        st.session_state[gen_lock_key] = True

                        progress_bar = st.progress(0.0, text="Starting pipeline…")
                        status_text = st.empty()
                        status_text.markdown("🚀 **Connecting to pipeline…**")

                        result = api_run_scope_gap_streaming(
                            pid, trade, progress_bar, status_text,
                        )

                        st.session_state[gen_lock_key] = False

                        if result and "error" not in result:
                            st.session_state.scope_results[trade] = result
                            st.session_state.selected_trade = trade
                            progress_bar.progress(1.0, text="Complete!")
                            status_text.empty()
                            st.success(f"{trade} analysis complete!")
                            time.sleep(1)
                            st.rerun()
                        elif result is None:
                            progress_bar.empty()
                            st.error("Cannot connect to API. Please check server status.")
                        else:
                            progress_bar.empty()
                            st.error(f"Error: {result.get('error', 'Unknown error')}")

        st.markdown(
            '<div style="height:1px;background:#F1F5F9;margin:4px 0;"></div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Report view
# ─────────────────────────────────────────────────────────────────────────────
def _workspace_report_view(proj: dict):
    pid = proj["project_id"]
    trade = st.session_state.selected_trade

    # Back button + header
    col_back, col_title, col_export = st.columns([1, 5, 1.5])
    with col_back:
        if st.button("← Back", key="back_to_export"):
            st.session_state.workspace_view = "export"
            st.rerun()
    with col_title:
        if trade:
            st.markdown(
                f'<div class="section-title">📋 {trade} — Scope of Work</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="section-title">📋 Scope Report</div>',
                unsafe_allow_html=True,
            )
    with col_export:
        pass  # Export buttons in document downloads section below

    if not trade:
        trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
        if isinstance(trades_list, dict):
            trades_list = list(trades_list.keys())
        selected = st.selectbox("Select trade", trades_list, key="report_trade_sel")
        if st.button("Load Report", key="load_report"):
            st.session_state.selected_trade = selected
            if selected not in st.session_state.scope_results:
                with st.spinner(f"Generating {selected} scope gap…"):
                    result = api_run_scope_gap(pid, selected)
                if result and "error" not in result:
                    st.session_state.scope_results[selected] = result
                elif result is None:
                    st.error("Cannot connect to API.")
                    return
                else:
                    st.error(result.get("error", "Unknown error"))
                    return
            st.rerun()
        return

    # Load / generate result
    if trade not in st.session_state.scope_results:
        with st.spinner(f"Generating {trade} scope gap analysis…"):
            result = api_run_scope_gap(pid, trade)
        if result and "error" not in result:
            st.session_state.scope_results[trade] = result
        elif result is None:
            st.markdown(
                '<div class="banner-error">Cannot connect to API. '
                "Please check server status.</div>",
                unsafe_allow_html=True,
            )
            return
        else:
            st.error(result.get("error", "Unknown error"))
            return

    result = st.session_state.scope_results[trade]
    if not isinstance(result, dict):
        st.error("Unexpected result format from API.")
        return

    # ── Score cards ──
    render_score_cards(result)

    # ── Document downloads ──
    documents = result.get("documents", {})
    render_export_documents(documents, trade)

    # ── Source documents sidebar ──
    all_source_drawings = _extract_source_drawings(result)

    col_main, col_ref = st.columns([3, 1.2])

    with col_main:
        _render_scope_items(result, trade)

    with col_ref:
        _render_source_documents_sidebar(all_source_drawings, result)
        if st.session_state.ref_panel_open and st.session_state.ref_panel_items:
            with st.expander("📎 Selected Item References", expanded=True):
                _render_reference_panel_inline()


# ─────────────────────────────────────────────────────────────────────────────
# Drawing view
# ─────────────────────────────────────────────────────────────────────────────
def _workspace_drawing_view(proj: dict):
    pid = proj["project_id"]
    drawing = st.session_state.get("selected_drawing", "A-001 Site Plan")

    # Toolbar
    st.markdown(
        f'<div style="background:#fff;border:1px solid #E2E8F0;border-radius:10px;'
        f'padding:10px 16px;display:flex;align-items:center;gap:16px;margin-bottom:16px;">'
        f'<span style="font-size:13px;font-weight:700;color:#0F172A;">{drawing}</span>'
        f'<span style="color:#E2E8F0;">|</span>'
        f'<span style="font-size:11px;color:#64748B;">Toolbar:</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">↖ Select</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">✋ Move</span>'
        f'<span style="background:#F1F5F9;border:1px solid #E2E8F0;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">🔍 Zoom</span>'
        f'<span style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:6px;'
        f'padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;">🖊 Highlight</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    col_canvas, col_findings = st.columns([3, 1])

    with col_canvas:
        st.markdown(
            f"""
<div class="drawing-canvas">
  <div style="font-size:48px;opacity:0.15;">📐</div>
  <div style="font-size:14px;font-weight:700;color:#94A3B8;">{drawing}</div>
  <div style="font-size:12px;color:#CBD5E1;">Project {pid} · Drawing Viewer</div>
  <div style="font-size:11px;color:#E2E8F0;margin-top:8px;">
    PDF rendering requires a CAD/PDF integration
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🖊 Draw a Highlight", key="draw_highlight"):
            st.info("Highlight drawing tools require PDF.js integration. "
                    "Use the API to save highlight coordinates.")

    with col_findings:
        st.markdown(
            '<div style="background:#1E293B;border-radius:10px;padding:12px;'
            'min-height:400px;">',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:12px;font-weight:700;color:#F8FAFC;margin-bottom:10px;">'
            "🔍 Findings</div>",
            unsafe_allow_html=True,
        )

        findings_shown = 0
        for trade, res in list(st.session_state.scope_results.items())[:3]:
            items = res.get("scope_items", []) if isinstance(res, dict) else []
            for it in items[:3]:
                text = it if isinstance(it, str) else it.get("text", str(it))
                st.checkbox(
                    text[:60] + ("…" if len(text) > 60 else ""),
                    key=f"find_{trade}_{text[:20]}",
                )
                findings_shown += 1

        if findings_shown == 0:
            st.markdown(
                '<div style="font-size:11px;color:#64748B;margin-top:8px;">'
                "Generate scope gap reports to see findings here.</div>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

        trades_list = st.session_state.trades_data.get(pid, MOCK_TRADES)
        if isinstance(trades_list, dict):
            trades_list = list(trades_list.keys())
        st.selectbox("Trade Filter", ["All"] + list(trades_list),
                     key="drawing_trade_filter")
