"""
Global CSS injection — all styles with Phase 1 color fixes.
"""
import streamlit as st


def inject_css():
    st.markdown(
        """
<style>
/* ── Reset & base ── */
* { box-sizing: border-box; }
[data-testid="stAppViewContainer"] { background: #F8FAFC; }
[data-testid="stHeader"] { display: none; }
[data-testid="stSidebar"] { background: #1E293B !important; color: #E2E8F0; }
[data-testid="stSidebar"] * { color: #E2E8F0 !important; }
[data-testid="stSidebarContent"] { padding: 0; }

/* ── Hide default Streamlit decorations ── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* ── Global font ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Top nav bar ── */
.ifs-navbar {
    background: #1E293B;
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
    border-bottom: 1px solid #334155;
    position: sticky;
    top: 0;
    z-index: 100;
}
.ifs-logo { display: flex; align-items: center; gap: 10px; }
.ifs-logo-mark {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, #C4841D, #E8A842);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; font-weight: 800; color: #fff;
}
.ifs-logo-text { font-size: 15px; font-weight: 700; color: #fff; }
.ifs-logo-sub  { font-size: 11px; color: #94A3B8; }
.ifs-nav-links { display: flex; gap: 4px; }
.ifs-nav-link {
    padding: 6px 12px; border-radius: 6px;
    font-size: 13px; font-weight: 500; color: #94A3B8;
    cursor: pointer; transition: all 0.15s;
    border: none; background: transparent;
}
.ifs-nav-link:hover { background: #334155; color: #fff; }
.ifs-nav-link.active { background: #334155; color: #fff; }

/* ── Hero ── */
.ifs-hero {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    padding: 48px 24px 36px;
    text-align: center;
    border-bottom: 1px solid #334155;
}
.ifs-hero h1 {
    font-size: 28px; font-weight: 800; color: #fff; margin: 0 0 8px;
}
.ifs-hero p {
    font-size: 15px; color: #94A3B8; margin: 0 0 24px;
}

/* ── Project cards ── */
.proj-card {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px;
    transition: all 0.2s ease;
    cursor: pointer;
    position: relative;
    overflow: hidden;
}
.proj-card:hover {
    border-color: #3B82F6;
    box-shadow: 0 4px 16px rgba(59,130,246,0.15);
    transform: translateY(-2px);
}
.proj-card-accent {
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #C4841D, #E8A842);
}
.proj-card-name {
    font-size: 15px; font-weight: 700; color: #0F172A; margin: 12px 0 4px;
}
.proj-card-meta {
    font-size: 12px; color: #64748B; display: flex; align-items: center; gap: 6px;
}
.proj-card-type {
    font-size: 11px; color: #94A3B8; background: #F8FAFC;
    border: 1px solid #E2E8F0; border-radius: 4px; padding: 2px 6px; margin-top: 8px;
    display: inline-block;
}
.proj-progress-label {
    font-size: 11px; color: #64748B; margin: 10px 0 4px;
    display: flex; justify-content: space-between;
}

/* ── Badges ── */
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 9999px;
    font-size: 11px; font-weight: 600;
}
.badge-active   { background: #DCFCE7; color: #166534; }
.badge-onhold   { background: #FEF3C7; color: #92400E; }
.badge-completed{ background: #F1F5F9; color: #475569; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; }
.badge-dot-active   { background: #22C55E; }
.badge-dot-onhold   { background: #F59E0B; }
.badge-dot-completed{ background: #94A3B8; }

/* ── Agent cards ── */
.agent-card {
    background: #fff;
    border: 1.5px solid #E2E8F0;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
}
.agent-card:hover {
    border-color: #3B82F6;
    box-shadow: 0 4px 16px rgba(59,130,246,0.12);
    transform: translateY(-2px);
}
.agent-card.active-agent {
    border-color: #C4841D;
    background: linear-gradient(135deg, #FFFBEB, #fff);
    box-shadow: 0 4px 16px rgba(196,132,29,0.15);
}
.agent-icon {
    font-size: 32px; margin-bottom: 10px; display: block;
}
.agent-name { font-size: 14px; font-weight: 700; color: #0F172A; margin: 0 0 6px; }
.agent-desc { font-size: 12px; color: #64748B; }
.agent-arrow {
    position: absolute; top: 12px; right: 12px;
    font-size: 14px; color: #94A3B8;
}

/* ── Breadcrumb ── */
.breadcrumb {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: #64748B; padding: 12px 0;
}
.breadcrumb a {
    color: #3B82F6; text-decoration: none; font-weight: 500;
}
.breadcrumb-sep { color: #CBD5E1; }
.breadcrumb-current { color: #0F172A; font-weight: 600; }

/* ── Section header ── */
.section-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; padding-bottom: 10px;
    border-bottom: 1px solid #E2E8F0;
}
.section-title { font-size: 16px; font-weight: 700; color: #1E293B; }

/* ── Trade rows ── */
.trade-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; border-radius: 8px;
    background: #fff; border: 1px solid #E2E8F0;
    margin-bottom: 8px; cursor: pointer;
    transition: all 0.15s;
}
.trade-row:hover {
    border-color: #3B82F6;
    background: #EFF6FF;
}
.trade-dot-name { display: flex; align-items: center; gap: 10px; }
.trade-color-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.trade-name { font-size: 13px; font-weight: 600; color: #0F172A; }

/* ── Scope item ── */
.scope-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px; border-radius: 8px;
    background: #F8FAFC; border: 1px solid #E2E8F0;
    margin-bottom: 6px;
    transition: background 0.15s;
}
.scope-item:hover { background: #EFF6FF; }
.scope-item-text { font-size: 13px; color: #1E293B !important; flex: 1; line-height: 1.5; }
.scope-item-link {
    font-size: 18px; cursor: pointer; color: #64748B; flex-shrink: 0;
    transition: color 0.15s;
}
.scope-item-link:hover { color: #3B82F6; }

/* ── Score cards ── */
.score-card {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 10px; padding: 14px 16px;
}
.score-label {
    font-size: 11px; font-weight: 600; color: #64748B;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;
}
.score-value { font-size: 22px; font-weight: 800; color: #0F172A; }
.score-sub   { font-size: 11px; color: #475569; margin-top: 2px; }

/* ── Reference panel ── */
.ref-panel {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 12px; padding: 16px;
    position: relative;
}
.ref-panel-title {
    font-size: 13px; font-weight: 700; color: #1E293B; margin-bottom: 12px;
    padding-bottom: 8px; border-bottom: 1px solid #E2E8F0;
}
.ref-card {
    background: #F8FAFC; border: 1px solid #E2E8F0;
    border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;
}
.ref-card-name { font-size: 12px; font-weight: 600; color: #1E293B; }
.ref-card-meta { font-size: 11px; color: #475569; margin-top: 2px; }

/* ── Sidebar (workspace) ── */
.sidebar-header {
    background: #0F172A; padding: 16px;
    border-bottom: 1px solid #1E293B;
}
.sidebar-title {
    font-size: 13px; font-weight: 700; color: #F8FAFC; margin-bottom: 4px;
}
.sidebar-sub { font-size: 11px; color: #64748B; }

/* ── Drawing canvas placeholder ── */
.drawing-canvas {
    background: #fff; border: 1px solid #E2E8F0;
    border-radius: 12px; min-height: 500px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: #94A3B8; gap: 8px;
}

/* ── Chat messages ── */
.chat-msg-user {
    background: #3B82F6; color: #fff;
    border-radius: 12px 12px 2px 12px;
    padding: 10px 14px; font-size: 13px;
    max-width: 72%; margin-left: auto; margin-bottom: 8px;
}
.chat-msg-agent {
    background: #fff; color: #0F172A;
    border: 1px solid #E2E8F0;
    border-radius: 12px 12px 12px 2px;
    padding: 10px 14px; font-size: 13px;
    max-width: 85%; margin-right: auto; margin-bottom: 8px;
}
.chat-msg-time {
    font-size: 10px; opacity: 0.6; margin-top: 4px;
}

/* ── Warning / info banners ── */
.banner-warn {
    background: #FEF3C7; border: 1px solid #FDE68A;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #92400E; margin-bottom: 12px;
}
.banner-info {
    background: #DBEAFE; border: 1px solid #BFDBFE;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #1E40AF; margin-bottom: 12px;
}
.banner-error {
    background: #FEE2E2; border: 1px solid #FECACA;
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #991B1B; margin-bottom: 12px;
}

/* ── Button override helpers ── */
div[data-testid="stButton"] > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stButton"] > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
}

/* ── Progress bar override ── */
[data-testid="stProgress"] > div {
    height: 6px !important;
    border-radius: 3px !important;
}

/* ── Utility ── */
.text-muted { color: #64748B; font-size: 12px; }
.text-sm    { font-size: 12px; }
.text-xs    { font-size: 11px; }
.fw-bold    { font-weight: 700; }
.mt-1       { margin-top: 8px; }
.mt-2       { margin-top: 16px; }
.gap-1      { gap: 8px; }
.flex-row   { display: flex; align-items: center; gap: 8px; }
</style>
        """,
        unsafe_allow_html=True,
    )
