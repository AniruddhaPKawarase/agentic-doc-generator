# Streamlit UI — API Flow Reference (Postman)

**Base URL (Sandbox):** `http://54.197.189.113:8003`
**Base URL (Production):** `https://ai5.ifieldsmart.com/construction`
**Headers for all POST requests:** `Content-Type: application/json`

APIs listed in the exact order they are hit as you walk through the Streamlit UI.
All responses verified against live sandbox on 2026-04-09.

---

## STEP 0: Health Check (Pre-flight)

Called before any generate action to verify the server is alive.

### `GET /health`

```
No body, no params
```

**What it does:** Returns Redis status, OpenAI config status, and API version. The Streamlit UI calls this before running the pipeline to ensure the server is reachable.

**Postman example:**
```
GET http://54.197.189.113:8003/health
```

**Verified response:**
```json
{
  "status": "ok",
  "redis": "in-memory-only",
  "openai": "configured",
  "new_api": "ok",
  "version": "2.1.0"
}
```

**`new_api` values:**
- `"ok"` — byTrade endpoint is reachable
- `"degraded (using fallback)"` — falling back to summaryByTrade
- `"disabled"` — `USE_NEW_API=false` in .env

---

## STEP 0b: Unique Trades (Upstream MongoDB)

Direct MongoDB API for discovering all trade names in a project. Used internally by the trade discovery service and chat pipeline. Fast single call — no pagination needed.

### `GET https://mongo.ifieldsmart.com/api/drawingText/uniqueTrades`

```
Query: projectId = 7276
```

**What it does:** Returns all unique trade name strings from the MongoDB `drawingText` collection for a project. This is the fastest way to discover what trades exist — one call, no probing.

**Postman example:**
```
GET https://mongo.ifieldsmart.com/api/drawingText/uniqueTrades?projectId=7276
```

**Verified response (7276):**
```json
{
  "success": true,
  "message": "Unique trades fetched for projectId 7276",
  "data": {
    "list": [
      "Appliance Installation",
      "Building Envelope",
      "Carpentry",
      "Casework",
      "Concrete",
      "Concrete Reinforcing",
      "Demolition",
      "Door & Hardware",
      "Door Hardware",
      "Doors",
      "Drywall",
      "Electrical",
      "Excavation",
      "Exterior Cladding",
      "Exterior Siding",
      "Fencing",
      "Finish Carpentry",
      "Flooring",
      "Glazing",
      "HVAC",
      "Hardware",
      "Insulation",
      "Landscaping",
      "Masonry",
      "Metal Fabrication",
      "Metalwork",
      "Millwork",
      "Painting",
      "Plumbing",
      "Rebar",
      "Roofing",
      "Siding",
      "Sitework",
      "Specialty Trade",
      "Stonework",
      "Structural",
      "Structural Steel",
      "Tile",
      "Tile Setting",
      "Waterproofing",
      "Weather Barrier Installation",
      "Welding"
    ],
    "count": 43
  }
}
```

**Verified counts across projects:**
| Project | Unique Trades |
|---------|--------------|
| 7276 | 42 trades |
| 7298 | 93 trades |
| 7212 | 127 trades |

> **Note:** The list may contain `null` entries — filter them out client-side. The count includes nulls.

---

## STEP 1: Load Drawings Sidebar (Workspace Page)

First API called when the workspace page loads. Populates the sidebar drawing tree under the "Drawings" tab.

### `GET /api/scope-gap/projects/{project_id}/drawings`

```
Path: project_id = 7298
Optional query: set_id = 4730
```

**What it does:** Fetches drawing records from the iFieldSmart API, categorizes them by discipline (Electrical, Mechanical, Architectural, etc.), and returns a tree structure. Internally uses a two-step strategy:
1. Try `summaryByTrade` with empty trade (returns all records on some APIs)
2. Always supplement with page-1-per-trade via `uniqueTrades` discovery to ensure complete drawing coverage

Falls back to `pdfName` field when `drawingName` is not available (varies by project).

**Postman example:**
```
GET http://54.197.189.113:8003/api/scope-gap/projects/7298/drawings
```

**Verified response (7298):**
```json
{
  "project_id": 7298,
  "total_drawings": 95,
  "total_specs": 0,
  "categories": {
    "ARCHITECTURAL": {
      "drawings": [
        {"drawing_name": "A10010", "drawing_title": "", "source_type": "drawing"},
        {"drawing_name": "A10148", "drawing_title": "", "source_type": "drawing"},
        {"drawing_name": "A101CH", "drawing_title": "", "source_type": "drawing"}
      ],
      "specs": []
    },
    "CIVIL": {
      "drawings": [
        {"drawing_name": "CD-505", "drawing_title": "", "source_type": "drawing"},
        {"drawing_name": "CE-101", "drawing_title": "", "source_type": "drawing"}
      ],
      "specs": []
    },
    "PLUMBING": {
      "drawings": [
        {"drawing_name": "PR-101", "drawing_title": "", "source_type": "drawing"},
        {"drawing_name": "PR-102", "drawing_title": "", "source_type": "drawing"}
      ],
      "specs": []
    }
  }
}
```

**Verified counts across projects:**
| Project | Drawings | Disciplines | Notes |
|---------|----------|-------------|-------|
| 7276 | 25 | 1 (ARCHITECTURAL) | All drawings are A-* prefixed |
| 7298 | 95 | 3 (ARCHITECTURAL, CIVIL, PLUMBING) | Full coverage verified against upstream |
| 7212 | 3,125 | 50 disciplines | Uses `pdfName` fallback — drawing names are raw PDF filenames |

---

## STEP 2: Load Trades List (Workspace > Export View)

Called when the Export view loads to show available trades in a table.

### `GET /api/scope-gap/projects/{project_id}/trades`

```
Path: project_id = 7298
Optional query: set_id = 4730
```

**What it does:** Discovers all available trades for the project using a three-strategy approach:
1. **`uniqueTrades` API** (fast, single call) — returns all trade names from MongoDB
2. **`summaryByTrade` with empty trade** — returns records across all trades on some API deployments
3. **Probe known trades** (slowest fallback) — checks 45 common construction trades

Returns each trade with its record count, pipeline status, and assigned color.

**Postman example:**
```
GET http://54.197.189.113:8003/api/scope-gap/projects/7276/trades
```

**Verified response (7276):**
```json
{
  "project_id": 7276,
  "trades": [
    {"trade": "Carpentry", "record_count": 383, "status": "pending", "color": {"hex": "#9067E4", "rgb": [144, 103, 228]}},
    {"trade": "Concrete", "record_count": 131, "status": "pending", "color": {"hex": "#BCAAA4", "rgb": [188, 170, 164]}},
    {"trade": "Doors", "record_count": 3, "status": "pending", "color": {"hex": "#67E46F", "rgb": [103, 228, 111]}},
    {"trade": "Drywall", "record_count": 72, "status": "pending", "color": {"hex": "#E48C67", "rgb": [228, 140, 103]}},
    {"trade": "Electrical", "record_count": 107, "status": "pending", "color": {"hex": "#F48FB1", "rgb": [244, 143, 177]}},
    {"trade": "Glazing", "record_count": 19, "status": "pending", "color": {"hex": "#E46797", "rgb": [228, 103, 151]}},
    {"trade": "HVAC", "record_count": 30, "status": "pending", "color": {"hex": "#90A4AE", "rgb": [144, 164, 174]}},
    {"trade": "Insulation", "record_count": 28, "status": "pending", "color": {"hex": "#E467D8", "rgb": [228, 103, 216]}},
    {"trade": "Masonry", "record_count": 31, "status": "pending", "color": {"hex": "#A7E467", "rgb": [167, 228, 103]}},
    {"trade": "Painting", "record_count": 77, "status": "pending", "color": {"hex": "#F8BBD0", "rgb": [248, 187, 208]}},
    {"trade": "Plumbing", "record_count": 154, "status": "pending", "color": {"hex": "#81D4FA", "rgb": [129, 212, 250]}},
    {"trade": "Roofing", "record_count": 65, "status": "pending", "color": {"hex": "#A5D6A7", "rgb": [165, 214, 167]}},
    {"trade": "Sitework", "record_count": 1, "status": "pending", "color": {"hex": "#E4D767", "rgb": [228, 215, 103]}},
    {"trade": "Structural", "record_count": 3, "status": "pending", "color": {"hex": "#E48D67", "rgb": [228, 141, 103]}},
    {"trade": "Waterproofing", "record_count": 13, "status": "pending", "color": {"hex": "#E46781", "rgb": [228, 103, 129]}}
  ],
  "total_trades": 15,
  "total_records": 1117
}
```

**Verified counts across projects:**
| Project | Trades | Total Records |
|---------|--------|---------------|
| 7276 | 15 | 1,117 |
| 7298 | 20 | 3,889 |
| 7212 | 20 | 38,994 |

**Status values:**
| Status | Meaning |
|--------|---------|
| `ready` | Trade has a completed pipeline result |
| `pending` | Pipeline has not been run yet |
| `failed` | Last pipeline run errored |

---

## STEP 3: Generate Scope Gap for a Single Trade (Export View > "Generate" button)

The main pipeline call. Fired when the user clicks "Generate" on a trade row. The UI first calls `/health` (Step 0) to confirm the server is alive, then starts this stream.

### `POST /api/scope-gap/stream` (preferred — SSE streaming with progress bar)

```json
{
  "project_id": 7276,
  "trade": "Electrical"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | int | Yes | MongoDB project ID (e.g., 7298, 7276) |
| `trade` | string | Yes | Trade name exactly as returned by Step 2 |
| `set_ids` | list[int] | No | Filter to specific drawing sets |
| `session_id` | string | No | Continue an existing session |

**What it does:** Runs the full 7-agent pipeline:
1. **Data Fetch** — pull drawing records from iFieldSmart API
2. **Extraction** — extract scope items from drawings via LLM
3. **Classification** — classify items by trade and CSI code
4. **Ambiguity Detection** — find items that belong to multiple trades
5. **Gotcha Detection** — identify hidden risks and missing scope
6. **Completeness Check** — verify coverage percentage (may trigger backpropagation retry)
7. **Quality Review** — final quality scoring
8. **Document Generation** — create Word/PDF/CSV/JSON exports

Streams real-time progress via SSE events so the UI can show a progress bar.

**Postman example:**
```
POST http://54.197.189.113:8003/api/scope-gap/stream
Content-Type: application/json

{
  "project_id": 7276,
  "trade": "Electrical"
}
```

> **Note:** SSE streaming is hard to test in Postman. Use `/api/scope-gap/generate` (Step 3b) for Postman testing instead.

**SSE Events (in order):**
```
event: data_fetch
data: {"records_count": 107, "drawings_count": 15}

event: agent_start
data: {"agent": "extraction"}

event: agent_complete
data: {"agent": "extraction", "elapsed_ms": 2500}

event: agent_start
data: {"agent": "classification"}

event: agent_complete
data: {"agent": "classification", "elapsed_ms": 1200}

event: agent_start
data: {"agent": "ambiguity"}

event: agent_complete
data: {"agent": "ambiguity", "elapsed_ms": 800}

event: agent_start
data: {"agent": "gotcha"}

event: agent_complete
data: {"agent": "gotcha", "elapsed_ms": 900}

event: completeness
data: {"overall_pct": 92.5, "is_complete": true}

event: agent_start
data: {"agent": "quality"}

event: agent_complete
data: {"agent": "quality", "elapsed_ms": 600}

event: pipeline_complete
data: {"items_count": 45, "completeness_pct": 92.5, "attempts": 1}

event: result
data: { <full ScopeGapResult JSON> }
```

**If completeness is below threshold, you'll also see:**
```
event: backpropagation
data: {"attempt": 1, "missing_drawings": ["E0.03", "E1.01"]}
```
(pipeline retries with missing drawings before continuing)

**Pipeline stage weights for progress bar:**
| Stage | Weight |
|-------|--------|
| data_fetch | 10% |
| extraction | 25% |
| classification | 15% |
| ambiguity | 10% |
| gotcha | 10% |
| completeness | 5% |
| quality | 10% |
| documents | 10% |
| finalize | 5% |

---

### STEP 3b: Generate Scope Gap — Synchronous (for Postman)

Used as a fallback if streaming fails, and easier to test in Postman.

### `POST /api/scope-gap/generate`

```json
{
  "project_id": 7276,
  "trade": "Doors"
}
```

Same request body as Step 3. Returns the full result in one JSON response instead of streaming.

**Postman example:**
```
POST http://54.197.189.113:8003/api/scope-gap/generate
Content-Type: application/json

{
  "project_id": 7276,
  "trade": "Doors"
}
```

**Verified response (7276 Doors — 3 records, smallest trade for fast testing):**
```json
{
  "project_id": 7276,
  "project_name": "SINGH RESIDENCE",
  "trade": "Doors",
  "items": [
    {
      "id": "itm_b0a4fa53",
      "text": "Contractor shall furnish and install interior solid core paint grade wood recessed panel doors as manufactured by Masonite or equal...",
      "drawing_name": "A-24",
      "confidence": 0.5,
      "csi_division": "08 - Openings",
      "trade": "Doors",
      "csi_code": "08 14 16",
      "classification_confidence": 1.0
    }
  ],
  "ambiguities": [],
  "gotchas": [
    {
      "id": "gtc_1574c9c8",
      "risk_type": "hidden_cost",
      "description": "Scope items reference 'allowance for doors and installation'... but do not specify allowance values...",
      "severity": "high",
      "affected_trades": ["Doors", "Finish Carpentry"],
      "recommendation": "Clarify allowance values...",
      "drawing_refs": ["A-24"]
    }
  ],
  "completeness": {
    "drawing_coverage_pct": 66.7,
    "csi_coverage_pct": 0.0,
    "overall_pct": 63.3,
    "is_complete": false,
    "attempt": 5
  },
  "quality": {
    "accuracy_score": 0.95
  },
  "documents": {
    "word_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.docx",
    "pdf_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.pdf",
    "csv_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.csv",
    "json_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.json"
  },
  "pipeline_stats": {
    "total_ms": 91662,
    "attempts": 5,
    "tokens_used": 12808,
    "estimated_cost_usd": 0.025616,
    "records_processed": 3,
    "items_extracted": 7
  }
}
```

> **Note on exported documents:** The Word/PDF exports contain ONLY clean scope text grouped by drawing — no ambiguities, gotchas, completeness report, CSI/confidence/source metadata, or pipeline footer. The JSON export remains a full data dump with all fields. See [AGENT_PROMPTS.md](AGENT_PROMPTS.md) for pipeline details.
```

---

## STEP 4: View Report (Workspace > Report View)

No separate API call — the Report view uses the cached result from Step 3 stored in `st.session_state.scope_results[trade]`. Renders score cards, scope items, ambiguities, gotchas, and document download buttons.

**If the trade result is NOT cached** (user navigates directly to Report view), the UI calls `POST /api/scope-gap/generate` (Step 3b) synchronously as a fallback.

---

## STEP 5: Download Export Documents (Report View > Export buttons)

Called when the user clicks Word / PDF / CSV / JSON download buttons in the Report view.

### `GET /api/documents/{file_id}/download`

```
Path: file_id = "7276_Singh_Residence_Doors_Scope_of_Work"
No body
```

**What it does:** The `file_id` is extracted from the document paths in the pipeline result (`documents.word_path`, `documents.pdf_path`, etc.). The filename without extension becomes the `file_id`. The backend looks up the file in S3 bucket `agentic-ai-production`, generates a presigned URL, and redirects (307).

**Postman example:**
```
GET http://54.197.189.113:8003/api/documents/7276_Singh_Residence_Doors_Scope_of_Work/download
```

**Verified:** Returns HTTP 307 redirect to S3 presigned URL.

**How to find the file_id:** Run Step 3b first, then look at the `documents` object in the response:
```json
{
  "documents": {
    "word_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.docx",
    "pdf_path": "./generated_docs/7276_Singh_Residence_Doors_Scope_of_Work.pdf"
  }
}
```
The file_id is: `7276_Singh_Residence_Doors_Scope_of_Work`

**Filename format:** `{project_id}_{Project_Name}_{Trade}_Scope_of_Work.{ext}` — project name comes from SQL database lookup.

### `GET /api/documents/{file_id}/info`

```
Path: file_id = "feb1d9df-4986-422d-88bd-bb7808f926a9"
No body
```

**What it does:** Returns metadata about a stored document without downloading it.

**Verified response:**
```json
{
  "file_id": "feb1d9df-4986-422d-88bd-bb7808f926a9",
  "filename": "extract_unknown_project_7276_7276_feb1d9df.docx",
  "size_bytes": 37764,
  "size_kb": 36.9,
  "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/feb1d9df/download",
  "storage": "s3",
  "s3_key": "construction-intelligence-agent/generated_documents/..."
}
```

---

## STEP 6: Run All Trades at Once (Export View > "Run All Trades" button)

### `POST /api/scope-gap/projects/{project_id}/run-all`

```json
{
  "force_rerun": false,
  "set_ids": null,
  "trades": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `force_rerun` | bool | No | false | If true, ignores cached results and re-runs everything |
| `set_ids` | list[int] | No | null | Filter to specific drawing sets |
| `trades` | list[string] | No | null | Run only specific trades (null = all trades) |

**What it does:** Triggers background orchestration for all trades in parallel. Returns 202 immediately. The orchestrator runs the 7-agent pipeline for each trade. Use Step 7 to poll for progress.

**Postman example:**
```
POST http://54.197.189.113:8003/api/scope-gap/projects/7298/run-all
Content-Type: application/json

{
  "force_rerun": false,
  "set_ids": null,
  "trades": null
}
```

**Verified response (202 Accepted):**
```json
{
  "accepted": true,
  "project_id": 7298,
  "force_rerun": false,
  "set_ids": null,
  "trades": null,
  "message": "Pipeline triggered for all trades. Poll /status for progress."
}
```

**To run only specific trades:**
```json
{
  "force_rerun": false,
  "trades": ["Electrical", "Plumbing"]
}
```

---

## STEP 7: Check Pipeline Status (After Run All)

### `GET /api/scope-gap/projects/{project_id}/status`

```
Path: project_id = 7298
No body
```

**What it does:** Returns a dashboard of all trade pipeline runs — how many are complete, failed, or pending. Used to monitor progress after "Run All Trades" (Step 6).

**Postman example:**
```
GET http://54.197.189.113:8003/api/scope-gap/projects/7276/status
```

**Verified response (no runs yet):**
```json
{
  "project_id": 7276,
  "session_id": null,
  "overall_progress": 0,
  "total_items": 0,
  "trades": []
}
```

### `GET /api/scope-gap/status` — System Health

```
No body, no params
```

**Verified response:**
```json
{
  "status": "ok",
  "uptime_seconds": 155996,
  "redis_connected": false,
  "s3_connected": true
}
```

### `GET /api/scope-gap/metrics` — Pipeline Metrics

```
No body, no params
```

**Verified response:**
```json
{
  "status": "ok",
  "uptime_seconds": 156002,
  "active_jobs": 0,
  "token_usage": {}
}
```

---

## STEP 8: Chat with AI Agent (Chat Page)

Called when the user types a message or clicks a quick prompt on the Chat page.

### `POST /api/chat`

```json
{
  "project_id": 7276,
  "query": "What are the electrical scope gaps?",
  "session_id": null,
  "generate_document": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `project_id` | int | Yes | — | MongoDB project ID |
| `query` | string | Yes | — | User's natural-language question (min 3 chars) |
| `session_id` | string | No | null | Pass the session_id from a previous response to continue the conversation |
| `user_id` | string | No | null | Optional user identifier |
| `generate_document` | bool | No | true | Whether to generate a downloadable .docx file |
| `set_ids` | list[int] | No | null | Filter to specific drawing sets |

**What it does:** The full chat pipeline: Intent Detection -> Data Fetching -> LLM Generation -> Document Generation. Uses `uniqueTrades` API to detect trade from the query, fetches relevant drawings from MongoDB, generates a scope answer via OpenAI, and optionally creates a downloadable Word document.

**Postman example (first message):**
```
POST http://54.197.189.113:8003/api/chat
Content-Type: application/json

{
  "project_id": 7276,
  "query": "What are the electrical scope gaps?",
  "session_id": null,
  "generate_document": true
}
```

**Verified response (abbreviated):**
```json
{
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "answer": "**Electrical Scope of Work Exhibit**\n\n**1. Smoke and Carbon Monoxide Detection Systems**\nDrawing Number(s): A-12, A-13, A-14...",
  "intent": {
    "trade": "Electrical",
    "document_type": "extract",
    "intent": "extract",
    "confidence": 0.9
  },
  "document": {
    "file_id": "feb1d9df-4986-422d-88bd-bb7808f926a9",
    "filename": "extract_electrical_project_7276.docx",
    "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/feb1d9df/download",
    "size_bytes": 37764
  },
  "token_usage": {
    "input_tokens": 1338,
    "output_tokens": 67,
    "total_tokens": 1405,
    "cost_usd": 0.000361
  },
  "groundedness_score": 0.4,
  "needs_clarification": false,
  "pipeline_ms": 38590,
  "cached": false,
  "source_references": {
    "A-12": {"drawing_id": 12345, "s3_url": "https://...", "pdf_name": "...", "x": 100, "y": 200, "width": 50, "height": 30},
    "A-13": {"drawing_id": 12346, "s3_url": "https://...", "pdf_name": "...", "x": null, "y": null, "width": null, "height": null}
  },
  "api_version": "byTrade",
  "warnings": []
}
```

**Postman example (follow-up message — pass session_id):**
```
POST http://54.197.189.113:8003/api/chat
Content-Type: application/json

{
  "project_id": 7276,
  "query": "Can you also check plumbing?",
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "generate_document": true
}
```

**Quick prompt examples (built into the UI):**
- `"What are the main electrical scope gaps?"`
- `"Summarize plumbing requirements"`
- `"List HVAC ambiguities"`
- `"Generate scope document"`

---

## STEP 9: Raw API Data (Chat Page — Expander)

Called by the "Raw API Data" expander below each chat response to display all records.

### `GET /api/projects/{project_id}/raw-data`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `trade` | string | Yes | — | Trade name (e.g., "Civil", "Electrical") |
| `set_id` | int | No | null | Optional set ID filter |
| `skip` | int | No | 0 | Pagination offset |
| `limit` | int | No | 500 | Records per page |

**Postman example:**
```
GET http://54.197.189.113:8003/api/projects/7292/raw-data?trade=Civil&set_id=4720&skip=0&limit=50
```

**Response:**
```json
{
  "success": true,
  "data": {
    "records": [
      {
        "_id": "69a700bd12179a5f1c8263d5",
        "projectId": 7292,
        "drawingId": 318845,
        "drawingName": "A102",
        "drawingTitle": "ARCHITECTURAL SITE PLAN",
        "s3BucketPath": "ifieldsmart/proj/Drawings/pdf",
        "pdfName": "pdfA102Plan",
        "text": "MATCH EXISTING SIDEWALK",
        "x": 3743, "y": 738, "width": 144, "height": 69,
        "csi_division": ["03 - Concrete"],
        "trades": ["Civil"]
      }
    ],
    "total": 342,
    "skip": 0,
    "limit": 50,
    "has_more": true
  }
}
```

**UI integration:** The Streamlit chat component calls this after each response. Results are displayed in a collapsible `st.expander("Raw API Data")` with column toggles, search/sort (via `st.dataframe`), and CSV export.

---

## Highlights CRUD (Drawing View)

All highlight endpoints require `X-User-Id` header. Highlights are stored per-user in S3.

### `POST /api/scope-gap/highlights` — Create

**Headers:** `X-User-Id: testuser`

```json
{
  "project_id": 7276,
  "drawing_name": "E0.03",
  "x": 100,
  "y": 200,
  "width": 300,
  "height": 40,
  "label": "Test Highlight",
  "color": "#FFEB3B",
  "opacity": 0.3,
  "critical": false
}
```

**Verified response (201):**
```json
{
  "id": "hl_c9c2f7e9f3",
  "drawing_name": "E0.03",
  "page": 1,
  "x": 100.0,
  "y": 200.0,
  "width": 300.0,
  "height": 40.0,
  "color": "#FFEB3B",
  "opacity": 0.3,
  "label": "Test Highlight",
  "trade": null,
  "critical": false,
  "comment": "",
  "scope_item_id": null,
  "scope_item_ids": [],
  "created_at": "2026-04-09T07:26:51.739517Z",
  "updated_at": "2026-04-09T07:26:51.739523Z"
}
```

### `GET /api/scope-gap/highlights` — List

**Headers:** `X-User-Id: testuser`

```
Query: project_id=7276&drawing_name=E0.03
```

**Verified:** Returns array of highlight objects.

### `PATCH /api/scope-gap/highlights/{id}` — Update

**Headers:** `X-User-Id: testuser`

```
Query: project_id=7276&drawing_name=E0.03
```
```json
{
  "label": "Updated Label",
  "critical": true
}
```

**Verified:** Returns updated highlight with new field values.

### `DELETE /api/scope-gap/highlights/{id}` — Delete

**Headers:** `X-User-Id: testuser`

```
Query: project_id=7276&drawing_name=E0.03
```

**Verified response:**
```json
{"deleted": true}
```

---

## Quick Test Sequence for Postman

Copy these in order. Each step builds on the previous.

| # | Method | URL | Body |
|---|--------|-----|------|
| 0 | GET | `http://54.197.189.113:8003/health` | — |
| 0b | GET | `https://mongo.ifieldsmart.com/api/drawingText/uniqueTrades?projectId=7276` | — |
| 1 | GET | `http://54.197.189.113:8003/api/scope-gap/projects/7276/drawings` | — |
| 2 | GET | `http://54.197.189.113:8003/api/scope-gap/projects/7276/trades` | — |
| 3 | POST | `http://54.197.189.113:8003/api/scope-gap/generate` | `{"project_id": 7276, "trade": "Doors"}` |
| 4 | — | — | Report view (uses Step 3 result) |
| 5 | GET | `http://54.197.189.113:8003/api/documents/{file_id}/download` | — (get file_id from Step 3 `documents.word_path`) |
| 6 | POST | `http://54.197.189.113:8003/api/scope-gap/projects/7276/run-all` | `{"force_rerun": false}` |
| 7 | GET | `http://54.197.189.113:8003/api/scope-gap/projects/7276/status` | — |
| 8 | POST | `http://54.197.189.113:8003/api/chat` | `{"project_id": 7276, "query": "What are the electrical scope gaps?"}` |
| 9 | POST | `http://54.197.189.113:8003/api/scope-gap/highlights` | `{"project_id": 7276, "drawing_name": "E0.03", "x": 100, "y": 200, "width": 300, "height": 40, "label": "Test"}` + Header: `X-User-Id: testuser` |

---

## Available Project IDs for Testing

| ID | Name | Location | Trades | Records | Status |
|----|------|----------|--------|---------|--------|
| 7276 | 450-460 JR PKWY Phase II | Nashville, TN | 15 | 1,117 | Active |
| 7298 | AVE Horsham Multi-Family | Horsham, PA | 20 | 3,889 | Active |
| 7212 | HSB Potomac Senior Living | Potomac, MD | 20 | 38,994 | Active |
| 7222 | Metro Transit Hub | Chicago, IL | — | — | On-Hold |
| 7223 | Greenfield Data Center | Phoenix, AZ | — | — | Completed |

---

## Error Handling (Verified)

| Scenario | HTTP Code | Response |
|----------|-----------|----------|
| Invalid session ID | 404 | `{"detail": "Session nonexistent_session not found"}` |
| Invalid job ID | 404 | `{"detail": "Job nonexistent_job not found"}` |
| Invalid document ID | 404 | `{"detail": "Document not found or expired"}` |
| Missing required field | 422 | `{"detail": [{"msg": "Field required", ...}]}` |

---

## Source Code References

| What | File |
|------|------|
| Streamlit main app | `scope-gap-ui/app.py` |
| Workspace page (Steps 1-7) | `scope-gap-ui/pages/workspace.py` |
| Chat page (Step 8) | `scope-gap-ui/pages/chat.py` |
| API client (low-level HTTP) | `scope-gap-ui/api/client.py` |
| Scope gap API calls | `scope-gap-ui/api/scope_gap.py` |
| Chat send helper | `scope-gap-ui/components/chat.py` |
| Document download buttons | `scope-gap-ui/components/export_panel.py` |
| FastAPI chat routes | `routers/chat.py` |
| FastAPI scope gap routes | `scope_pipeline/routers/scope_gap.py` |
| FastAPI project endpoints | `scope_pipeline/routers/project_endpoints.py` |
| Drawing index service | `scope_pipeline/services/drawing_index_service.py` |
| Trade discovery service | `scope_pipeline/services/trade_discovery_service.py` |
| API client (upstream HTTP) | `services/api_client.py` |
| App config | `config.py` |
| UI config (projects, trades) | `scope-gap-ui/config.py` |
