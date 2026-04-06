# Construction Intelligence Agent — Complete API Reference (Postman)

**Base URL (Sandbox):** `http://54.197.189.113:8003`
**Base URL (Production):** `https://ai.ifieldsmart.com/construction`

**Total endpoints: 34**

---

## 1. System (2 endpoints)

### 1.1 GET `/` — Root

Returns API info.

```
No body, no params
```

**Response:** `{"message": "Construction Intelligence Agent API", "docs": "/docs"}`

---

### 1.2 GET `/health` — Health Check

Service status for Redis, OpenAI, S3.

```
No body, no params
```

**Response:** `{"status": "ok", "redis": "connected", "openai": "configured"}`

---

## 2. Chat Pipeline (5 endpoints)

### 2.1 POST `/api/chat` — Generate Scope Document

The main endpoint. Detects trade from query, fetches data from MongoDB, generates scope via LLM, creates Word doc.

```json
{
  "project_id": 7276,
  "query": "Generate exhibit for electrical",
  "session_id": null,
  "user_id": null,
  "generate_document": true,
  "set_ids": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | int | Yes | MongoDB project ID |
| `query` | string | Yes | Natural language query (min 3 chars) |
| `session_id` | string | No | Continue existing conversation |
| `user_id` | string | No | User identifier |
| `generate_document` | bool | No | Generate .docx file (default: true) |
| `set_ids` | list[int] | No | Filter by specific drawing sets |

**Response:** Full ChatResponse with answer, document download URL, intent, token usage, groundedness score.

---

### 2.2 POST `/api/chat/stream` — Streaming Chat (SSE)

Same request body as `/api/chat`. Returns Server-Sent Events with token-by-token output.

```json
{
  "project_id": 7276,
  "query": "Generate exhibit for electrical"
}
```

**SSE Events:** `token` (text chunks), `done` (final result), `error`

---

### 2.3 GET `/api/sessions/{session_id}/history` — Chat History

Get conversation messages for a session.

```
Path: session_id = "abc123def456"
No body
```

---

### 2.4 GET `/api/sessions/{session_id}/tokens` — Token Usage

Get cumulative token/cost stats for a session.

```
Path: session_id = "abc123def456"
No body
```

**Response:** `{"session_id", "total_input", "total_output", "total_tokens", "total_cost_usd", "call_count"}`

---

### 2.5 DELETE `/api/sessions/{session_id}` — Clear Session

```
Path: session_id = "abc123def456"
No body
```

---

## 3. Documents (2 endpoints)

### 3.1 GET `/api/documents/{file_id}/download` — Download Document

Downloads the generated Word (.docx) file. Returns file or 302 redirect to S3.

```
Path: file_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
No body
```

---

### 3.2 GET `/api/documents/{file_id}/info` — Document Metadata

```
Path: file_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
No body
```

**Response:** `{"file_id", "filename", "size_bytes", "download_url", "storage"}`

---

## 4. Project Context (1 endpoint)

### 4.1 GET `/api/projects/{project_id}/context` — Project Metadata

Returns available trades, CSI divisions, and text count.

```
Path: project_id = 7276
No body
```

---

## 5. Scope Gap Pipeline — Execution (3 endpoints)

### 5.1 POST `/api/scope-gap/generate` — Run Pipeline (Blocking)

Runs the full 7-agent pipeline synchronously. Use for small datasets (<2000 records).

```json
{
  "project_id": 7276,
  "trade": "Electrical",
  "set_ids": null,
  "session_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_id` | int | Yes | MongoDB project ID |
| `trade` | string | Yes | Trade name (e.g., "Electrical", "Plumbing") |
| `set_ids` | list[int] | No | Filter by drawing sets |
| `session_id` | string | No | Continue existing session |

**Response:** Full ScopeGapResult — items, ambiguities, gotchas, completeness, quality, documents, stats.

---

### 5.2 POST `/api/scope-gap/stream` — Run Pipeline (SSE Streaming)

Same body as `/generate`. Returns SSE events with per-agent progress + final result.

```json
{
  "project_id": 7276,
  "trade": "Electrical"
}
```

**SSE Events:** `agent_start`, `agent_complete`, `backpropagation`, `pipeline_complete`, `result`, `error`

---

### 5.3 POST `/api/scope-gap/submit` — Run Pipeline (Background Job)

Returns 202 immediately with job_id. Poll `/jobs/{id}/status` for progress.

```json
{
  "project_id": 7276,
  "trade": "Electrical"
}
```

**Response (202):** `{"job_id": "job_abc123", "status": "pending", "poll_url": "/api/scope-gap/jobs/job_abc123/status"}`

---

## 6. Scope Gap Pipeline — Job Management (5 endpoints)

### 6.1 GET `/api/scope-gap/jobs` — List Jobs

```
Query params (all optional):
  project_id = 7276
  status = "completed"
```

---

### 6.2 GET `/api/scope-gap/jobs/{job_id}/status` — Job Status

```
Path: job_id = "job_abc123"
```

**Response:** `{"job_id", "status", "progress", "created_at", "started_at", "completed_at", "error"}`

---

### 6.3 GET `/api/scope-gap/jobs/{job_id}/result` — Job Result

Only works when status is `completed` or `partial`.

```
Path: job_id = "job_abc123"
```

---

### 6.4 POST `/api/scope-gap/jobs/{job_id}/continue` — Continue Partial Job

Re-submits a partial extraction targeting missing drawings.

```
Path: job_id = "job_abc123"
No body
```

**Response (202):** `{"job_id": "job_new456", "continued_from": "job_abc123"}`

---

### 6.5 DELETE `/api/scope-gap/jobs/{job_id}` — Cancel Job

```
Path: job_id = "job_abc123"
No body
```

---

## 7. Scope Gap — Session Management (3 endpoints)

### 7.1 GET `/api/scope-gap/sessions` — List Sessions

```
Query params (all optional):
  project_id = 7276
  trade = "Electrical"
```

---

### 7.2 GET `/api/scope-gap/sessions/{session_id}` — Session Detail

Full session with runs, resolutions, messages, and latest result.

```
Path: session_id = "sess_abc123"
```

---

### 7.3 DELETE `/api/scope-gap/sessions/{session_id}` — Delete Session

```
Path: session_id = "sess_abc123"
```

---

## 8. Scope Gap — User Decisions (5 endpoints)

### 8.1 POST `/api/scope-gap/sessions/{session_id}/resolve-ambiguity` — Assign Trade to Ambiguity

When the pipeline finds an item that belongs to multiple trades, the user resolves it.

```json
{
  "ambiguity_id": "amb_d7e4f1a2",
  "assigned_trade": "Plumbing"
}
```

---

### 8.2 POST `/api/scope-gap/sessions/{session_id}/acknowledge-gotcha` — Acknowledge Risk

Mark a gotcha (hidden cost, missing scope, coordination risk) as acknowledged.

```json
{
  "gotcha_id": "gtc_c9a3b8e5"
}
```

---

### 8.3 POST `/api/scope-gap/sessions/{session_id}/ignore-item` — Exclude Item

Remove a scope item from the report.

```json
{
  "item_id": "itm_a3f7b2c1"
}
```

---

### 8.4 POST `/api/scope-gap/sessions/{session_id}/restore-item` — Restore Item

Bring back a previously ignored item.

```json
{
  "item_id": "itm_a3f7b2c1"
}
```

---

### 8.5 POST `/api/scope-gap/sessions/{session_id}/chat` — Follow-up Q&A

Ask questions about the scope gap report.

```json
{
  "message": "What panels are mentioned in the electrical scope?"
}
```

---

## 9. Project-Level Endpoints — Phase 12 (6 endpoints)

### 9.1 GET `/api/scope-gap/projects/{project_id}/trades` — Discover Trades

Lists all trades for a project with record counts, pipeline status, and color. Call this BEFORE running the pipeline to know what trades are available.

```
Path: project_id = 7276
Query params (optional):
  set_id = 4730
```

**Response:**
```json
{
  "project_id": 7276,
  "trades": [
    {"trade": "Electrical", "record_count": 107, "status": "ready", "color": "#F48FB1"},
    {"trade": "Plumbing", "record_count": 45, "status": "pending", "color": "#81D4FA"},
    {"trade": "HVAC", "record_count": 89, "status": "failed", "color": "#90A4AE"}
  ],
  "total_trades": 3,
  "total_records": 241
}
```

Status values: `ready` (has results), `pending` (not yet run), `failed` (last run errored)

---

### 9.2 GET `/api/scope-gap/projects/{project_id}/trade-colors` — Color Palette

Returns hex + RGB colors for all trades. 23 base colors, auto-generated for unknown trades.

```
Path: project_id = 7276
```

**Response:**
```json
{
  "colors": {
    "Electrical": {"hex": "#F48FB1", "rgb": [244, 143, 177]},
    "HVAC": {"hex": "#90A4AE", "rgb": [144, 164, 174]},
    "Custom Trade": {"hex": "#7B1FA2", "rgb": [123, 31, 162]}
  }
}
```

---

### 9.3 GET `/api/scope-gap/projects/{project_id}/drawings` — Drawing Tree

Returns drawings + specs categorized by discipline (ELECTRICAL, MECHANICAL, etc.) for the sidebar.

```
Path: project_id = 7276
Query params (optional):
  set_id = 4730
```

**Response:**
```json
{
  "project_id": 7276,
  "total_drawings": 85,
  "total_specs": 42,
  "categories": {
    "ELECTRICAL": {
      "drawings": [
        {"drawing_name": "E0.03", "drawing_title": "Schedules", "source_type": "drawing"}
      ],
      "specs": [
        {"drawing_name": "260000", "drawing_title": "Electrical General", "source_type": "specification"}
      ]
    },
    "MECHANICAL": { ... }
  }
}
```

---

### 9.4 GET `/api/scope-gap/projects/{project_id}/drawings/meta` — Drawing Metadata (Batch)

Fetch metadata for specific drawings (used by Reference Panel when user clicks a source link).

```
Path: project_id = 7276
Query params (required):
  drawing_names = "E0.03,E1.01,M2.01"
```

**Response:**
```json
{
  "drawings": {
    "E0.03": {
      "drawing_name": "E0.03",
      "drawing_title": "Schedules - Electrical",
      "discipline": "ELECTRICAL",
      "source_type": "drawing",
      "set_name": "100% CD",
      "set_trade": "Electrical",
      "record_count": 107
    }
  }
}
```

---

### 9.5 GET `/api/scope-gap/projects/{project_id}/status` — Pipeline Dashboard

Overview of all trade pipeline runs for a project.

```
Path: project_id = 7276
```

**Response:**
```json
{
  "project_id": 7276,
  "session_id": "abc123",
  "overall_progress": {
    "total_trades": 67,
    "completed": 45,
    "failed": 3,
    "pct": 67.2
  },
  "total_items": 3240,
  "total_cost_usd": 6.70,
  "trades": [
    {"trade": "Electrical", "status": "ready", "items": 107},
    {"trade": "HVAC", "status": "failed", "error": "Timeout"}
  ]
}
```

---

### 9.6 POST `/api/scope-gap/projects/{project_id}/run-all` — Run All Trades

Triggers the ProjectOrchestrator to run the 7-agent pipeline for all (or selected) trades in parallel.

```json
{
  "set_ids": [4730],
  "force_rerun": false,
  "trades": ["Electrical", "Plumbing"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `set_ids` | list[int] | No | Filter by drawing sets |
| `force_rerun` | bool | No | Ignore cached results, re-run everything (default: false) |
| `trades` | list[string] | No | Run only specific trades (default: all) |

**Response (202):** `{"project_id": 7276, "message": "Project pipeline queued"}`

---

## 10. Highlights — Phase 12 (4 endpoints)

All highlight endpoints require `X-User-Id` header. Highlights are per-user, stored in S3.

### 10.1 POST `/api/scope-gap/highlights` — Create Highlight

Draw a highlight rectangle on a drawing with metadata.

**Headers:** `X-User-Id: user_123`

```json
{
  "project_id": 7276,
  "drawing_name": "E0.03",
  "page": 1,
  "x": 245.5,
  "y": 380.2,
  "width": 312.0,
  "height": 48.0,
  "color": "#F48FB1",
  "opacity": 0.3,
  "label": "Panel LP-1",
  "trade": "Electrical",
  "critical": true,
  "comment": "Verify in field",
  "scope_item_id": "itm_a3f7b2c1",
  "scope_item_ids": ["itm_a3f7b2c1", "itm_b4e8c3d2"]
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `project_id` | int | Yes | — | Project ID |
| `drawing_name` | string | Yes | — | Drawing name |
| `page` | int | No | 1 | Page number |
| `x` | float | Yes | — | Left position (points) |
| `y` | float | Yes | — | Top position (points) |
| `width` | float | Yes | — | Rectangle width |
| `height` | float | Yes | — | Rectangle height |
| `color` | string | No | "#FFEB3B" | Hex color |
| `opacity` | float | No | 0.3 | Transparency |
| `label` | string | No | "" | Short label |
| `trade` | string | No | "" | Associated trade |
| `critical` | bool | No | false | Flag as critical |
| `comment` | string | No | "" | User comment |
| `scope_item_id` | string | No | null | Link to one scope item |
| `scope_item_ids` | list[str] | No | [] | Link to multiple items |

**Response (201):** Created highlight with `id` (prefixed `hl_`)

---

### 10.2 GET `/api/scope-gap/highlights` — List Highlights

Get all highlights for a drawing (per-user). Cached in Redis (5 min TTL).

**Headers:** `X-User-Id: user_123`

```
Query params (required):
  project_id = 7276
  drawing_name = E0.03
```

**Response:** Array of highlight objects

---

### 10.3 PATCH `/api/scope-gap/highlights/{highlight_id}` — Update Highlight

Move, resize, or edit a highlight. Only provided fields are updated.

**Headers:** `X-User-Id: user_123`

```
Path: highlight_id = "hl_a3f7b2c1"
Query params (required):
  project_id = 7276
  drawing_name = E0.03
```

```json
{
  "x": 250.0,
  "label": "Updated label",
  "critical": false,
  "comment": "Reviewed"
}
```

---

### 10.4 DELETE `/api/scope-gap/highlights/{highlight_id}` — Delete Highlight

**Headers:** `X-User-Id: user_123`

```
Path: highlight_id = "hl_a3f7b2c1"
Query params (required):
  project_id = 7276
  drawing_name = E0.03
```

---

## 11. Webhook — Phase 12 (1 endpoint)

### 11.1 POST `/api/scope-gap/webhooks/project-event` — Receive Webhook

Called by iFieldSmart when a project is created or drawings are uploaded. Triggers background pre-computation.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `X-Webhook-Signature` | Yes | `sha256=<hmac_hex>` — HMAC-SHA256 of raw body with shared secret |
| `X-Webhook-Event-Id` | No | Unique event ID for idempotency dedup |

**Body (project created):**
```json
{
  "event": "project.created",
  "project_id": 7276,
  "project_name": "Granville Hotel",
  "timestamp": "2026-04-06T10:00:00Z"
}
```

**Body (drawings uploaded):**
```json
{
  "event": "drawings.uploaded",
  "project_id": 7276,
  "set_id": 4730,
  "changed_trades": ["Electrical", "HVAC"],
  "drawing_count": 15,
  "timestamp": "2026-04-06T14:00:00Z"
}
```

| Response | Status | When |
|----------|--------|------|
| `{"message": "Pre-computation queued", "event": "...", "project_id": ...}` | 202 | Valid event, processing queued |
| `{"message": "Duplicate event, already processed"}` | 200 | Same event_id seen before |
| `{"detail": "Invalid signature"}` | 401 | HMAC verification failed |
| `{"detail": "Invalid payload: ..."}` | 422 | JSON parse error |

---

## Quick Test Sequence for Postman

**Step 1:** Health check
```
GET http://54.197.189.113:8003/health
```

**Step 2:** Discover trades for a project
```
GET http://54.197.189.113:8003/api/scope-gap/projects/7276/trades
```

**Step 3:** Run scope gap for one trade
```
POST http://54.197.189.113:8003/api/scope-gap/generate
Body: {"project_id": 7276, "trade": "Electrical"}
```

**Step 4:** Chat about the result
```
POST http://54.197.189.113:8003/api/chat
Body: {"project_id": 7276, "query": "Generate exhibit for electrical"}
```

**Step 5:** Create a highlight
```
POST http://54.197.189.113:8003/api/scope-gap/highlights
Headers: X-User-Id: testuser
Body: {"project_id": 7276, "drawing_name": "E0.03", "x": 100, "y": 200, "width": 300, "height": 40, "label": "Test"}
```

**Step 6:** Get project status
```
GET http://54.197.189.113:8003/api/scope-gap/projects/7276/status
```
