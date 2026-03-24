# DEVELOPMENT_PLAN_v3.md — Project Name + Record Completeness + Latency

**Date:** 2026-03-18
**Author:** Claude Code (Sonnet 4.6) — pre-development Q&A session
**Status:** APPROVED — ready for development

---

## User Story

> As a construction professional using the Construction Intelligence Agent,
> I want to see the **project name** (e.g., "Granville Hotel") instead of only the project ID in all outputs,
> And I want **every single record** for a trade to be reliably fetched from the database without any being skipped,
> And I want the **full response** (including Word document generation) to complete within **3 minutes** for normal datasets and within **5–10 minutes** for very large datasets.

---

## Pre-Development Q&A — Confirmed Answers (2026-03-18)

| # | Question | Answer |
|---|----------|--------|
| 1 | Project Name format? | `Granville Hotel (ID: 7298)` everywhere |
| 2 | Where does project name appear? | Document header, footer, filename, `ChatResponse` JSON, session, cache keys — **all of them** |
| 3 | Latency requirement? | Full response including Word doc ≤ 3 min; for thousands of records, 5–10 min acceptable |
| 4 | Record completeness failure mode? | **Known failure**: getting 50 records instead of 154, pages being skipped |
| 5 | SQL connection strategy? | On failure: **fall back to project ID** + include reason why it failed |
| 6 | Streaming status? | Frontend integration **in progress**; backend `/api/chat/stream` already exists — no backend changes needed |

**SQL Source:**
- Host: `ifieldsmartencrypted.ctzuheyxit1m.us-east-1.rds.amazonaws.com`
- Port: `1433`
- Database: `iFMasterDatabase_1`
- Credentials: from `SQL-Intelligence-Agent/.env`
- Query: `SELECT ProjectName FROM Projects WHERE projectid = ?`

---

## Root Cause Analysis — Record Completeness Bug

**Symptom:** 50 records returned instead of 154 for a given project/trade.

**Root cause candidates** (to be confirmed during implementation):

1. **API page size discovery logic**: The client fetches page 1, sees 50 records, and may derive `items_per_page = len(page1_records)`. If the API returns exactly 50 on page 1 and the actual page size is 50, the client calculates `total_pages = ceil(154/50) = 4`. But if the total count is NOT in the API response header/body, the client stops after page 1 (assuming 50 = all records).

2. **Missing total count in API response**: If `/summaryByTrade` returns only the list without a `total` or `count` field, the pagination `while` loop may terminate early when it sees `len(page) < page_size` is False on page 1 (50 == 50 == full page) — but there's no way to know pages 2, 3, 4 exist.

3. **Dedup over-aggressiveness**: If `_id` dedup accidentally matches across pages (e.g., records with identical `_id`s across different pages), records are silently dropped.

**Fix strategy:**
- Continue fetching pages until a page returns **0 records** (empty page = definitive end), not `len(page) < page_size`
- Add post-fetch **record count verification**: log warning if fetched < first-page-implied-total
- Add a `completion_verified` flag in the API response metadata
- Log per-page record counts to detect gaps

---

## Architecture: What Changes & Why

### New Service: `services/sql_service.py`

**Purpose:** Single-responsibility SQL lookup for project names.

**Design decisions:**
- Uses `pyodbc` (sync) wrapped in `asyncio.to_thread()` — same pattern as `document_generator.py`
- **No heavyweight connection pool** — project name lookups are rare (cache TTL = 3600s, so SQL hit = once per project per hour)
- **Lazy reconnect**: create connection on first use, test liveness before each query, reconnect if dead
- **1-hour cache** via `CacheService` with key `project_name:{project_id}` — eliminates repeat SQL hits
- **Fallback tuple**: returns `(project_name: str | None, error_reason: str | None)` — caller always gets a usable display string

**Connection string:** MS SQL Server via pyodbc ODBC Driver 17.

**Display string logic:**
```
If SQL succeeds and name found:   "Granville Hotel (ID: 7298)"
If SQL succeeds but no row found: "Unknown Project (ID: 7298)" + reason logged
If SQL fails (any error):         "Project ID: 7298 (name lookup failed: {specific reason})"
```

---

### Modified: `agents/generation_agent.py`

**Change:** Add `SQLService.get_project_name(project_id)` to Phase 1 parallel block.

```
Phase 1 (parallel, ~50ms + SQL ~5-50ms):
  ├── SessionService.get_or_create()
  ├── CacheService.get(pre_cache_key)
  ├── DataAgent.get_project_metadata()       ← empty stub (unchanged)
  └── SQLService.get_project_name()          ← NEW: SQL lookup (cached 1 hour)
```

**Pass-through:** `project_display_name` propagated to:
- System prompt context block header
- Document generator call
- `ChatResponse.project_name`

---

### Modified: `models/schemas.py`

Add `project_name: str` to `ChatResponse`. This is the display string (`"Granville Hotel (ID: 7298)"` or fallback).

---

### Modified: `services/document_generator.py` and `exhibit_document_generator.py`

- `generate_sync(... project_name: str)` receives the display name
- Document title block: `Project: Granville Hotel (ID: 7298)` instead of `Project ID: 7298`
- Document footer: same
- **Filename**: `scope_electrical_GranvilleHotel_7298_a1b2c3d4.docx`
  - Sanitize: strip spaces/special chars → underscores, max 30 chars for project name segment

---

### Modified: `services/api_client.py`

**Record completeness fix:**

```
OLD termination condition:
  stop when len(page_records) < page_size  ← WRONG: if API always returns exactly 50, never stops

NEW termination condition:
  stop when len(page_records) == 0  ← CORRECT: empty page = definitive end
```

**Additional hardening:**
- Log each page's record count: `page {n}: {count} records (running total: {total})`
- After all pages: log `FETCH COMPLETE: {total} records across {pages} pages`
- If any page fetch fails after 3 retries: log `PAGE SKIP WARNING: page {n} failed after 3 retries — {total} records may be incomplete`
- Add `fetch_stats: {pages_fetched, records_total, pages_failed}` returned alongside records

---

### Modified: `config.py`

New settings block:
```python
# SQL Server (project name lookup)
sql_server_host: str = ""
sql_server_port: int = 1433
sql_database: str = ""
sql_username: str = ""
sql_password: str = ""
sql_driver: str = "ODBC Driver 17 for SQL Server"
sql_connection_timeout: int = 10
cache_ttl_project_name: int = 3600  # 1 hour
```

Pagination tuning:
```python
parallel_fetch_concurrency: int = 30  # raised from 15 → 30 for latency target
```

---

### Modified: `.env`

New variables added:
```
# SQL Server — Project Name Lookup
SQL_SERVER_HOST=ifieldsmartencrypted.ctzuheyxit1m.us-east-1.rds.amazonaws.com
SQL_SERVER_PORT=1433
SQL_DATABASE=iFMasterDatabase_1
SQL_USERNAME=aniruddhak
SQL_PASSWORD=y2tGPBy7u%2$5C
SQL_DRIVER=ODBC Driver 17 for SQL Server
SQL_CONNECTION_TIMEOUT=10
CACHE_TTL_PROJECT_NAME=3600

# Raised from 15 → 30 for latency
PARALLEL_FETCH_CONCURRENCY=30
```

---

### Modified: `main.py`

- Import and initialize `SQLService` in lifespan startup
- Attach to `app.state.sql_service`
- Pass to `GenerationAgent.__init__`
- Graceful startup: SQL connection failure = warn + continue (not fatal)

---

## Latency Budget (Target: ≤ 3 min for normal, ≤ 10 min for large)

| Dataset Size | Pages | Old Fetch (concurrency=15) | New Fetch (concurrency=30) | LLM (10k tokens) | Total |
|-------------|-------|---------------------------|---------------------------|------------------|-------|
| 154 records | 4 | ~8s | ~5s | ~2.4 min | **~2.5 min** ✅ |
| 1,000 records | 20 | ~40s | ~25s | ~2.4 min | **~3 min** ✅ |
| 11,360 records | 228 | ~88s | ~50s | ~2.4 min | **~3.3 min** ⚠️ |
| 20,000+ records | 400+ | ~155s | ~85s | ~2.4 min | **~5 min** ✅ (within 5-10 min) |

**Note on LLM time:** Context compression caps at `MAX_CONTEXT_TOKENS=120000`. Even with 11k records, LLM input is compressed to fit. LLM output is capped at 10k tokens ≈ 2.4 min. This is the floor — cannot reduce without shrinking output quality.

**Streaming note:** With `/api/chat/stream`, user sees **first token in ~50s** (after data fetch completes) even for large datasets. Full doc generation adds ~500ms after LLM finishes.

---

## Implementation Sequence

### Phase A — SQL Service (Independent)
1. Create `services/sql_service.py`
2. Update `config.py` with SQL settings
3. Update `.env` with SQL credentials
4. Update `main.py` to initialize `SQLService`
5. Install dependency: `pyodbc` (add to `requirements.txt`)

### Phase B — Record Completeness Fix (Independent)
1. Fix pagination termination in `services/api_client.py`
2. Add per-page logging and `fetch_stats`
3. Test with known project (verify 154 records now returned, not 50)

### Phase C — Project Name Propagation (Depends on Phase A)
1. Update `models/schemas.py` — add `project_name` to `ChatResponse`
2. Update `agents/generation_agent.py` — Phase 1 SQL fetch + propagation
3. Update `services/document_generator.py` — display name in header/footer/filename
4. Update `services/exhibit_document_generator.py` — same

### Phase D — Concurrency Tuning (Independent)
1. Update `config.py` and `.env`: `PARALLEL_FETCH_CONCURRENCY=30`
2. Verify no API rate-limit errors at 30 concurrent connections

---

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `services/sql_service.py` | **CREATE** | Project name SQL lookup |
| `config.py` | **MODIFY** | SQL settings + concurrency tuning |
| `.env` | **MODIFY** | SQL credentials + PARALLEL_FETCH_CONCURRENCY=30 |
| `main.py` | **MODIFY** | SQLService init in lifespan |
| `models/schemas.py` | **MODIFY** | Add `project_name` to `ChatResponse` |
| `agents/generation_agent.py` | **MODIFY** | Phase 1 SQL fetch + propagation |
| `services/api_client.py` | **MODIFY** | Pagination termination fix + logging |
| `services/document_generator.py` | **MODIFY** | Display name in doc + filename |
| `services/exhibit_document_generator.py` | **MODIFY** | Display name in doc + filename |
| `requirements.txt` | **MODIFY** | Add `pyodbc` |
| `CLAUDE.md` | **MODIFY** | Updated to reflect v3 changes |

---

## Testing Plan

1. **SQL lookup**: Call with known `project_id=7298`, verify `"Granville Hotel (ID: 7298)"` returned.
2. **SQL fallback**: Temporarily set wrong password, verify response contains fallback string with reason.
3. **Record completeness**: Call with project that was returning 50 records — verify now returns 154.
4. **Filename**: Download document, verify name includes project name slug.
5. **ChatResponse**: Verify `project_name` field in JSON response.
6. **End-to-end latency**: Time full pipeline for 154-record and 11k-record trades.

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| `pyodbc` not installed on VM | Add to `requirements.txt`; startup warning if missing |
| ODBC Driver 17 not on VM | Document install step in `SETUP.md` |
| SQL connection slow (~200ms) | Cached 1 hour — negligible after first request |
| API rate limits at concurrency=30 | Semaphore can be reduced via env var; 15 is safe fallback |
| Record count still wrong after fix | Add explicit reconciliation log — pages fetched vs expected total |