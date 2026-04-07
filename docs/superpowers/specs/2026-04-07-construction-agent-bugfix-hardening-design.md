# Construction Intelligence Agent: Bug Fixes, UI Refactor & Infrastructure Hardening

**Date:** 2026-04-07
**Status:** Approved
**Approach:** Phased Delivery (4 phases, each independently deployable)

---

## Context

The construction intelligence agent (`PORT 8003`) is a production-grade FastAPI application with a 7-agent scope gap extraction pipeline (Phase 11), multi-trade orchestration (Phase 12), and a Streamlit-based demo UI. Two critical bugs have been reported, and a comprehensive infrastructure review is required before scaling to 50 concurrent users and 30K drawing records.

**Codebase:**
- Backend: `PROD_SETUP/construction-intelligence-agent/` (~40 Python modules)
- UI: `_archive/scope-gap-ui/app.py` (2093 lines, monolithic Streamlit app)
- GitHub: `AniruddhaPKawarase/agentic-ai-platform` > `agents/doc-generator/`
- Sandbox VM: `54.197.189.113:/home/ubuntu/chatbot/aniruddha/vcsai`

---

## Phase 1: Critical Bug Fixes

### Bug 1: Reference Documents Not Displaying

**Root Cause:** Two gaps in the Streamlit UI:

1. **No inline citations.** `_render_scope_items()` (app.py:1445-1523) shows each item's `text`, `csi_code`, `confidence`, and `page` but does NOT render `drawing_name` or `source_snippet` inline. Source info only appears when the user clicks the `🔗` button.

2. **Right panel state conflict.** The right column (`col_ref` at line 1438) switches between `_render_source_documents_sidebar` (aggregate view, default) and `_render_reference_panel` (item-level, opened by `🔗`). When an item ref panel opens, the aggregate source list disappears entirely.

**Fix:**

**Note:** Phase 1 fixes are applied to the monolithic `app.py` directly. Phase 2 then refactors into modules. This avoids a dependency loop.

| # | Change | File(s) | Detail |
|---|--------|---------|--------|
| 1 | Add inline citation | `app.py` (`_render_scope_items`) | Below each scope item text, render `[Source: {drawing_name}, p.{page}]` in `#475569` italic text. Use `source_snippet` as tooltip. After Phase 2 refactor, this moves to `components/scope_items.py` |
| 2 | Unified right panel | `app.py` (`_render_reference_panel`, `_render_source_documents_sidebar`) | Always show aggregate source drawings at top of right column. When user clicks `🔗`, expand an item-level detail section below (not replacing the aggregate view). Use `st.expander` for item refs within the sidebar |
| 3 | Auto-populate on completion | `app.py` (`_workspace_report_view`) | After pipeline completes, `_extract_source_drawings(result)` already runs at line 1431. Ensure `ref_panel_open` stays `False` so the aggregate view shows by default |
| 4 | Verify backend data | `scope_pipeline/orchestrator.py` | Confirm `items[].drawing_name`, `source_snippet`, `drawing_refs`, `page` are populated in the pipeline result. Trace through all 7 agents to ensure source fields propagate |

### Bug 2: Export to Doc Button Not Working

**Root Cause:** Two broken UI elements:

1. **Line 1314:** `st.button("Export DOCX", key="export_docx")` has no click handler — the button exists but does nothing.
2. **Lines 1401-1427:** Document download section renders styled `<div>` cards for Word/PDF/CSV/JSON but they are static HTML — not clickable, no download action.

The backend is fully functional: `DocumentAgent.generate_all()` creates all 4 formats, returns `DocumentSet` with paths. The `routers/documents.py` has proper download endpoints with S3 presigned URLs.

**Fix:**

**Note:** Phase 1 fixes are applied to monolithic `app.py`. Phase 2 refactors into modules.

| # | Change | File(s) | Detail |
|---|--------|---------|--------|
| 1 | Wire Export button | `app.py` (line 1314 area) | Replace the static `st.button` with a format selector (radio: Word/PDF/CSV/JSON) + `st.download_button` that fetches file bytes from backend. After Phase 2, moves to `components/export_panel.py` |
| 2 | Download implementation | `app.py` (new helper function) | New helper: `fetch_document_bytes(doc_path)` — extracts file_id from doc_path, calls backend `/api/documents/{file_id}/download`, follows redirect to S3 presigned URL, returns bytes for `st.download_button` |
| 3 | Replace static cards | `app.py` (lines 1401-1427) | Replace the 4 styled `<div>` cards with 4 `st.download_button` widgets, each fetching the appropriate format. Direct browser download |
| 4 | Handle S3 paths | `app.py` (new helper) | Parse `documents.word_path` from pipeline result. Extract file_id (UUID portion). Call `/api/documents/{file_id}/download` which returns presigned URL redirect. Use `requests.get(allow_redirects=True)` to fetch bytes |

### Bug 3: Font/Color Visibility

**Root Cause:** CSS in `inject_css()` uses light grays (`#94A3B8`, `#CBD5E1`) for primary text, invisible against light backgrounds.

**Fix:**

| Element | Current | Fixed |
|---------|---------|-------|
| Page background | Mixed | `#F8FAFC` consistent |
| Primary text (scope items, headings) | Various | `#0F172A` |
| Secondary text (labels, metadata) | `#94A3B8` | `#475569` |
| Card backgrounds | `#fff` | `#FFFFFF` with `border: 1px solid #E2E8F0` |
| Section headers | Mixed colors | `#1E293B`, 14px, weight 700 |
| Scope item text | No explicit color | `#1E293B`, 13px |

---

## Phase 2: UI Refactor & UX

### Modular Architecture

Break `app.py` (2093 lines) into ~15 focused modules:

```
scope-gap-ui/
├── app.py                    # Entry point (~50 lines) — page router only
├── config.py                 # API_BASE from env vars, timeouts, constants
├── requirements.txt          # streamlit>=1.35.0, requests>=2.31.0
├── README.md                 # Setup: pip install -r requirements.txt && streamlit run app.py
│
├── api/
│   ├── __init__.py
│   ├── client.py             # _get(), _post(), error handling, retries
│   ├── scope_gap.py          # Streaming + sync pipeline calls
│   └── documents.py          # fetch_document_bytes(), document info
│
├── components/
│   ├── __init__.py
│   ├── navbar.py             # Top navigation bar
│   ├── score_cards.py        # Completeness, quality, coverage cards
│   ├── scope_items.py        # Item list with inline citations
│   ├── reference_panel.py    # Unified right sidebar (aggregate + item-level)
│   ├── export_panel.py       # Format selector + download buttons
│   ├── progress_bar.py       # SSE streaming progress with ETA
│   └── chat.py               # Chat interface
│
├── pages/
│   ├── __init__.py
│   ├── projects.py           # Project selection
│   ├── agents.py             # Agent selection
│   ├── workspace.py          # Export/Report/Drawing sub-views
│   └── chat.py               # Conversational Q&A
│
├── styles/
│   ├── __init__.py
│   └── theme.py              # All CSS — neutral palette, dark fonts
│
└── utils/
    ├── __init__.py
    └── session.py            # Session state init, defaults, helpers
```

### Portability Requirements

- `config.py` reads `SCOPE_API_BASE` from environment (default: `http://54.197.189.113:8003`)
- `requirements.txt` is self-contained — `pip install -r requirements.txt` then `streamlit run app.py`
- No hardcoded IPs in any module except `config.py` defaults
- Works on any OS (Windows, Linux, Mac)

### Progress Bar Enhancement

- Move existing `_STAGE_WEIGHTS` and `_AGENT_DISPLAY` to `components/progress_bar.py`
- Add ETA calculation: `remaining_seconds = (elapsed / progress) * (1 - progress)`
- Show: `[=====>    ] 65% — Classification | ~2 min remaining`
- On completion: green success banner, auto-display results

### Color Palette

Neutral background + dark fonts throughout. See Phase 1 Bug 3 table for specific values.

---

## Phase 3: Infrastructure Hardening

### 1) Scaling (50 users, 30K records)

- `PARALLEL_FETCH_CONCURRENCY`: 15 → 30 for 30K-record projects
- Uvicorn workers: `--workers 4` in systemd service
- httpx pool: `max_connections=100`, `max_keepalive_connections=20`
- `limit_concurrency` middleware: reject with 503 when >50 active requests

### 2) Optimization

- Adaptive note compression: add 75-char tier for 30K+ datasets
- Pipeline result caching in S3: key = `cache/{project_id}_{trade}_{set_ids_hash}.json`, serve cached on repeat requests (cache TTL: 1 hour, invalidated on new pipeline run)
- Document caching: pipeline still generates all 4 formats on first run (no behavior change). On repeat requests, serve from S3 cache instead of regenerating

### New Dependencies (add to requirements.txt)

- `structlog>=24.1.0` — structured JSON logging (Phase 3.3)
- `slowapi>=0.1.9` — rate limiting middleware (Phase 3.4)
- `pip-audit` — dev dependency for CVE scanning (Phase 3.5, not in production requirements)

### 3) Performance Metrics

- Replace `print()` with `structlog` JSON logging: `request_id`, `project_id`, `trade`, `duration_ms`, `tokens_used`
- FastAPI middleware: log `method`, `path`, `status_code`, `duration_ms` per request
- `GET /api/scope-gap/metrics`: avg pipeline time, cache hit rate, active jobs, error rate
- Token cost tracking already in `token_tracker.py` — surface in metrics

### 4) Request Handling

- UUID `X-Request-Id` header per request, propagated through all logs
- Graceful timeout: return partial results with `"status": "partial"` instead of 504
- Idempotency: if same `project_id:trade` already running, return existing job
- `slowapi` rate limiting: 10 req/min per IP for generate, 60 req/min for reads

### 5) Vulnerability

- Input validation: `project_id > 0`, `trade` length <= 100, regex for `file_id`: `^[a-f0-9-]+$`
- S3 key injection prevention: validate file_id format before S3 lookup
- Error sanitization: never expose stack traces in API responses
- `pip-audit` on `requirements.txt` for CVE detection
- CORS: restrict `allow_origins` to known domains

### 6) SDLC Parameters

- Test coverage target: 77% → 85%+ (add tests for bug fixes + new endpoints)
- `scripts/run_tests.sh`: pytest with coverage, fail if <80%
- `__version__ = "2.1.0"` in `main.py`, surfaced in `/health`
- `CHANGELOG.md` for this release

### 7) Compliance

- Audit logging: all document generation/download events to S3 `audit_logs/` prefix
- Data retention: S3 lifecycle rule — 90-day TTL for generated docs, 30-day for sessions
- Token rotation: `/api/admin/rotate-token` endpoint + rotation SOP doc

### 8) Disaster Recovery & Backup

- Enable S3 versioning on `agentic-ai-production` bucket
- Session backup to S3: write session JSON to `s3://.../sessions/` after each pipeline completion
- Pipeline result index: `s3://.../result_index/{project_id}.json` listing all completed runs
- `scripts/restore_session.py`: reload sessions from S3 after restart

### 9) Support & Helpdesk Framework

- Structured error codes: `PIPELINE_TIMEOUT`, `DATA_FETCH_FAILED`, `LLM_ERROR`, `DOCUMENT_GENERATION_FAILED`
- `docs/TROUBLESHOOTING.md`: maps error codes to explanations + fix steps
- `GET /api/scope-gap/status`: system health, last run, Redis/S3 connectivity

### 10) System Maintenance

- Systemd: `Restart=always`, `RestartSec=5`, `WatchdogSec=120`, `MemoryMax=2G`
- Log rotation via journald, 30-day retention
- Health endpoint reports disk usage, alerts at 80% threshold
- Graceful shutdown: verify no orphan tasks on SIGTERM

### 11) Network & Security Requirements

- Nginx upstream `/construction/*` → `localhost:8003` (already configured)
- Firewall: port 8003 internal only (verify `ufw`)
- HTTPS via Let's Encrypt on production; HTTP on sandbox (documented)
- Auth middleware: validate `Authorization: Bearer <token>` on all `/api/` routes

### 12) Resource Management: Efficiency through Automation

- `scripts/deploy_to_sandbox.sh`: rsync → restart systemd → verify health
- `scripts/push_to_github.sh`: sync PROD_SETUP → agentic-ai-platform/agents/doc-generator/
- Cron: delete local `/tmp` docs older than 24h (S3 is source of truth)
- Startup config validation: fail fast listing missing env vars

---

## Phase 4: Deploy, Push & Archive

### 4A: Sandbox VM Deployment

- **Target:** `54.197.189.113:/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent/`
- **Transfer:** `scp -r -i ai_assistant_sandbox.pem`
- **Env:** `.env` with sandbox values, `STORAGE_BACKEND=s3`, Redis fallback to S3
- **Dependencies:** `pip install -r requirements.txt` in venv
- **Systemd:** Install `construction-agent.service` with `Restart=always`
- **UI:** `scope-gap-ui/` deployed alongside agent, runnable via `streamlit run`

### 4B: GitHub Push

- **Repo:** `AniruddhaPKawarase/agentic-ai-platform`
- **Directory:** `agents/doc-generator/`
- **Excluded:** `.env`, `__pycache__/`, `*.pyc`, `generated_docs/`, `venv/`
- **Commit:** `feat(doc-generator): fix reference display, export downloads, UI refactor, infra hardening`

### 4C: Folder Restructure

**Keep (active agent files):**
- `main.py`, `config.py`, `requirements.txt`, `.env.example`
- `agents/`, `models/`, `routers/`, `services/`, `s3_utils/`, `scope_pipeline/`, `utils/`, `tests/`
- `docs/`, `scripts/`
- `scope-gap-ui/` (refactored, promoted from _archive)
- `CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`

**Archive (move to `_archive/`):**
- Original monolithic `scope-gap-ui/app.py` (backup)
- `ifieldsmart-scope-ai.jsx`, `scopegap-agent-v3.html`, `index.html` (prototypes)
- Completed planning docs: `DEVELOPMENT_PLAN_SETID_FEATURE.md`, `DEVELOPMENT_PLAN_v3.md`, `OPTIMIZATION_DESIGN_v2.md`

**Delete:**
- `__pycache__/` directories, `*.pyc` files, orphaned temp files

### 4D: Post-Deploy Verification

| # | Check | Pass Criteria |
|---|-------|--------------|
| 1 | `systemctl status construction-agent` | Active (running) |
| 2 | `curl localhost:8003/health` | `{"status": "ok"}` |
| 3 | `curl localhost:8003/api/scope-gap/status` | All subsystems green |
| 4 | Scope gap generation test | Pipeline completes, returns items + documents |
| 5 | Inline citations visible | Each scope item shows `[Source: drawing, page]` |
| 6 | Right panel auto-populated | Source drawings list appears after generation |
| 7 | Export Word download | `.docx` downloads directly to browser |
| 8 | Export PDF/CSV/JSON | All 3 additional formats download correctly |
| 9 | Progress bar streaming | Real-time progress with ETA during pipeline |
| 10 | S3 document storage | Generated docs appear in S3 bucket |
| 11 | Session backup in S3 | Session JSON saved after pipeline completion |
| 12 | GitHub sync verified | `agents/doc-generator/` matches local structure |

---

## User Answers Reference

| # | Question | Answer |
|---|----------|--------|
| Q1 | Reference display | C) Both inline citations AND auto-populated right panel |
| Q2 | Export formats | B) All four (Word, PDF, CSV, JSON) with user choice |
| Q3 | Download behavior | Direct to browser |
| Q4 | Concurrent users | 50 |
| Q5 | Max records | 30K |
| Q6 | Latency targets | No hard target; show progress bar |
| Q7 | Frontend | Streamlit only (demo/testing) |
| Q8 | Sandbox mirror | Yes, mirror production |
| Q9 | Redis on sandbox | No, later; keep option; use S3 for sessions |
| Q10 | Compliance | Apply if possible this phase, otherwise later |
| Q11 | Token rotation | Rotate on schedule |
| Q12 | Watermarking | No |
| Q13 | S3 versioning | Add it |
| Q14 | RPO | Save to S3 immediately, display on UI |
| Q15 | Redis backup | Use S3 for now, shift to Redis later |
| Q16 | Systemd | Auto-start |
| Q17 | GitHub repo | `agentic-ai-platform/agents/doc-generator/` |
| Q18 | Branch | Push to agents/doc-generator in main |
| Q19 | Logging | Yes, structured JSON logs |
| Q20 | Health checks | Yes, pipeline-specific |
| Q21 | UI refactor | Yes, modular; portable; shareable |
| Q22 | Branding | Functional fixes + neutral palette + dark fonts |

---

## Technical Constraints

- Python 3.11+, FastAPI 0.115, Streamlit 1.35+
- OpenAI gpt-4.1-mini (chat), gpt-4.1 (scope pipeline)
- S3 bucket: `agentic-ai-production`, region `us-east-1`
- MongoDB API: `https://mongo.ifieldsmart.com` (external, paginated at 50/page)
- Sandbox VM: Ubuntu, SSH via PEM key
- No Redis on sandbox initially — all persistence via S3 + local fallback
