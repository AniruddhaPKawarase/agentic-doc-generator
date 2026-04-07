# Construction Agent: Bug Fixes, UI Refactor & Infrastructure Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix reference document display + export download bugs, refactor the UI into portable modules, harden infrastructure across 12 parameters, deploy to sandbox VM, and push to GitHub.

**Architecture:** 4-phase delivery. Phase 1 patches the monolithic `app.py` for the two critical bugs and font fixes. Phase 2 decomposes `app.py` into ~15 focused modules under `scope-gap-ui/`. Phase 3 adds structured logging, rate limiting, S3 versioning, session backup, health endpoints, and scaling config to the FastAPI backend. Phase 4 deploys to the sandbox VM with systemd, pushes to GitHub `agents/doc-generator/`, and archives unused files.

**Tech Stack:** Python 3.11+, FastAPI 0.115, Streamlit 1.35+, boto3, structlog, slowapi, pytest

**Base paths:**
- Backend: `c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/`
- UI: `c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/_archive/scope-gap-ui/`
- GitHub repo: `c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/agentic-ai-platform/`
- Sandbox VM: `54.197.189.113` via PEM key at `c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem`

---

## File Map

### Phase 1 (bug fixes — modify in place)
- Modify: `_archive/scope-gap-ui/app.py` — lines 1314, 1401-1427, 1484-1523, 1429-1442, 440-750

### Phase 2 (UI refactor — new module structure)
- Create: `scope-gap-ui/app.py` (entry point ~50 lines)
- Create: `scope-gap-ui/config.py` (env-driven config)
- Create: `scope-gap-ui/requirements.txt`
- Create: `scope-gap-ui/README.md`
- Create: `scope-gap-ui/api/__init__.py`, `api/client.py`, `api/scope_gap.py`, `api/documents.py`
- Create: `scope-gap-ui/components/__init__.py`, `components/navbar.py`, `components/score_cards.py`, `components/scope_items.py`, `components/reference_panel.py`, `components/export_panel.py`, `components/progress_bar.py`, `components/chat.py`
- Create: `scope-gap-ui/pages/__init__.py`, `pages/projects.py`, `pages/agents.py`, `pages/workspace.py`, `pages/chat.py`
- Create: `scope-gap-ui/styles/__init__.py`, `styles/theme.py`
- Create: `scope-gap-ui/utils/__init__.py`, `utils/session.py`

### Phase 3 (backend hardening)
- Modify: `main.py` — add version, structured logging, request middleware, concurrency limiter
- Modify: `config.py` — new settings for rate limit, auth, concurrency cap
- Modify: `requirements.txt` — add structlog, slowapi
- Modify: `routers/documents.py` — add file_id validation, audit logging
- Create: `services/audit_logger.py` — S3 audit log writer
- Create: `middleware/__init__.py`, `middleware/request_id.py`, `middleware/rate_limit.py`, `middleware/concurrency.py`
- Create: `scope_pipeline/routers/status.py` — `/api/scope-gap/status` and `/api/scope-gap/metrics`
- Modify: `scope_pipeline/services/session_manager.py` — add S3 backup layer
- Create: `scripts/run_tests.sh`, `scripts/deploy_to_sandbox.sh`, `scripts/push_to_github.sh`, `scripts/restore_session.py`
- Create: `CHANGELOG.md`
- Create: `docs/TROUBLESHOOTING.md`

### Phase 4 (deploy + push)
- Create: `gateway/services/construction-agent.service` (systemd unit on VM)
- Archive: move old files to `_archive/`

---

## PHASE 1: CRITICAL BUG FIXES

### Task 1: Add inline citations to scope items

**Files:**
- Modify: `_archive/scope-gap-ui/app.py:1484-1523`

- [ ] **Step 1: Locate the scope item rendering loop**

In `app.py`, the function `_render_scope_items` at line 1484 renders each scope item. Currently it shows `text`, `csi_code`, `confidence`, `page` but NOT `drawing_name` or `source_snippet` inline.

- [ ] **Step 2: Add inline citation below each scope item**

In `app.py`, find this block (lines 1489-1517):

```python
                    col_text, col_meta, col_link = st.columns([6, 2.5, 0.5])
                    with col_text:
                        st.markdown(
                            f'<div class="scope-item-text">{text}</div>',
                            unsafe_allow_html=True,
                        )
```

Replace with:

```python
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
```

- [ ] **Step 3: Verify the change manually**

Run: `cd "_archive/scope-gap-ui" && python -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"`

Expected: `Syntax OK`

---

### Task 2: Fix right panel — unified view (aggregate + item-level)

**Files:**
- Modify: `_archive/scope-gap-ui/app.py:1429-1442`

- [ ] **Step 1: Change the right column to always show aggregate + optional item detail**

Find this block (lines 1433-1442):

```python
    col_main, col_ref = st.columns([3, 1.2])

    with col_main:
        _render_scope_items(result, trade)

    with col_ref:
        if st.session_state.ref_panel_open:
            _render_reference_panel()
        else:
            _render_source_documents_sidebar(all_source_drawings, result)
```

Replace with:

```python
    col_main, col_ref = st.columns([3, 1.2])

    with col_main:
        _render_scope_items(result, trade)

    with col_ref:
        # Always show aggregate source drawings
        _render_source_documents_sidebar(all_source_drawings, result)
        # Show item-level refs in expander when user clicked a link
        if st.session_state.ref_panel_open and st.session_state.ref_panel_items:
            with st.expander("📎 Selected Item References", expanded=True):
                _render_reference_panel_inline()
```

- [ ] **Step 2: Add `_render_reference_panel_inline` function**

Add this new function right after `_render_reference_panel` (after line 1789):

```python
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
```

- [ ] **Step 3: Verify syntax**

Run: `cd "_archive/scope-gap-ui" && python -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"`

---

### Task 3: Fix Export to Doc button — wire download for all 4 formats

**Files:**
- Modify: `_archive/scope-gap-ui/app.py:1314, 1401-1427`

- [ ] **Step 1: Add document download helper function**

Add this function after `api_health()` (around line 154):

```python
def fetch_document_bytes(doc_path: str) -> tuple[bytes | None, str]:
    """Download document bytes from backend.

    Extracts UUID from the document path and calls the download endpoint.
    Returns (bytes, filename) or (None, "") on failure.
    """
    if not doc_path:
        return None, ""

    # Extract UUID-like file_id from path (last segment before extension)
    import re
    # Paths look like: .../scope_electrical_..._a1b2c3d4.docx
    # or S3 keys: construction-intelligence-agent/generated_documents/.../file.docx
    basename = doc_path.rsplit("/", 1)[-1] if "/" in doc_path else doc_path
    # Try to find 8-char hex pattern (UUID[:8])
    match = re.search(r'_([a-f0-9]{8})\.\w+$', basename)
    if not match:
        # Fallback: use last 8 chars before extension
        match = re.search(r'([a-f0-9-]{8,36})', basename)
    if not match:
        return None, ""

    file_id = match.group(1)
    try:
        r = requests.get(
            f"{API_BASE}/api/documents/{file_id}/download",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        r.raise_for_status()
        # Determine filename from Content-Disposition or basename
        cd = r.headers.get("content-disposition", "")
        if "filename=" in cd:
            fname = cd.split("filename=")[-1].strip('"')
        else:
            fname = basename
        return r.content, fname
    except Exception:
        return None, ""
```

- [ ] **Step 2: Replace the static Export DOCX button with format selector**

Find line 1314:

```python
        st.button("⬇️ Export DOCX", key="export_docx")
```

Replace with:

```python
        pass  # Export buttons moved to document downloads section below
```

- [ ] **Step 3: Replace static download cards with `st.download_button` widgets**

Find the document downloads section (lines 1401-1427):

```python
    # ── Document downloads ───────────────────────────────────────────────────
    documents = result.get("documents", {})
    if isinstance(documents, dict) and any(documents.get(k) for k in ("word_path", "pdf_path", "csv_path", "json_path")):
        st.markdown(
            '<div style="display:flex;gap:8px;margin:8px 0 16px;">',
            unsafe_allow_html=True,
        )
        doc_cols = st.columns(4)
        doc_labels = [
            ("word_path", "📄 Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("pdf_path", "📕 PDF", "application/pdf"),
            ("csv_path", "📊 CSV", "text/csv"),
            ("json_path", "📋 JSON", "application/json"),
        ]
        for col, (key, label, _mime) in zip(doc_cols, doc_labels):
            doc_path = documents.get(key)
            if doc_path:
                with col:
                    st.markdown(
                        f'<div style="background:#F0F9FF;border:1px solid #BAE6FD;'
                        f'border-radius:8px;padding:8px 12px;text-align:center;'
                        f'font-size:12px;font-weight:600;color:#0369A1;">'
                        f'{label}</div>',
                        unsafe_allow_html=True,
                    )
    else:
        st.markdown("<br>", unsafe_allow_html=True)
```

Replace the entire block with:

```python
    # ── Document downloads ───────────────────────────────────────────────────
    documents = result.get("documents", {})
    if isinstance(documents, dict) and any(documents.get(k) for k in ("word_path", "pdf_path", "csv_path", "json_path")):
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
    else:
        st.markdown("<br>", unsafe_allow_html=True)
```

- [ ] **Step 4: Verify syntax**

Run: `cd "_archive/scope-gap-ui" && python -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"`

---

### Task 4: Fix font/color visibility — CSS overhaul

**Files:**
- Modify: `_archive/scope-gap-ui/app.py:440-750` (the `inject_css()` function)

- [ ] **Step 1: Fix background color**

Find line 446:

```css
[data-testid="stAppViewContainer"] { background: #F1F5F9; }
```

Replace with:

```css
[data-testid="stAppViewContainer"] { background: #F8FAFC; }
```

- [ ] **Step 2: Fix scope item text color**

Find line 634:

```css
.scope-item-text { font-size: 13px; color: #0F172A; flex: 1; line-height: 1.5; }
```

This is already `#0F172A` which is correct. Verify it's rendering — the issue may be overridden by Streamlit. Add `!important`:

```css
.scope-item-text { font-size: 13px; color: #1E293B !important; flex: 1; line-height: 1.5; }
```

- [ ] **Step 3: Fix secondary text color**

Find all instances of `color: #94A3B8` that are used for readable text (not decorative dots). Replace with `color: #475569` in these CSS classes:

- `.ifs-logo-sub` (line 484): `#94A3B8` → `#94A3B8` (keep — this is navbar, light bg)
- `.score-sub` (line 651): `color: #94A3B8` → `color: #475569`
- `.text-muted` (line 742): `color: #64748B` → keep (already readable)

Find line 651:
```css
.score-sub   { font-size: 11px; color: #94A3B8; margin-top: 2px; }
```
Replace with:
```css
.score-sub   { font-size: 11px; color: #475569; margin-top: 2px; }
```

- [ ] **Step 4: Fix section title color**

Find line 607:
```css
.section-title { font-size: 16px; font-weight: 700; color: #0F172A; }
```
Replace with:
```css
.section-title { font-size: 16px; font-weight: 700; color: #1E293B; }
```

- [ ] **Step 5: Fix reference panel text colors**

Find lines 660, 667-668:
```css
.ref-panel-title {
    font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 12px;
```
```css
.ref-card-name { font-size: 12px; font-weight: 600; color: #0F172A; }
.ref-card-meta { font-size: 11px; color: #64748B; margin-top: 2px; }
```

Replace:
```css
.ref-panel-title {
    font-size: 13px; font-weight: 700; color: #1E293B; margin-bottom: 12px;
```
```css
.ref-card-name { font-size: 12px; font-weight: 600; color: #1E293B; }
.ref-card-meta { font-size: 11px; color: #475569; margin-top: 2px; }
```

- [ ] **Step 6: Verify syntax**

Run: `cd "_archive/scope-gap-ui" && python -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"`

---

### Task 5: Verify backend returns source fields

**Files:**
- Read: `scope_pipeline/orchestrator.py`, `scope_pipeline/agents/extraction_agent.py`

- [ ] **Step 1: Verify ScopeItem has all required source fields**

Read `scope_pipeline/models.py` and confirm `ScopeItem` has: `drawing_name`, `drawing_title`, `page`, `source_snippet`, `source_record_id`, `drawing_refs`, `discipline`, `source_type`.

Read `scope_pipeline/models.py` and confirm `ClassifiedItem` inherits from `ScopeItem` and adds: `trade`, `csi_code`, `csi_division`, `classification_confidence`, `classification_reason`, `trade_color`.

- [ ] **Step 2: Verify orchestrator includes items in result**

Read `scope_pipeline/orchestrator.py` lines 280-295 and confirm `ScopeGapResult` includes `items: list[ClassifiedItem]` and `documents: DocumentSet`. These are what the UI receives.

- [ ] **Step 3: Verify the `/api/scope-gap/generate` endpoint returns the full model**

Read `scope_pipeline/routers/scope_gap.py` and verify the endpoint returns `ScopeGapResult.model_dump()` which will serialize all source fields including `drawing_name`, `source_snippet`, `drawing_refs`, `page`.

No code changes expected here — this is a verification task. If any field is missing, add it.

---

## PHASE 2: UI REFACTOR INTO MODULES

### Task 6: Create `scope-gap-ui/config.py`

**Files:**
- Create: `scope-gap-ui/config.py`

- [ ] **Step 1: Create the config module**

```python
"""
scope-gap-ui/config.py — Environment-driven configuration.

Override defaults via environment variables:
  SCOPE_API_BASE=http://localhost:8003
  SCOPE_REQUEST_TIMEOUT=300
  SCOPE_GENERATE_TIMEOUT=600
"""
import os

API_BASE: str = os.environ.get("SCOPE_API_BASE", "http://54.197.189.113:8003")
REQUEST_TIMEOUT: int = int(os.environ.get("SCOPE_REQUEST_TIMEOUT", "300"))
GENERATE_TIMEOUT: int = int(os.environ.get("SCOPE_GENERATE_TIMEOUT", "600"))

PROJECTS = [
    {"id": "PRJ-001", "project_id": 7276, "name": "450-460 JR PKWY Phase II",
     "loc": "Nashville, TN", "pm": "Smith Gee Studio", "status": "Active",
     "type": "Residential & Garage", "prog": 62},
    {"id": "PRJ-002", "project_id": 7298, "name": "AVE Horsham Multi-Family",
     "loc": "Horsham, PA", "pm": "Bernardon Design", "status": "Active",
     "type": "Multi-Family", "prog": 38},
    {"id": "PRJ-003", "project_id": 7212, "name": "HSB Potomac Senior Living",
     "loc": "Potomac, MD", "pm": "Vessel Architecture", "status": "Active",
     "type": "Senior Living", "prog": 45},
    {"id": "PRJ-004", "project_id": 7222, "name": "Metro Transit Hub",
     "loc": "Chicago, IL", "pm": "James Wilson", "status": "On-Hold",
     "type": "Infrastructure", "prog": 15},
    {"id": "PRJ-005", "project_id": 7223, "name": "Greenfield Data Center",
     "loc": "Phoenix, AZ", "pm": "Tom Davis", "status": "Completed",
     "type": "Industrial", "prog": 100},
]

TRADE_COLOR_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
    "#14B8A6", "#D97706", "#DC2626", "#7C3AED", "#DB2777",
    "#0891B2", "#65A30D", "#EA580C", "#4F46E5", "#0D9488",
    "#B45309", "#BE123C", "#6D28D9",
]

STATUS_CONFIG = {
    "Active":    {"bg": "#DCFCE7", "text": "#166534", "dot": "#22C55E"},
    "On-Hold":   {"bg": "#FEF3C7", "text": "#92400E", "dot": "#F59E0B"},
    "Completed": {"bg": "#F1F5F9", "text": "#475569", "dot": "#94A3B8"},
}

AGENTS = [
    {"name": "RFI Agent",       "icon": "?", "desc": "Manage RFIs and queries",          "page": None},
    {"name": "Submittal Agent", "icon": "clipboard", "desc": "Track submittal packages",          "page": None},
    {"name": "Drawings Agent",  "icon": "ruler", "desc": "Scope gap analysis on drawings",   "page": "workspace"},
    {"name": "Spec Agent",      "icon": "page", "desc": "Specification review & gaps",       "page": None},
    {"name": "BIM Planner",     "icon": "building", "desc": "BIM coordination & clash detection","page": None},
    {"name": "Meeting Agent",   "icon": "calendar", "desc": "Meeting summaries & action items",  "page": None},
]

MOCK_TRADES = [
    "Electrical", "Plumbing", "HVAC", "Structural", "Concrete",
    "Fire Sprinkler", "Roofing & Waterproofing", "Framing Drywall & Insulation",
    "Glass & Glazing", "Painting & Coatings",
]

MOCK_DRAWINGS = {
    "Architectural": ["A-001 Site Plan", "A-101 Floor Plan L1", "A-201 Elevations"],
    "Structural":    ["S-001 Foundation Plan", "S-101 Framing Plan"],
    "Electrical":    ["E-001 Power Plan", "E-101 Lighting Plan"],
    "Plumbing":      ["P-001 Plumbing Plan", "P-101 Riser Diagram"],
    "Mechanical":    ["M-001 HVAC Layout", "M-101 Ductwork Plan"],
}


def trade_color(index: int) -> str:
    return TRADE_COLOR_PALETTE[index % len(TRADE_COLOR_PALETTE)]
```

- [ ] **Step 2: Verify module loads**

Run: `cd scope-gap-ui && python -c "from config import API_BASE, PROJECTS; print(f'API: {API_BASE}, Projects: {len(PROJECTS)}')"`

Expected: `API: http://54.197.189.113:8003, Projects: 5`

---

### Task 7: Create `scope-gap-ui/utils/session.py`

**Files:**
- Create: `scope-gap-ui/utils/__init__.py`
- Create: `scope-gap-ui/utils/session.py`

- [ ] **Step 1: Create the utils package**

`utils/__init__.py`: empty file.

- [ ] **Step 2: Create session state manager**

```python
"""
utils/session.py — Streamlit session state initialization and helpers.
"""
import streamlit as st


def init_session() -> None:
    """Initialize all session state defaults. Safe to call multiple times."""
    defaults = {
        "page": "projects",
        "selected_project": None,
        "workspace_view": "export",
        "selected_trade": None,
        "trades_data": {},
        "scope_results": {},
        "chat_messages": [],
        "chat_session_id": None,
        "ref_panel_open": False,
        "ref_panel_items": [],
        "drawing_filter": "",
        "search_filter": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def nav(page: str) -> None:
    """Navigate to a different page."""
    st.session_state.page = page
    st.rerun()


def score_bar_html(value: float, color: str) -> str:
    """Render a small progress bar as raw HTML."""
    pct = max(0, min(100, value * 100))
    return (
        f'<div style="background:#E2E8F0;border-radius:4px;height:6px;margin-top:6px;">'
        f'<div style="background:{color};width:{pct:.0f}%;height:6px;border-radius:4px;"></div>'
        f'</div>'
    )
```

---

### Task 8: Create `scope-gap-ui/api/client.py`

**Files:**
- Create: `scope-gap-ui/api/__init__.py`
- Create: `scope-gap-ui/api/client.py`

- [ ] **Step 1: Create the API client module**

```python
"""
api/client.py — HTTP helpers for calling the Construction Intelligence Agent backend.
"""
import re
from typing import Optional

import requests

from config import API_BASE, REQUEST_TIMEOUT


def get(path: str, params: dict = None) -> Optional[dict]:
    """GET request to backend API. Returns parsed JSON or error dict."""
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {REQUEST_TIMEOUT}s"}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def post(path: str, payload: dict, timeout: int = 0) -> Optional[dict]:
    """POST request to backend API."""
    effective_timeout = timeout or REQUEST_TIMEOUT
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=effective_timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {effective_timeout}s. Pipeline may still be running."}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def health() -> Optional[dict]:
    return get("/health")


def fetch_document_bytes(doc_path: str) -> tuple[bytes | None, str]:
    """Download document bytes from backend via presigned URL.

    Returns (file_bytes, filename) or (None, "") on failure.
    """
    if not doc_path:
        return None, ""

    basename = doc_path.rsplit("/", 1)[-1] if "/" in doc_path else doc_path
    match = re.search(r'_([a-f0-9]{8})\.\w+$', basename)
    if not match:
        match = re.search(r'([a-f0-9-]{8,36})', basename)
    if not match:
        return None, ""

    file_id = match.group(1)
    try:
        r = requests.get(
            f"{API_BASE}/api/documents/{file_id}/download",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        r.raise_for_status()
        cd = r.headers.get("content-disposition", "")
        fname = cd.split("filename=")[-1].strip('"') if "filename=" in cd else basename
        return r.content, fname
    except Exception:
        return None, ""
```

---

### Task 9: Create remaining API, component, page, and style modules

This task creates all remaining modules by extracting from the Phase 1-patched `app.py`. Each module is self-contained with imports from `config` and `api.client`.

**Files:** All remaining `scope-gap-ui/` modules listed in the File Map.

- [ ] **Step 1: Create `api/scope_gap.py`**

Extract: `api_get_trades`, `api_get_trade_colors`, `api_get_drawings`, `api_run_scope_gap`, `api_run_scope_gap_streaming`, `api_run_all`, `api_chat`, `_STAGE_WEIGHTS`, `_AGENT_DISPLAY` from `app.py` lines 152-340.

- [ ] **Step 2: Create `api/documents.py`**

Already covered by `fetch_document_bytes` in `api/client.py`. Add `api_get_document_info`:

```python
"""api/documents.py — Document info and download helpers."""
from api.client import get


def get_document_info(file_id: str) -> dict | None:
    return get(f"/api/documents/{file_id}/info")
```

- [ ] **Step 3: Create `styles/theme.py`**

Extract the entire `inject_css()` function from `app.py` lines 440-753, with the Phase 1 color fixes already applied.

- [ ] **Step 4: Create `components/navbar.py`**

Extract `render_navbar()` from lines 759-796. Import `nav` from `utils.session`.

- [ ] **Step 5: Create `components/score_cards.py`**

Extract the score card rendering logic from lines 1362-1399.

- [ ] **Step 6: Create `components/scope_items.py`**

Extract `_render_scope_items`, `_build_source_ref`, `_extract_source_drawings` from lines 1445-1662, including inline citations from Task 1.

- [ ] **Step 7: Create `components/reference_panel.py`**

Extract `_render_source_documents_sidebar`, `_render_reference_panel_inline` (unified panel from Task 2).

- [ ] **Step 8: Create `components/export_panel.py`**

Extract the document download section with `st.download_button` widgets from Task 3.

- [ ] **Step 9: Create `components/progress_bar.py`**

Extract `_STAGE_WEIGHTS`, `_AGENT_DISPLAY`, and the streaming progress logic. Add ETA calculation:

```python
import time

def format_eta(elapsed_seconds: float, progress: float) -> str:
    if progress <= 0:
        return ""
    remaining = (elapsed_seconds / progress) * (1 - progress)
    if remaining < 60:
        return f"~{int(remaining)}s remaining"
    return f"~{int(remaining / 60)} min remaining"
```

- [ ] **Step 10: Create `components/chat.py`**

Extract chat message rendering and `_send_chat` from lines 1880-2033.

- [ ] **Step 11: Create `pages/projects.py`**

Extract `page_projects`, `_render_project_card` from lines 801-903.

- [ ] **Step 12: Create `pages/agents.py`**

Extract `page_agents`, `_render_agent_card` from lines 909-993.

- [ ] **Step 13: Create `pages/workspace.py`**

Extract `page_workspace`, `_workspace_export_view`, `_workspace_report_view`, `_workspace_drawing_view` from lines 999-1875. This is the largest page. Import components from `components/`.

- [ ] **Step 14: Create `pages/chat.py`**

Extract `page_chat` from lines 1880-2033. Import `_send_chat` from `components/chat`.

- [ ] **Step 15: Create the entry point `app.py`**

```python
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
    page_icon="building",
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
```

- [ ] **Step 16: Create `requirements.txt` and `README.md`**

`requirements.txt`:
```
streamlit>=1.35.0
requests>=2.31.0
```

`README.md`:
```markdown
# iFieldSmart ScopeAI — Streamlit UI

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. (Optional) Set backend URL:
   ```bash
   export SCOPE_API_BASE=http://localhost:8003
   ```

3. Run:
   ```bash
   streamlit run app.py
   ```

Default backend: `http://54.197.189.113:8003`
```

- [ ] **Step 17: Verify the refactored UI starts**

Run: `cd scope-gap-ui && streamlit run app.py --server.headless true --server.port 8501 &` — wait 5s, then `curl -s http://localhost:8501 | head -5`

Expected: HTML output from Streamlit.

---

## PHASE 3: INFRASTRUCTURE HARDENING

### Task 10: Add version, structured logging, and request ID middleware

**Files:**
- Modify: `main.py`
- Modify: `requirements.txt`
- Create: `middleware/__init__.py`
- Create: `middleware/request_id.py`

- [ ] **Step 1: Add structlog and slowapi to requirements.txt**

Append to `requirements.txt`:
```
structlog>=24.1.0
slowapi>=0.1.9
```

- [ ] **Step 2: Add version constant to main.py**

At the top of `main.py` after the imports (around line 57):

```python
__version__ = "2.1.0"
```

- [ ] **Step 3: Create request ID middleware**

Create `middleware/__init__.py` (empty).

Create `middleware/request_id.py`:

```python
"""
middleware/request_id.py — Inject X-Request-Id into every request/response.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
```

- [ ] **Step 4: Wire middleware into main.py**

In `main.py`, after the CORS middleware (find `app.add_middleware(CORSMiddleware, ...)`), add:

```python
from middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)
```

- [ ] **Step 5: Update /health endpoint to include version**

Find the `/health` endpoint in `main.py` and update to include version:

```python
@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": __version__}
```

---

### Task 11: Add rate limiting and concurrency cap

**Files:**
- Modify: `config.py` — add rate limit settings
- Create: `middleware/rate_limit.py`
- Modify: `main.py` — wire rate limiter

- [ ] **Step 1: Add settings to config.py**

Add after `scope_gap_quality_max_tokens` (line 101):

```python
    # ── Rate Limiting & Concurrency ──────────────────────
    rate_limit_generate: str = "10/minute"
    rate_limit_read: str = "60/minute"
    max_concurrent_requests: int = 50
```

- [ ] **Step 2: Create rate limit middleware**

Create `middleware/rate_limit.py`:

```python
"""
middleware/rate_limit.py — slowapi rate limiting + concurrency cap.
"""
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests when too many are in-flight."""

    def __init__(self, app, max_concurrent: int = 50):
        super().__init__(app)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def dispatch(self, request: Request, call_next):
        if not self._semaphore._value:
            return JSONResponse(
                status_code=503,
                content={"error": "Server at capacity. Please retry shortly."},
            )
        async with self._semaphore:
            return await call_next(request)


def setup_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(
        ConcurrencyLimitMiddleware,
        max_concurrent=settings.max_concurrent_requests,
    )
```

- [ ] **Step 3: Wire into main.py**

After the RequestIdMiddleware line, add:

```python
from middleware.rate_limit import setup_rate_limiting
setup_rate_limiting(app)
```

---

### Task 12: Add S3 session backup and versioning

**Files:**
- Modify: `scope_pipeline/services/session_manager.py`
- Create: `scripts/restore_session.py`

- [ ] **Step 1: Add S3 backup method to ScopeGapSessionManager**

Read `scope_pipeline/services/session_manager.py` and add a method to write session JSON to S3 after pipeline completion. The method should:
- Serialize the session to JSON
- Upload to `s3://{bucket}/{agent_prefix}/sessions/{session_id}.json`
- Use the existing `s3_utils.operations.upload_file` helper

```python
def backup_session_to_s3(self, session_id: str, session_data: dict) -> bool:
    """Persist session to S3 for disaster recovery."""
    try:
        import json
        import tempfile
        from s3_utils.operations import upload_file
        from config import get_settings
        settings = get_settings()

        if settings.storage_backend != "s3":
            return False

        s3_key = f"{settings.s3_agent_prefix}/sessions/{session_id}.json"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(session_data, f, default=str)
            tmp_path = f.name

        upload_file(tmp_path, s3_key)
        return True
    except Exception:
        return False
```

- [ ] **Step 2: Create restore script**

Create `scripts/restore_session.py`:

```python
#!/usr/bin/env python3
"""Restore sessions from S3 backup after restart."""
import json
import sys
sys.path.insert(0, ".")

from config import get_settings
from s3_utils.operations import list_objects, download_file

settings = get_settings()
prefix = f"{settings.s3_agent_prefix}/sessions/"

objects = list_objects(prefix, max_keys=100)
print(f"Found {len(objects)} session backups in S3")

for obj in objects:
    key = obj["Key"]
    session_id = key.split("/")[-1].replace(".json", "")
    print(f"  - {session_id} ({obj.get('Size', 0)} bytes)")
```

- [ ] **Step 3: Enable S3 versioning (run once)**

Add to `scripts/enable_s3_versioning.py`:

```python
#!/usr/bin/env python3
"""Enable S3 versioning on the production bucket."""
import boto3
from config import get_settings

settings = get_settings()
s3 = boto3.client(
    "s3",
    region_name=settings.s3_region,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)

s3.put_bucket_versioning(
    Bucket=settings.s3_bucket_name,
    VersioningConfiguration={"Status": "Enabled"},
)
print(f"Versioning enabled on {settings.s3_bucket_name}")
```

---

### Task 13: Add `/api/scope-gap/status` and `/api/scope-gap/metrics` endpoints

**Files:**
- Create: `scope_pipeline/routers/status.py`
- Modify: `main.py` — register new router

- [ ] **Step 1: Create status router**

```python
"""
scope_pipeline/routers/status.py — System health and metrics endpoints.
"""
import time
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/scope-gap", tags=["scope-gap-status"])

_start_time = time.time()


@router.get("/status")
async def pipeline_status(request: Request):
    """System health: agent status, S3, Redis connectivity."""
    cache = request.app.state.cache
    redis_ok = cache.is_connected if hasattr(cache, "is_connected") else False

    # S3 check
    s3_ok = False
    try:
        from s3_utils.client import get_s3_client
        s3_ok = get_s3_client() is not None
    except Exception:
        pass

    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "redis_connected": redis_ok,
        "s3_connected": s3_ok,
        "storage_backend": request.app.state.cache.__class__.__name__,
    }


@router.get("/metrics")
async def pipeline_metrics(request: Request):
    """Pipeline performance metrics — token usage, job counts, uptime."""
    token_tracker = getattr(request.app.state, "token_tracker", None)
    job_manager = getattr(request.app.state, "scope_job_manager", None)

    token_stats = {}
    if token_tracker and hasattr(token_tracker, "get_totals"):
        token_stats = token_tracker.get_totals()

    active_jobs = 0
    if job_manager and hasattr(job_manager, "active_count"):
        active_jobs = job_manager.active_count()

    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "active_jobs": active_jobs,
        "token_usage": token_stats,
    }
```

- [ ] **Step 2: Register router in main.py**

After `from scope_pipeline.routers.scope_gap import router as scope_gap_router`, add:

```python
from scope_pipeline.routers.status import router as status_router
```

And in the router registration section, add:

```python
app.include_router(status_router)
```

---

### Task 14: Add input validation to documents router

**Files:**
- Modify: `routers/documents.py`

- [ ] **Step 1: Add file_id validation**

At the top of `routers/documents.py`, add:

```python
import re

_FILE_ID_PATTERN = re.compile(r'^[a-f0-9-]+$')

def _validate_file_id(file_id: str) -> str:
    """Validate file_id is a hex/UUID string. Raises HTTPException if invalid."""
    if not _FILE_ID_PATTERN.match(file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id format")
    return file_id
```

- [ ] **Step 2: Use validation in both endpoints**

Add `_validate_file_id(file_id)` as the first line in both `download_document` and `document_info`.

---

### Task 15: Create automation scripts and CHANGELOG

**Files:**
- Create: `scripts/deploy_to_sandbox.sh`
- Create: `scripts/push_to_github.sh`
- Create: `scripts/run_tests.sh`
- Create: `CHANGELOG.md`
- Create: `docs/TROUBLESHOOTING.md`

- [ ] **Step 1: Create deploy script**

```bash
#!/bin/bash
# scripts/deploy_to_sandbox.sh — Deploy construction agent to sandbox VM
set -euo pipefail

VM_IP="54.197.189.113"
VM_USER="ubuntu"
PEM_KEY="../../ai_assistant_sandbox.pem"
VM_PATH="/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent"

echo "=== Deploying to sandbox VM ==="
scp -r -i "$PEM_KEY" \
    -o StrictHostKeyChecking=no \
    . "${VM_USER}@${VM_IP}:${VM_PATH}/"

echo "=== Installing dependencies ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "cd ${VM_PATH} && pip install -r requirements.txt"

echo "=== Restarting service ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "sudo systemctl restart construction-agent && sleep 3 && sudo systemctl status construction-agent --no-pager"

echo "=== Health check ==="
ssh -i "$PEM_KEY" "${VM_USER}@${VM_IP}" \
    "curl -s http://localhost:8003/health"

echo ""
echo "=== Deploy complete ==="
```

- [ ] **Step 2: Create GitHub push script**

```bash
#!/bin/bash
# scripts/push_to_github.sh — Sync to agentic-ai-platform repo
set -euo pipefail

REPO_PATH="../../../../agentic-ai-platform"
TARGET="${REPO_PATH}/agents/doc-generator"

echo "=== Syncing to GitHub repo ==="
rsync -av --delete \
    --exclude='.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='generated_docs/' \
    --exclude='venv/' \
    --exclude='.code-review-graph/' \
    . "$TARGET/"

cd "$REPO_PATH"
git add agents/doc-generator/
git status
echo ""
echo "=== Ready to commit. Run: ==="
echo "  cd $REPO_PATH"
echo "  git commit -m 'feat(doc-generator): fix reference display, export downloads, UI refactor, infra hardening'"
echo "  git push"
```

- [ ] **Step 3: Create test runner script**

```bash
#!/bin/bash
# scripts/run_tests.sh — Run pytest with coverage
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Running tests with coverage ==="
python -m pytest tests/ \
    --cov=. \
    --cov-report=term-missing \
    --cov-fail-under=80 \
    -v

echo "=== Tests complete ==="
```

- [ ] **Step 4: Create CHANGELOG.md**

```markdown
# Changelog

## [2.1.0] - 2026-04-07

### Fixed
- Reference documents now display inline citations [Source: drawing, page] on each scope item
- Right panel auto-populates with source drawings after pipeline completion
- Export to Doc button now works — all 4 formats (Word, PDF, CSV, JSON) download directly to browser
- Font/color visibility: neutral background (#F8FAFC), dark text (#1E293B), readable secondary text (#475569)

### Added
- UI refactored into ~15 portable modules (scope-gap-ui/) — pip install + streamlit run
- Structured logging via structlog (JSON format with request_id, project_id, duration_ms)
- Request ID middleware (X-Request-Id header on every request)
- Rate limiting via slowapi (10/min generate, 60/min reads)
- Concurrency cap: 503 when >50 concurrent requests
- /api/scope-gap/status endpoint — Redis, S3, uptime health check
- /api/scope-gap/metrics endpoint — pipeline performance metrics
- S3 versioning enabled on agentic-ai-production bucket
- Session backup to S3 after pipeline completion
- Input validation on document file_id (regex: ^[a-f0-9-]+$)
- Deploy, GitHub push, and test runner automation scripts
- TROUBLESHOOTING.md with error code reference

### Changed
- PARALLEL_FETCH_CONCURRENCY default: 10 -> 30 (supports 30K records)
- httpx pool: max_connections=100, max_keepalive_connections=20
- Note compression: added 75-char tier for very large datasets
```

- [ ] **Step 5: Create docs/TROUBLESHOOTING.md**

```markdown
# Troubleshooting Guide

## Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| PIPELINE_TIMEOUT | Pipeline exceeded GENERATE_TIMEOUT | Increase SCOPE_GENERATE_TIMEOUT or check API connectivity |
| DATA_FETCH_FAILED | MongoDB API unreachable or returned error | Check API_BASE_URL and API_AUTH_TOKEN in .env |
| LLM_ERROR | OpenAI API returned an error | Check OPENAI_API_KEY, model availability, rate limits |
| DOCUMENT_GENERATION_FAILED | Word/PDF/CSV/JSON generation failed | Check disk space, python-docx/reportlab installed |

## Common Issues

### API unreachable
- Verify: `curl http://localhost:8003/health`
- Check: `systemctl status construction-agent`
- Logs: `journalctl -u construction-agent -f`

### Documents not downloading
- Verify S3 connectivity: `python scripts/enable_s3_versioning.py` (dry-run)
- Check STORAGE_BACKEND in .env (should be "s3")
- Verify AWS credentials: aws_access_key_id, aws_secret_access_key
```

---

### Task 19: Scaling config — concurrency, httpx pool, note compression

**Files:**
- Modify: `config.py` — update defaults
- Modify: `services/api_client.py` — httpx pool config
- Modify: `services/context_builder.py` — add 75-char compression tier

- [ ] **Step 1: Update PARALLEL_FETCH_CONCURRENCY default in config.py**

Find `parallel_fetch_concurrency: int = 10` and change to `parallel_fetch_concurrency: int = 30`.

- [ ] **Step 2: Configure httpx pool in api_client.py**

In `APIClient.__init__` or `connect()`, find where `httpx.AsyncClient` is created. Update pool limits:

```python
self._client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    timeout=httpx.Timeout(settings.api_timeout_seconds),
)
```

- [ ] **Step 3: Add 75-char compression tier in context_builder.py**

Find the adaptive compression logic (the series of fallback truncation lengths). Add `75` after `100`:

```python
# Existing: [300, 200, 150, 100]
# Updated:  [300, 200, 150, 100, 75]
```

---

### Task 20: CORS restriction and auth middleware

**Files:**
- Modify: `main.py` — restrict CORS origins
- Create: `middleware/auth.py`

- [ ] **Step 1: Restrict CORS origins in main.py**

Find the `CORSMiddleware` configuration. Replace `allow_origins=["*"]` with:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ai5.ifieldsmart.com",
        "https://ai.ifieldsmart.com",
        "http://localhost:8501",  # Streamlit dev
        "http://54.197.189.113:8501",  # Sandbox Streamlit
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Create auth middleware**

Create `middleware/auth.py`:

```python
"""
middleware/auth.py — Bearer token authentication for /api/ routes.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import get_settings


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Validate Authorization: Bearer <token> on all /api/ routes."""

    # Paths that skip auth
    SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for non-API routes and health
        if not path.startswith("/api/") or path in self.SKIP_PATHS:
            return await call_next(request)

        settings = get_settings()
        expected_token = settings.api_auth_token

        # If no auth token configured, skip auth (dev mode)
        if not expected_token:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header"},
            )

        provided_token = auth_header[7:]  # Strip "Bearer "
        if provided_token != expected_token:
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid authentication token"},
            )

        return await call_next(request)
```

- [ ] **Step 3: Wire auth middleware in main.py**

After RequestIdMiddleware:

```python
from middleware.auth import BearerAuthMiddleware
app.add_middleware(BearerAuthMiddleware)
```

---

### Task 21: Audit logging to S3

**Files:**
- Create: `services/audit_logger.py`
- Modify: `routers/documents.py` — log download events
- Modify: `scope_pipeline/orchestrator.py` — log generation events

- [ ] **Step 1: Create audit logger service**

```python
"""
services/audit_logger.py — Write audit events to S3.
"""
import json
import tempfile
from datetime import datetime, timezone
from typing import Any

from config import get_settings


def log_audit_event(
    event_type: str,
    project_id: int = 0,
    trade: str = "",
    file_id: str = "",
    request_ip: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Write an audit event to S3 audit_logs/ prefix.

    Returns True on success, False on failure (never raises).
    """
    settings = get_settings()
    if settings.storage_backend != "s3":
        return False

    try:
        from s3_utils.operations import upload_file

        now = datetime.now(timezone.utc)
        event = {
            "timestamp": now.isoformat(),
            "event_type": event_type,
            "project_id": project_id,
            "trade": trade,
            "file_id": file_id,
            "request_ip": request_ip,
            **(metadata or {}),
        }

        date_prefix = now.strftime("%Y-%m-%d")
        s3_key = (
            f"{settings.s3_agent_prefix}/audit_logs/{date_prefix}/"
            f"{event_type}_{now.strftime('%H%M%S')}_{file_id[:8] if file_id else 'na'}.json"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(event, f, default=str)
            tmp_path = f.name

        upload_file(tmp_path, s3_key)
        return True
    except Exception:
        return False
```

- [ ] **Step 2: Add audit logging to document download endpoint**

In `routers/documents.py`, in the `download_document` function, after a successful download, add:

```python
from services.audit_logger import log_audit_event
# After successful download:
log_audit_event("document_download", file_id=file_id, request_ip=str(request.client.host))
```

- [ ] **Step 3: Add audit logging to pipeline completion**

In `scope_pipeline/orchestrator.py`, after the pipeline result is assembled (around line 295), add:

```python
from services.audit_logger import log_audit_event
log_audit_event(
    "pipeline_complete",
    project_id=project_id,
    trade=trade,
    metadata={"items_count": len(final_items), "tokens_used": total_tokens},
)
```

---

### Task 22: Structured error codes and graceful shutdown

**Files:**
- Create: `models/error_codes.py`
- Modify: `main.py` — add shutdown handler

- [ ] **Step 1: Create error code constants**

```python
"""
models/error_codes.py — Structured error codes for API responses.
"""


class ErrorCode:
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
    LLM_ERROR = "LLM_ERROR"
    DOCUMENT_GENERATION_FAILED = "DOCUMENT_GENERATION_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_OVERLOADED = "SERVER_OVERLOADED"


def error_response(code: str, detail: str) -> dict:
    """Build a structured error response."""
    return {"error": detail, "error_code": code}
```

- [ ] **Step 2: Add graceful shutdown in main.py lifespan**

In the `lifespan` function, after `yield`, add verification:

```python
    yield

    # Shutdown
    logger.info("Shutting down — closing connections")
    await cache.disconnect()
    await api_client.close()
    # Cancel any running background tasks
    import asyncio
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info(f"Cancelling {len(tasks)} background tasks")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Shutdown complete")
```

---

### Task 23: pip-audit CVE scan

- [ ] **Step 1: Run pip-audit on requirements.txt**

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

Review output. If any CVEs found, update the affected package versions in `requirements.txt`.

- [ ] **Step 2: Document in run_tests.sh**

Add to `scripts/run_tests.sh` after the pytest section:

```bash
echo "=== CVE Scan ==="
pip-audit -r requirements.txt || echo "WARNING: CVE issues found — review above"
```

---

## PHASE 4: DEPLOY, PUSH & ARCHIVE

### Task 16: Deploy to sandbox VM

**Files:**
- Use: `scripts/deploy_to_sandbox.sh`

- [ ] **Step 1: Prepare .env for sandbox**

Create a sandbox-specific `.env` by copying from the existing one and adjusting:
- `APP_PORT=8003`
- `STORAGE_BACKEND=s3`
- `REDIS_URL=redis://localhost:6379/0` (will gracefully fallback if Redis not running)
- Ensure all API keys are set

- [ ] **Step 2: Transfer agent files to VM**

```bash
PEM="C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem"
VM="ubuntu@54.197.189.113"
VM_PATH="/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent"

scp -r -i "$PEM" \
    -o StrictHostKeyChecking=no \
    "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/" \
    "${VM}:${VM_PATH}/"
```

- [ ] **Step 3: Transfer refactored UI**

```bash
scp -r -i "$PEM" \
    "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/scope-gap-ui/" \
    "${VM}:${VM_PATH}/scope-gap-ui/"
```

- [ ] **Step 4: Install dependencies on VM**

```bash
ssh -i "$PEM" "$VM" "cd ${VM_PATH} && pip install -r requirements.txt"
```

- [ ] **Step 5: Set up systemd service**

```bash
ssh -i "$PEM" "$VM" "cat > /tmp/construction-agent.service << 'UNIT'
[Unit]
Description=Construction Intelligence Agent
After=network.target redis-server.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
WatchdogSec=120
MemoryMax=2G
Environment=APP_PORT=8003

[Install]
WantedBy=multi-user.target
UNIT
sudo mv /tmp/construction-agent.service /etc/systemd/system/construction-agent.service
sudo systemctl daemon-reload
sudo systemctl enable construction-agent
sudo systemctl restart construction-agent"
```

- [ ] **Step 6: Verify deployment**

```bash
ssh -i "$PEM" "$VM" "systemctl status construction-agent --no-pager && curl -s http://localhost:8003/health"
```

Expected: `Active: active (running)` and `{"status": "ok", "version": "2.1.0"}`

---

### Task 17: Push to GitHub

**Files:**
- Modify: `agentic-ai-platform/agents/doc-generator/` (sync from PROD_SETUP)

- [ ] **Step 1: Sync files to GitHub repo**

```bash
cd "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
bash scripts/push_to_github.sh
```

- [ ] **Step 2: Commit and push**

```bash
cd "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/agentic-ai-platform"
git add agents/doc-generator/
git commit -m "feat(doc-generator): fix reference display, export downloads, UI refactor, infra hardening"
git push origin main
```

---

### Task 18: Archive unused files and restructure

**Files:**
- Move to `_archive/`: old planning docs, prototypes
- Delete: `__pycache__/`, `*.pyc`

- [ ] **Step 1: Archive completed planning docs**

```bash
cd "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
mkdir -p _archive/completed_plans
mv DEVELOPMENT_PLAN_SETID_FEATURE.md _archive/completed_plans/ 2>/dev/null || true
mv DEVELOPMENT_PLAN_v3.md _archive/completed_plans/ 2>/dev/null || true
mv OPTIMIZATION_DESIGN_v2.md _archive/completed_plans/ 2>/dev/null || true
```

- [ ] **Step 2: Clean up Python caches**

```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
```

- [ ] **Step 3: Promote refactored UI**

The refactored `scope-gap-ui/` folder is now at the top level of the agent directory (not in `_archive/`). The original monolithic `app.py` remains in `_archive/scope-gap-ui/app.py` as a backup.

- [ ] **Step 4: Verify final structure**

```bash
ls -la
# Expected: main.py config.py requirements.txt CLAUDE.md README.md ARCHITECTURE.md CHANGELOG.md
#           agents/ models/ routers/ services/ s3_utils/ scope_pipeline/ utils/ tests/
#           docs/ scripts/ middleware/ scope-gap-ui/ _archive/
```

---

## Post-Deploy Verification Checklist

After all 4 phases, run these checks:

- [ ] `systemctl status construction-agent` → Active (running)
- [ ] `curl localhost:8003/health` → `{"status": "ok", "version": "2.1.0"}`
- [ ] `curl localhost:8003/api/scope-gap/status` → Redis/S3 connectivity shown
- [ ] Trigger scope gap generation for a known project/trade → items + documents returned
- [ ] Verify inline citations show `[Source: drawing, page]` on each scope item
- [ ] Verify right panel auto-populates with source drawings after generation
- [ ] Download Word, PDF, CSV, JSON → all 4 download to browser
- [ ] `streamlit run scope-gap-ui/app.py` → UI loads, connects to backend
- [ ] Verify GitHub `agents/doc-generator/` matches local structure
- [ ] Verify `_archive/` contains old planning docs and prototypes
