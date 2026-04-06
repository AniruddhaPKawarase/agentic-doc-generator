# Scope Gap Pipeline — API Reference

**Base URL (Sandbox):** `http://54.197.189.113:8003`
**Base URL (via Nginx):** `http://54.197.189.113:8000/construction`
**Prefix:** `/api/scope-gap`

---

## Old API vs New API — Full Comparison

### Architecture Comparison

| Aspect | Old API (`/api/chat`) | New API (`/api/scope-gap`) |
|--------|----------------------|---------------------------|
| **Purpose** | General-purpose chat: ask questions, get scope docs | Dedicated scope gap extraction with multi-agent pipeline |
| **Agent count** | 3 (Intent → Data → Generation) | 7 (Extraction → Classification + Ambiguity + Gotcha → Completeness → Quality → Document) |
| **Execution model** | Single-pass LLM generation | Multi-pass with backpropagation (up to 3 attempts) |
| **Parallelism** | Sequential phases | Parallel fan-out (Classification + Ambiguity + Gotcha run simultaneously) |
| **Output format** | Free-form markdown text + single Word doc | Structured JSON items + 4 document formats (Word, PDF, CSV, JSON) |
| **Source traceability** | None (LLM output doesn't link to specific drawings) | Every item links to drawing_name, page, source_snippet |
| **Completeness check** | None (hallucination guard is informational only) | Drawing coverage %, CSI coverage %, hallucination detection, backpropagation |
| **Ambiguity detection** | Not available | Dedicated agent identifies trade overlaps |
| **Gotcha/risk scanning** | Not available | Dedicated agent finds hidden costs, coordination issues, missing scope |
| **Background jobs** | Not available (always blocking) | Hybrid: blocking for small datasets, background jobs for large |
| **Session persistence** | Redis + S3 (conversation history only) | 3-layer (L1 memory + L2 Redis + L3 S3) with run history, user decisions, chat |
| **User decisions** | None | Resolve ambiguities, acknowledge gotchas, ignore/restore items |
| **Follow-up chat** | Via the same `/api/chat` endpoint | Dedicated `/sessions/{id}/chat` with report context |

### Endpoint-by-Endpoint Comparison

#### Old API Endpoints (still active, unchanged)

| # | Method | Old Endpoint | Purpose | Request Body |
|---|--------|-------------|---------|-------------|
| 1 | POST | `/api/chat` | Run chat pipeline (blocking) | `{"project_id": 7276, "query": "Create scope for electrical", "session_id": null, "generate_document": true, "set_ids": null}` |
| 2 | POST | `/api/chat/stream` | SSE streaming chat | Same as /api/chat |
| 3 | GET | `/api/sessions/{id}/history` | Conversation history | - |
| 4 | GET | `/api/sessions/{id}/tokens` | Token usage | - |
| 5 | DELETE | `/api/sessions/{id}` | Clear session | - |
| 6 | GET | `/api/documents/{id}/download` | Download Word file | - |
| 7 | GET | `/api/documents/{id}/info` | Document metadata | - |
| 8 | GET | `/api/projects/{id}/context` | Trades + CSI for project | - |
| 9 | GET | `/health` | Health check | - |

**Total old endpoints: 9**

#### New API Endpoints (added, old endpoints untouched)

| # | Method | New Endpoint | Purpose | Request Body |
|---|--------|-------------|---------|-------------|
| 1 | POST | `/api/scope-gap/generate` | Run full pipeline (blocking) | `{"project_id": 7276, "trade": "Electrical"}` |
| 2 | POST | `/api/scope-gap/stream` | SSE streaming pipeline | Same as /generate |
| 3 | POST | `/api/scope-gap/submit` | Background job | Same as /generate |
| 4 | GET | `/api/scope-gap/jobs` | List jobs | Query: ?project_id=&status= |
| 5 | GET | `/api/scope-gap/jobs/{id}/status` | Job progress | - |
| 6 | GET | `/api/scope-gap/jobs/{id}/result` | Job result | - |
| 7 | POST | `/api/scope-gap/jobs/{id}/continue` | Continue partial | - |
| 8 | DELETE | `/api/scope-gap/jobs/{id}` | Cancel job | - |
| 9 | GET | `/api/scope-gap/sessions` | List sessions | Query: ?project_id=&trade= |
| 10 | GET | `/api/scope-gap/sessions/{id}` | Session detail | - |
| 11 | DELETE | `/api/scope-gap/sessions/{id}` | Delete session | - |
| 12 | POST | `/api/scope-gap/sessions/{id}/resolve-ambiguity` | Resolve overlap | `{"ambiguity_id": "amb_xxx", "assigned_trade": "Roofing"}` |
| 13 | POST | `/api/scope-gap/sessions/{id}/acknowledge-gotcha` | Acknowledge risk | `{"gotcha_id": "gtc_xxx"}` |
| 14 | POST | `/api/scope-gap/sessions/{id}/ignore-item` | Ignore item | `{"item_id": "itm_xxx"}` |
| 15 | POST | `/api/scope-gap/sessions/{id}/restore-item` | Restore item | `{"item_id": "itm_xxx"}` |
| 16 | POST | `/api/scope-gap/sessions/{id}/chat` | Follow-up Q&A | `{"message": "Why was fire stopping flagged?"}` |

**Total new endpoints: 16 | Combined total: 25**

### Request Body Comparison

#### Old: POST /api/chat
```json
{
    "project_id": 7276,
    "query": "Create a scope for plumbing",
    "session_id": null,
    "user_id": null,
    "generate_document": true,
    "set_ids": null
}
```
- Requires a **natural language query** — user must describe what they want
- Trade is inferred by the IntentAgent from the query text
- Single document type (Word only)
- No control over pipeline behavior

#### New: POST /api/scope-gap/generate
```json
{
    "project_id": 7276,
    "trade": "Electrical",
    "set_ids": null,
    "session_id": null
}
```
- **Explicit trade selection** — no ambiguity in intent
- No natural language query needed — pipeline knows what to do
- All 4 document formats generated automatically
- Pipeline behavior configurable via env vars

### Response Comparison

#### Old: ChatResponse
```json
{
    "session_id": "sess_abc",
    "project_name": "Singh Residence (ID: 7276)",
    "answer": "## Electrical Scope\n\nBased on the drawings...(free-form markdown)...",
    "document": {
        "filename": "scope_electrical_7276_a1b2.docx",
        "download_url": "/api/documents/a1b2/download",
        "size_bytes": 45000,
        "generated_at": "2026-04-05T14:00:00Z"
    },
    "intent": {
        "trade": "Electrical",
        "document_type": "scope",
        "confidence": 0.95
    },
    "token_usage": {
        "input_tokens": 85000,
        "output_tokens": 3500,
        "total_tokens": 88500,
        "estimated_cost_usd": 0.04
    },
    "groundedness_score": 0.82,
    "needs_clarification": false,
    "clarification_questions": [],
    "follow_up_questions": [
        "Would you like an exhibit version?",
        "Should I include HVAC scope too?"
    ],
    "pipeline_ms": 240000,
    "cached": false
}
```

**Key limitation:** The `answer` is free-form markdown. You cannot programmatically extract individual scope items, their sources, CSI codes, or confidence scores from it.

#### New: ScopeGapResult
```json
{
    "project_id": 7276,
    "project_name": "",
    "trade": "Electrical",
    "items": [
        {
            "id": "itm_a1b2c3d4",
            "text": "Install electric double oven per riser diagram",
            "drawing_name": "A-25",
            "drawing_title": null,
            "page": 1,
            "source_snippet": "electric double oven per riser",
            "confidence": 0.95,
            "trade": "Electrical",
            "csi_code": "26 27 26",
            "csi_division": "26 - Electrical",
            "classification_confidence": 0.92,
            "classification_reason": "Electrical appliance connection"
        }
    ],
    "ambiguities": [
        {
            "id": "amb_e5f6",
            "scope_text": "Flashing at roof penetrations",
            "competing_trades": ["Roofing", "Sheet Metal"],
            "severity": "high",
            "recommendation": "Assign to Roofing per CSI 07 62 00"
        }
    ],
    "gotchas": [
        {
            "id": "gtc_i9j0",
            "risk_type": "hidden_cost",
            "description": "Temporary power not explicitly scoped",
            "severity": "high",
            "affected_trades": ["Electrical", "General Trades"],
            "recommendation": "Add to Electrical scope"
        }
    ],
    "completeness": {
        "drawing_coverage_pct": 68.8,
        "csi_coverage_pct": 61.5,
        "overall_pct": 72.8,
        "missing_drawings": ["A-15", "A-16", "A-17", "A-18", "A-24"],
        "is_complete": false,
        "attempt": 3
    },
    "quality": {
        "accuracy_score": 0.98,
        "corrections": [],
        "summary": "98% accuracy"
    },
    "documents": {
        "word_path": "./generated_docs/7276_Electrical_20260405.docx",
        "pdf_path": "./generated_docs/7276_Electrical_20260405.pdf",
        "csv_path": "./generated_docs/7276_Electrical_20260405.csv",
        "json_path": "./generated_docs/7276_Electrical_20260405.json"
    },
    "pipeline_stats": {
        "total_ms": 115600,
        "attempts": 3,
        "tokens_used": 0,
        "records_processed": 107,
        "items_extracted": 49
    }
}
```

**Key advantage:** Every item is a structured object with source traceability (drawing_name, page, source_snippet), classification (trade, csi_code), and confidence score. The frontend can render tables, filter, sort, and link back to source drawings.

### Feature Capability Matrix

| Capability | Old `/api/chat` | New `/api/scope-gap` |
|-----------|-----------------|---------------------|
| **Structured scope items** | No (free-form markdown) | Yes (JSON array with IDs, sources, CSI) |
| **Source traceability per item** | No | Yes (drawing_name, page, source_snippet) |
| **CSI code per item** | No (mentioned in text but not structured) | Yes (csi_code field per item) |
| **Confidence score per item** | No | Yes (0.0-1.0 per item) |
| **Ambiguity detection** | No | Yes (competing trades, severity, recommendation) |
| **Gotcha/risk scanning** | No | Yes (hidden costs, coordination, missing scope) |
| **Completeness measurement** | No | Yes (drawing %, CSI %, overall %) |
| **Backpropagation (multi-pass)** | No (single LLM call) | Yes (up to 3 attempts, targeted re-extraction) |
| **Quality review** | No | Yes (accuracy score, corrections applied) |
| **Multiple document formats** | Word only | Word + PDF + CSV + JSON |
| **Background job execution** | No | Yes (submit → poll → download) |
| **Job cancellation** | No | Yes |
| **Session run history** | No (conversation history only) | Yes (each pipeline run tracked with stats) |
| **Resolve ambiguities** | No | Yes (assign trade, persisted in session) |
| **Acknowledge gotchas** | No | Yes (mark as noted) |
| **Ignore/restore items** | No | Yes (exclude from reports) |
| **Context-aware follow-up chat** | Yes (but about general questions) | Yes (specifically about the scope report) |
| **Streaming progress** | Token-level SSE | Agent-level SSE (which agent is running, completeness %) |
| **Multiple trades per query** | Intent detection (may misidentify) | Explicit trade parameter (no ambiguity) |

### When to Use Which API

| Use Case | Recommended API |
|----------|----------------|
| Quick question about drawings | Old: `POST /api/chat` — "What plumbing fixtures are on floor 2?" |
| Generate a free-form scope narrative | Old: `POST /api/chat` — "Create comprehensive plumbing scope" |
| Formal scope gap report with traceability | **New: `POST /api/scope-gap/generate`** |
| Identify ambiguous trade responsibilities | **New: `/api/scope-gap/generate`** → check `ambiguities[]` |
| Find hidden costs and risks | **New: `/api/scope-gap/generate`** → check `gotchas[]` |
| Measure extraction completeness | **New: `/api/scope-gap/generate`** → check `completeness` |
| Export structured data for other systems | **New:** Use JSON output from `documents.json_path` |
| Background processing for large projects | **New: `POST /api/scope-gap/submit`** |
| Let users resolve trade overlaps | **New: `POST /sessions/{id}/resolve-ambiguity`** |
| Ask follow-up about a specific report | **New: `POST /sessions/{id}/chat`** |
| Download Word doc | Both: Old uses `/api/documents/{id}/download`, New generates all 4 formats |

### Migration Notes

- **Old APIs are NOT deprecated.** Both APIs coexist. Old endpoints work exactly as before.
- **No breaking changes.** Zero modifications to existing endpoint behavior.
- **Shared infrastructure.** Both APIs use the same APIClient, CacheService, and S3Utils.
- **Separate sessions.** Old chat sessions (`/api/sessions/`) and new scope gap sessions (`/api/scope-gap/sessions/`) are completely independent.

---

## Quick Reference

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 1 | POST | `/api/scope-gap/generate` | Run pipeline (blocking) |
| 2 | POST | `/api/scope-gap/stream` | Run pipeline (SSE streaming) |
| 3 | POST | `/api/scope-gap/submit` | Submit as background job |
| 4 | GET | `/api/scope-gap/jobs` | List all jobs |
| 5 | GET | `/api/scope-gap/jobs/{job_id}/status` | Get job progress |
| 6 | GET | `/api/scope-gap/jobs/{job_id}/result` | Get job result |
| 7 | POST | `/api/scope-gap/jobs/{job_id}/continue` | Continue partial job |
| 8 | DELETE | `/api/scope-gap/jobs/{job_id}` | Cancel a job |
| 9 | GET | `/api/scope-gap/sessions` | List sessions |
| 10 | GET | `/api/scope-gap/sessions/{session_id}` | Get session detail |
| 11 | DELETE | `/api/scope-gap/sessions/{session_id}` | Delete session |
| 12 | POST | `/api/scope-gap/sessions/{session_id}/resolve-ambiguity` | Resolve trade overlap |
| 13 | POST | `/api/scope-gap/sessions/{session_id}/acknowledge-gotcha` | Acknowledge risk |
| 14 | POST | `/api/scope-gap/sessions/{session_id}/ignore-item` | Ignore scope item |
| 15 | POST | `/api/scope-gap/sessions/{session_id}/restore-item` | Restore ignored item |
| 16 | POST | `/api/scope-gap/sessions/{session_id}/chat` | Follow-up Q&A |

---

## 1. Pipeline Execution

### 1.1 POST /api/scope-gap/generate

**Purpose:** Run the full 7-agent scope gap pipeline synchronously. Returns the complete result when done.

**When to use:** Small-to-medium datasets (<2000 records). For large datasets, use `/submit` instead.

**Request:**
```json
POST /api/scope-gap/generate
Content-Type: application/json

{
    "project_id": 7276,
    "trade": "Electrical",
    "set_ids": null,
    "session_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | int | Yes | iFieldSmart project ID |
| `trade` | string | Yes | Trade name (e.g., "Electrical", "Plumbing", "HVAC") |
| `set_ids` | list[int] | No | Filter by drawing set IDs. Null = all sets. |
| `session_id` | string | No | Reuse an existing session. Null = auto-create. |

**Response (200):** Full `ScopeGapResult` (see Response Schema below)

**Response (500):** `{"detail": "error message"}`

**Timing:** ~30s for small projects, ~2-5 min for large projects

**Postman Example:**
```
Method: POST
URL: http://54.197.189.113:8003/api/scope-gap/generate
Headers: Content-Type: application/json
Body (raw JSON):
{
    "project_id": 7276,
    "trade": "Electrical"
}
```

---

### 1.2 POST /api/scope-gap/stream

**Purpose:** Run pipeline with real-time SSE progress events. Shows which agents are running, completeness %, backpropagation attempts.

**When to use:** When you want to show real-time progress in the UI.

**Request:** Same body as `/generate`

```json
POST /api/scope-gap/stream
Content-Type: application/json

{
    "project_id": 7276,
    "trade": "Electrical"
}
```

**Response:** `text/event-stream` (SSE)

**SSE Events:**
```
event: pipeline_start
data: {"project_id": 7276, "trade": "Electrical"}

event: data_fetch
data: {"message": "Fetching drawing records..."}

event: agent_start
data: {"agent": "extraction", "message": "Starting extraction agent..."}

event: agent_complete
data: {"agent": "extraction", "elapsed_ms": 19000, "attempt": 1}

event: agent_start
data: {"agent": "classification", "message": "Starting classification agent..."}

event: agent_start
data: {"agent": "ambiguity", "message": "Starting ambiguity agent..."}

event: agent_start
data: {"agent": "gotcha", "message": "Starting gotcha agent..."}

event: agent_complete
data: {"agent": "classification", "elapsed_ms": 12000, "attempt": 1}

event: completeness
data: {"attempt": 1, "overall_pct": 87.3, "drawing_coverage_pct": 80.0, "missing_drawings": ["E-104"], "is_complete": false}

event: backpropagation
data: {"attempt": 2, "reason": "1 drawings missing", "missing_drawings": ["E-104"]}

event: completeness
data: {"attempt": 2, "overall_pct": 98.6, "is_complete": true}

event: agent_complete
data: {"agent": "quality", "elapsed_ms": 8000, "attempt": 1}

event: pipeline_complete
data: {"total_ms": 115000, "attempts": 2, "items": 49, "ambiguities": 8, "gotchas": 9}

event: result
data: {full ScopeGapResult JSON}
```

**Note:** SSE requires special handling in Postman. Use the React UI or `curl` for testing:
```bash
curl -N -X POST http://54.197.189.113:8003/api/scope-gap/stream \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "trade": "Electrical"}'
```

---

### 1.3 POST /api/scope-gap/submit

**Purpose:** Submit pipeline as a background job. Returns immediately with a job_id for polling.

**When to use:** Large datasets, or when you don't want to wait for the result.

**Request:** Same body as `/generate`

```json
POST /api/scope-gap/submit
Content-Type: application/json

{
    "project_id": 7276,
    "trade": "Electrical"
}
```

**Response (202):**
```json
{
    "job_id": "job_a1b2c3d4",
    "status": "queued",
    "poll_url": "/api/scope-gap/jobs/job_a1b2c3d4/status"
}
```

---

## 2. Job Management

### 2.1 GET /api/scope-gap/jobs

**Purpose:** List all pipeline jobs. Optional filters by project_id and status.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `project_id` | int | Filter by project |
| `status` | string | Filter by status: queued, running, completed, partial, failed, cancelled |

**Request:**
```
GET /api/scope-gap/jobs
GET /api/scope-gap/jobs?project_id=7276
GET /api/scope-gap/jobs?status=running
GET /api/scope-gap/jobs?project_id=7276&status=completed
```

**Response (200):**
```json
[
    {
        "job_id": "job_a1b2c3d4",
        "status": "completed",
        "project_id": 7276,
        "trade": "Electrical",
        "created_at": "2026-04-05T14:32:00Z",
        "started_at": "2026-04-05T14:32:01Z",
        "completed_at": "2026-04-05T14:34:00Z"
    }
]
```

---

### 2.2 GET /api/scope-gap/jobs/{job_id}/status

**Purpose:** Get current status and progress for a specific job. Poll this every 5 seconds during execution.

**Request:**
```
GET /api/scope-gap/jobs/job_a1b2c3d4/status
```

**Response (200):**
```json
{
    "job_id": "job_a1b2c3d4",
    "status": "running",
    "project_id": 7276,
    "trade": "Electrical",
    "created_at": "2026-04-05T14:32:00Z",
    "started_at": "2026-04-05T14:32:01Z",
    "completed_at": null,
    "error": null
}
```

**Response (404):** `{"detail": "Job job_xyz not found"}`

**Job statuses:**

| Status | Meaning |
|--------|---------|
| `queued` | Waiting for execution slot (semaphore) |
| `running` | Pipeline is executing |
| `completed` | All agents finished, 100% complete |
| `partial` | <95% completeness after 3 attempts |
| `failed` | Pipeline error |
| `cancelled` | User cancelled |

---

### 2.3 GET /api/scope-gap/jobs/{job_id}/result

**Purpose:** Get the result of a completed or partial job.

**Request:**
```
GET /api/scope-gap/jobs/job_a1b2c3d4/result
```

**Response (200):** Result metadata (use session endpoint for full data)
```json
{
    "job_id": "job_a1b2c3d4",
    "status": "completed",
    "message": "Use session endpoint for full result."
}
```

**Response (409):** `{"detail": "Job job_xyz is 'running' -- result not yet available"}`

---

### 2.4 POST /api/scope-gap/jobs/{job_id}/continue

**Purpose:** Continue a partial extraction. Creates a new job targeting the same project/trade. Only works when status is `partial`.

**Request:**
```
POST /api/scope-gap/jobs/job_a1b2c3d4/continue
```

**Response (202):**
```json
{
    "job_id": "job_e5f6g7h8",
    "status": "queued",
    "continued_from": "job_a1b2c3d4",
    "poll_url": "/api/scope-gap/jobs/job_e5f6g7h8/status"
}
```

**Response (409):** `{"detail": "Job job_xyz is 'completed' -- can only continue partial jobs"}`

---

### 2.5 DELETE /api/scope-gap/jobs/{job_id}

**Purpose:** Cancel a queued or running job.

**Request:**
```
DELETE /api/scope-gap/jobs/job_a1b2c3d4
```

**Response (200):**
```json
{
    "cancelled": true,
    "job_id": "job_a1b2c3d4"
}
```

**Response (409):** `{"detail": "Job job_xyz is 'completed' -- cannot cancel"}`

---

## 3. Session Management

### 3.1 GET /api/scope-gap/sessions

**Purpose:** List all scope gap sessions. Sessions are created automatically when pipeline runs.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `project_id` | int | Filter by project |
| `trade` | string | Filter by trade |

**Request:**
```
GET /api/scope-gap/sessions
GET /api/scope-gap/sessions?project_id=7276
GET /api/scope-gap/sessions?project_id=7276&trade=Electrical
```

**Response (200):**
```json
[
    {
        "id": "sg_session_a1b2c3d4",
        "project_id": 7276,
        "trade": "Electrical",
        "set_ids": null,
        "created_at": "2026-04-05T14:32:00Z",
        "updated_at": "2026-04-05T14:34:00Z",
        "runs_count": 1,
        "has_result": true
    }
]
```

---

### 3.2 GET /api/scope-gap/sessions/{session_id}

**Purpose:** Get full session detail including run history, user decisions, messages, and latest result.

**Request:**
```
GET /api/scope-gap/sessions/sg_session_a1b2c3d4
```

**Response (200):** Full `ScopeGapSession` object:
```json
{
    "id": "sg_session_a1b2c3d4",
    "user_id": null,
    "project_id": 7276,
    "trade": "Electrical",
    "set_ids": null,
    "created_at": "2026-04-05T14:32:00Z",
    "updated_at": "2026-04-05T14:34:00Z",
    "runs": [
        {
            "run_id": "run_x1y2z3",
            "job_id": null,
            "started_at": "2026-04-05T14:32:02Z",
            "completed_at": "2026-04-05T14:33:58Z",
            "status": "partial",
            "attempts": 3,
            "completeness_pct": 72.8,
            "items_count": 49,
            "ambiguities_count": 8,
            "gotchas_count": 9,
            "token_usage": 0,
            "cost_usd": 0.0,
            "documents": {
                "word_path": "./generated_docs/7276_Electrical_20260405.docx",
                "pdf_path": "./generated_docs/7276_Electrical_20260405.pdf",
                "csv_path": "./generated_docs/7276_Electrical_20260405.csv",
                "json_path": "./generated_docs/7276_Electrical_20260405.json"
            }
        }
    ],
    "ambiguity_resolutions": {},
    "gotcha_acknowledgments": [],
    "ignored_items": [],
    "messages": [],
    "latest_result": { ... full ScopeGapResult ... }
}
```

---

### 3.3 DELETE /api/scope-gap/sessions/{session_id}

**Purpose:** Delete a session and all its data.

**Request:**
```
DELETE /api/scope-gap/sessions/sg_session_a1b2c3d4
```

**Response (200):**
```json
{
    "deleted": true,
    "session_id": "sg_session_a1b2c3d4"
}
```

---

## 4. User Decisions

These endpoints let users act on pipeline results — resolve ambiguities, acknowledge risks, ignore/restore items. Decisions are persisted in the session and respected on subsequent pipeline runs.

### 4.1 POST /api/scope-gap/sessions/{session_id}/resolve-ambiguity

**Purpose:** Assign a trade to an ambiguous scope item.

**Request:**
```json
POST /api/scope-gap/sessions/sg_session_a1b2c3d4/resolve-ambiguity
Content-Type: application/json

{
    "ambiguity_id": "amb_x1y2z3",
    "assigned_trade": "Roofing"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ambiguity_id` | string | Yes | ID from the ambiguities list in the pipeline result |
| `assigned_trade` | string | Yes | Trade to assign the ambiguous scope to |

**Response (200):**
```json
{
    "resolved": true,
    "ambiguity_id": "amb_x1y2z3",
    "assigned_trade": "Roofing"
}
```

---

### 4.2 POST /api/scope-gap/sessions/{session_id}/acknowledge-gotcha

**Purpose:** Mark a gotcha/risk as acknowledged (user has seen it and noted it).

**Request:**
```json
POST /api/scope-gap/sessions/sg_session_a1b2c3d4/acknowledge-gotcha
Content-Type: application/json

{
    "gotcha_id": "gtc_a1b2c3"
}
```

**Response (200):**
```json
{
    "acknowledged": true,
    "gotcha_id": "gtc_a1b2c3"
}
```

---

### 4.3 POST /api/scope-gap/sessions/{session_id}/ignore-item

**Purpose:** Ignore a scope item (exclude from future reports).

**Request:**
```json
POST /api/scope-gap/sessions/sg_session_a1b2c3d4/ignore-item
Content-Type: application/json

{
    "item_id": "itm_x1y2z3"
}
```

**Response (200):**
```json
{
    "ignored": true,
    "item_id": "itm_x1y2z3"
}
```

---

### 4.4 POST /api/scope-gap/sessions/{session_id}/restore-item

**Purpose:** Restore a previously ignored scope item.

**Request:**
```json
POST /api/scope-gap/sessions/sg_session_a1b2c3d4/restore-item
Content-Type: application/json

{
    "item_id": "itm_x1y2z3"
}
```

**Response (200):**
```json
{
    "restored": true,
    "item_id": "itm_x1y2z3"
}
```

---

## 5. Follow-up Chat

### 5.1 POST /api/scope-gap/sessions/{session_id}/chat

**Purpose:** Ask a follow-up question about the scope gap report. Uses the session's latest result as context.

**Request:**
```json
POST /api/scope-gap/sessions/sg_session_a1b2c3d4/chat
Content-Type: application/json

{
    "message": "Why was fire stopping flagged as a gotcha?"
}
```

**Response (200):**
```json
{
    "answer": "Fire stopping was flagged because drawing A-25 references fire-rated penetrations at floor levels, but no trade was explicitly assigned responsibility for fire stopping installation. This is a common coordination gap between Fire Protection and General Trades.",
    "source_refs": ["gtc_abc123", "itm_def456"]
}
```

---

## 6. Response Schema — ScopeGapResult

The full result returned by `/generate` and stored in sessions:

```json
{
    "project_id": 7276,
    "project_name": "",
    "trade": "Electrical",

    "items": [
        {
            "id": "itm_a1b2c3d4",
            "text": "Install electric double oven per riser diagram",
            "drawing_name": "A-25",
            "drawing_title": null,
            "page": 1,
            "source_snippet": "electric double oven per riser",
            "confidence": 0.95,
            "csi_hint": null,
            "source_record_id": null,
            "trade": "Electrical",
            "csi_code": "26 27 26",
            "csi_division": "26 - Electrical",
            "classification_confidence": 0.92,
            "classification_reason": "Electrical appliance connection"
        }
    ],

    "ambiguities": [
        {
            "id": "amb_e5f6g7h8",
            "scope_text": "Flashing and waterproofing at roof penetrations",
            "competing_trades": ["Roofing", "Sheet Metal"],
            "severity": "high",
            "recommendation": "Assign to Roofing per CSI 07 62 00",
            "source_items": ["itm_abc"],
            "drawing_refs": ["A-201"]
        }
    ],

    "gotchas": [
        {
            "id": "gtc_i9j0k1l2",
            "risk_type": "hidden_cost",
            "description": "Temporary power during construction not explicitly scoped",
            "severity": "high",
            "affected_trades": ["Electrical", "General Trades"],
            "recommendation": "Add temporary power provisions to Electrical scope",
            "drawing_refs": ["E-101"]
        }
    ],

    "completeness": {
        "drawing_coverage_pct": 68.8,
        "csi_coverage_pct": 61.5,
        "hallucination_count": 0,
        "overall_pct": 72.8,
        "missing_drawings": ["A-15", "A-16", "A-17", "A-18", "A-24"],
        "missing_csi_codes": ["26 05 00"],
        "hallucinated_items": [],
        "is_complete": false,
        "attempt": 3
    },

    "quality": {
        "accuracy_score": 0.98,
        "corrections": [],
        "validated_items": [ ... same as items ... ],
        "removed_items": [],
        "summary": "98% accuracy, 0 corrections"
    },

    "documents": {
        "word_path": "./generated_docs/7276_Electrical_20260405_144317.docx",
        "pdf_path": "./generated_docs/7276_Electrical_20260405_144317.pdf",
        "csv_path": "./generated_docs/7276_Electrical_20260405_144317.csv",
        "json_path": "./generated_docs/7276_Electrical_20260405_144317.json"
    },

    "pipeline_stats": {
        "total_ms": 115600,
        "attempts": 3,
        "tokens_used": 0,
        "estimated_cost_usd": 0.0,
        "per_agent_timing": {
            "extraction_attempt_1": 19000,
            "extraction_attempt_2": 15000,
            "extraction_attempt_3": 12000
        },
        "records_processed": 107,
        "items_extracted": 49
    }
}
```

---

## 7. Available Trades

Use these trade names in the `trade` field:

| Trade | CSI Divisions |
|-------|--------------|
| Electrical | 26, 27, 28 |
| Plumbing | 22 |
| HVAC | 23 |
| Structural | - |
| Concrete | 03 |
| Fire Sprinkler | 21 |
| Flooring | 09.6 |
| Framing, Drywall & Insulation | 09.2, 07.2 |
| Glass & Glazing | 08.4, 08.5 |
| Painting & Coatings | 09.9 |
| Doors Frames & Hardware | 08.1, 08.7 |
| Elevators | 14 |
| Roofing & Waterproofing | 07.5, 07.6 |
| Structural Steel | 05 |
| Casework | 06.4, 12.3 |
| Ceramic Tile | 09.3 |
| Acoustical Ceilings | 09.5 |
| Earthwork | 31 |
| Abatement | 02 |

---

## 8. Test Projects (Sandbox)

| Project ID | Name | Electrical Records | Notes |
|-----------|------|-------------------|-------|
| 7276 | Singh Residence | ~107 records | Small, fast (~2 min) |
| 7298 | Granville Hotel | ~11,360 records | Large, slow (~4 min) |

---

## 9. Error Responses

All endpoints return standard HTTP error responses:

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 202 | Accepted (background job submitted) |
| 404 | Job/Session not found |
| 409 | Conflict (e.g., job not in correct state) |
| 422 | Validation error (bad request body) |
| 500 | Internal server error |

Error format:
```json
{
    "detail": "Human-readable error message"
}
```

---

## 10. Postman Collection Quick Setup

1. Create a new Collection: "Scope Gap Pipeline"
2. Set Collection variable: `base_url` = `http://54.197.189.113:8003`
3. Import these requests:

### Pipeline
- `POST {{base_url}}/api/scope-gap/generate` — Body: `{"project_id": 7276, "trade": "Electrical"}`
- `POST {{base_url}}/api/scope-gap/submit` — Body: `{"project_id": 7276, "trade": "Electrical"}`

### Jobs
- `GET {{base_url}}/api/scope-gap/jobs`
- `GET {{base_url}}/api/scope-gap/jobs/{{job_id}}/status`
- `GET {{base_url}}/api/scope-gap/jobs/{{job_id}}/result`
- `POST {{base_url}}/api/scope-gap/jobs/{{job_id}}/continue`
- `DELETE {{base_url}}/api/scope-gap/jobs/{{job_id}}`

### Sessions
- `GET {{base_url}}/api/scope-gap/sessions`
- `GET {{base_url}}/api/scope-gap/sessions/{{session_id}}`
- `DELETE {{base_url}}/api/scope-gap/sessions/{{session_id}}`

### User Decisions
- `POST {{base_url}}/api/scope-gap/sessions/{{session_id}}/resolve-ambiguity` — Body: `{"ambiguity_id": "amb_xxx", "assigned_trade": "Roofing"}`
- `POST {{base_url}}/api/scope-gap/sessions/{{session_id}}/acknowledge-gotcha` — Body: `{"gotcha_id": "gtc_xxx"}`
- `POST {{base_url}}/api/scope-gap/sessions/{{session_id}}/ignore-item` — Body: `{"item_id": "itm_xxx"}`
- `POST {{base_url}}/api/scope-gap/sessions/{{session_id}}/restore-item` — Body: `{"item_id": "itm_xxx"}`

### Chat
- `POST {{base_url}}/api/scope-gap/sessions/{{session_id}}/chat` — Body: `{"message": "Why was fire stopping flagged?"}`

**Workflow for testing:**
1. Call `/generate` with project 7276 + Electrical → save response
2. Call `/sessions` → get the session_id from the list
3. Call `/sessions/{session_id}` → see full detail with items, ambiguities, gotchas
4. Call `/sessions/{session_id}/resolve-ambiguity` with an ambiguity_id from the result
5. Call `/sessions/{session_id}/chat` with a question about the report
