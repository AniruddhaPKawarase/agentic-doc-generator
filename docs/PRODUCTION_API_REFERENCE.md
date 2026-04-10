# Construction Intelligence Agent — Production API Reference

**Base URL:** `https://ai5.ifieldsmart.com/construction`
**Protocol:** HTTPS (TLS 1.2+, Let's Encrypt)
**Server:** Nginx → uvicorn port 8003
**Headers:** `Content-Type: application/json` for all POST requests

---

## 1. Health Check

**`GET /health`**

Verifies the server is alive before making pipeline calls. Check `new_api` to confirm whether the richer byTrade endpoint is active or degraded.

```
GET https://ai5.ifieldsmart.com/construction/health
```

No body. No params.

**Response:**
```json
{
  "status": "ok",
  "redis": "in-memory-only",
  "openai": "configured",
  "new_api": "ok",
  "version": "2.1.0"
}
```

| Field | Values |
|-------|--------|
| `new_api` | `"ok"` — byTrade endpoint active, `"degraded (using fallback)"` — using summaryByTrade, `"disabled"` — USE_NEW_API=false |

---

## 2. Chat — Generate Scope Document

**`POST /api/chat`**

The main chat pipeline. Detects trade from the query, fetches drawing data, generates a scope answer via LLM, creates a downloadable Word document with S3 PDF hyperlinks and traceability table.

```
POST https://ai5.ifieldsmart.com/construction/api/chat
Content-Type: application/json
```

**Request Body:**
```json
{
  "project_id": 7276,
  "query": "generate electrical scope",
  "session_id": null,
  "user_id": null,
  "generate_document": true,
  "set_ids": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `project_id` | int | Yes | — | MongoDB project ID (e.g., 7276, 7298, 7212) |
| `query` | string | Yes | — | Natural-language question (min 3 chars) |
| `session_id` | string | No | null | Pass from previous response to continue conversation |
| `user_id` | string | No | null | Optional user identifier |
| `generate_document` | bool | No | true | Whether to generate a downloadable .docx |
| `set_ids` | list[int] | No | null | Filter to specific drawing sets (e.g., [4720]) |

**Response:**
```json
{
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "project_name": "SINGH RESIDENCE (ID: 7276)",
  "answer": "**Electrical Scope of Work Exhibit**\n\n**1. Smoke and Carbon Monoxide Detection Systems**\nDrawing Number(s): A-12, A-13...",
  "set_ids": null,
  "set_names": [],
  "intent": {
    "trade": "Electrical",
    "csi_divisions": ["26 - Electrical"],
    "document_type": "scope",
    "intent": "generate",
    "keywords": ["electrical", "scope"],
    "confidence": 0.95,
    "raw_query": "generate electrical scope"
  },
  "document": {
    "file_id": "891295d6-b074-4988-afdc-8bef4ef71acd",
    "filename": "scope_Electrical_SINGHRESIDENCE_7276_891295d6.docx",
    "file_path": "s3://agentic-ai-production/construction-intelligence-agent/generated_documents/SINGH_RESIDENCE_ID_7276_7276/Electrical/scope_Electrical_SINGHRESIDENCE_7276_891295d6.docx",
    "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/891295d6-b074-4988-afdc-8bef4ef71acd/download",
    "project_id": 7276,
    "trade": "Electrical",
    "document_type": "scope",
    "size_bytes": 42872
  },
  "token_usage": {
    "input_tokens": 1338,
    "output_tokens": 67,
    "total_tokens": 1405,
    "cost_usd": 0.000361
  },
  "groundedness_score": 0.4,
  "needs_clarification": false,
  "clarification_questions": [],
  "follow_up_questions": [
    "What specific electrical panel specifications are mentioned?",
    "Are there any cross-trade coordination items for Electrical?",
    "Generate a detailed takeoff for Electrical components"
  ],
  "pipeline_ms": 38590,
  "cached": false,
  "token_log": {},
  "source_references": {
    "A-12": {
      "drawing_id": 12345,
      "drawing_name": "A-12",
      "drawing_title": "ELECTRICAL FLOOR PLAN",
      "s3_url": "https://agentic-ai-production.s3.amazonaws.com/ifieldsmart/proj/Drawings/pdf/pdfA12.pdf",
      "pdf_name": "pdfA12",
      "x": 100,
      "y": 200,
      "width": 50,
      "height": 30
    },
    "A-13": {
      "drawing_id": 12346,
      "drawing_name": "A-13",
      "drawing_title": "ELECTRICAL PANEL SCHEDULE",
      "s3_url": "https://agentic-ai-production.s3.amazonaws.com/ifieldsmart/proj/Drawings/pdf/pdfA13.pdf",
      "pdf_name": "pdfA13",
      "x": null,
      "y": null,
      "width": null,
      "height": null
    }
  },
  "api_version": "byTrade",
  "warnings": []
}
```

**Follow-up message (continue conversation):**
```json
{
  "project_id": 7276,
  "query": "Can you also check plumbing?",
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "generate_document": true
}
```

---

## 3. Chat — SSE Streaming

**`POST /api/chat/stream`**

Same as `/api/chat` but streams the LLM response token-by-token via Server-Sent Events. Use for better UX on large responses (first token appears in ~90s instead of waiting 4+ minutes).

```
POST https://ai5.ifieldsmart.com/construction/api/chat/stream
Content-Type: application/json
```

**Request Body:** Same as `/api/chat`.

**Response:** SSE event stream. Final event contains the full ChatResponse JSON.

---

## 4. Document List

**`GET /api/documents/list`**

Lists all generated documents stored in S3. Documents are never deleted. Supports filtering by project and trade.

```
GET https://ai5.ifieldsmart.com/construction/api/documents/list?project_id=7276
GET https://ai5.ifieldsmart.com/construction/api/documents/list?project_id=7276&trade=Concrete
GET https://ai5.ifieldsmart.com/construction/api/documents/list
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `project_id` | int | No | null | Filter by project ID |
| `trade` | string | No | null | Filter by trade name |

**Response:**
```json
{
  "success": true,
  "data": {
    "documents": [
      {
        "file_id": "891295d6",
        "filename": "scope_Concrete_SINGHRESIDENCE_7276_891295d6.docx",
        "s3_key": "construction-intelligence-agent/generated_documents/SINGH_RESIDENCE_ID_7276_7276/Concrete/scope_Concrete_SINGHRESIDENCE_7276_891295d6.docx",
        "project_folder": "SINGH_RESIDENCE_ID_7276_7276",
        "project_id": 7276,
        "trade": "Concrete",
        "size_bytes": 42872,
        "size_kb": 41.9,
        "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/891295d6/download",
        "created_at": "2026-04-10T09:00:00Z",
        "storage": "s3"
      }
    ],
    "total": 6
  }
}
```

---

## 5. Document Download

**`GET /api/documents/{file_id}/download`**

Downloads a generated Word document. Returns a 307 redirect to an S3 presigned URL (1-hour expiry).

```
GET https://ai5.ifieldsmart.com/construction/api/documents/891295d6-b074-4988-afdc-8bef4ef71acd/download
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `file_id` | string (path) | UUID or short ID from document metadata |

**Response:** HTTP 307 redirect to S3 presigned URL. Browser auto-downloads the file.

---

## 6. Document Info

**`GET /api/documents/{file_id}/info`**

Returns metadata about a document without downloading it.

```
GET https://ai5.ifieldsmart.com/construction/api/documents/891295d6-b074-4988-afdc-8bef4ef71acd/info
```

**Response:**
```json
{
  "file_id": "891295d6-b074-4988-afdc-8bef4ef71acd",
  "filename": "scope_Concrete_SINGHRESIDENCE_7276_891295d6.docx",
  "size_bytes": 42872,
  "size_kb": 41.9,
  "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/891295d6/download",
  "storage": "s3",
  "s3_key": "construction-intelligence-agent/generated_documents/SINGH_RESIDENCE_ID_7276_7276/Concrete/scope_Concrete_SINGHRESIDENCE_7276_891295d6.docx"
}
```

---

## 7. Raw API Data

**`GET /api/projects/{project_id}/raw-data`**

Fetches raw drawing records from the MongoDB API for display in the UI. Returns all fields including `s3BucketPath`, `pdfName`, coordinates. Paginated.

```
GET https://ai5.ifieldsmart.com/construction/api/projects/7276/raw-data?trade=Concrete
GET https://ai5.ifieldsmart.com/construction/api/projects/7292/raw-data?trade=Civil&set_id=4720&skip=0&limit=50
```

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `trade` | string | Yes | — | Trade name |
| `set_id` | int | No | null | Optional set ID filter |
| `skip` | int | No | 0 | Pagination offset (min: 0) |
| `limit` | int | No | 500 | Records per page (min: 1, max: 1000) |

**Response:**
```json
{
  "success": true,
  "data": {
    "records": [
      {
        "_id": "69a700bd12179a5f1c8263d5",
        "projectId": 7292,
        "setId": 4720,
        "tradeId": 10,
        "drawingId": 318845,
        "drawingName": "A102",
        "drawingTitle": "ARCHITECTURAL SITE PLAN - NEW VET HOSPITAL",
        "s3BucketPath": "ifieldsmart/acsveterinarianhospital2502202613322528/Drawings/pdf2502202613361561",
        "pdfName": "2502202613395178A102ARCHITECTURALSITEPLANNEWVETHOSPITAL1-1",
        "text": "MATCH EXISTING SIDEWALK. RE; CIVIL",
        "x": 3743,
        "y": 738,
        "width": 144,
        "height": 69,
        "csi_division": ["03 - Concrete", "31 - Earthwork"],
        "trades": ["Concrete", "Civil"]
      }
    ],
    "total": 342,
    "skip": 0,
    "limit": 50,
    "has_more": true
  }
}
```

---

## 8. Session History

**`GET /api/sessions/{session_id}/history`**

Returns the conversation history for a session. Each assistant message includes document metadata (if a document was generated).

```
GET https://ai5.ifieldsmart.com/construction/api/sessions/5f31a620-ab94-402f-aee1-bf8cfb4a2c07/history
```

**Response:**
```json
{
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "project_id": 7276,
  "messages": [
    {
      "role": "user",
      "content": "generate electrical scope",
      "timestamp": "2026-04-10T08:30:00Z",
      "metadata": {}
    },
    {
      "role": "assistant",
      "content": "**Electrical Scope of Work Exhibit**...",
      "timestamp": "2026-04-10T08:31:00Z",
      "metadata": {
        "trade": "Electrical",
        "doc_type": "scope",
        "groundedness_score": 0.4,
        "document": {
          "file_id": "891295d6-b074-4988-afdc-8bef4ef71acd",
          "filename": "scope_Electrical_SINGHRESIDENCE_7276_891295d6.docx",
          "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/891295d6/download",
          "trade": "Electrical",
          "document_type": "scope",
          "size_bytes": 42872,
          "created_at": "2026-04-10T08:31:00Z"
        }
      }
    }
  ],
  "token_summary": {
    "total_input": 1338,
    "total_output": 67,
    "total_tokens": 1405,
    "total_cost_usd": 0.000361,
    "call_count": 1
  }
}
```

---

## 9. Session Token Usage

**`GET /api/sessions/{session_id}/tokens`**

Returns accumulated token usage for a session.

```
GET https://ai5.ifieldsmart.com/construction/api/sessions/5f31a620-ab94-402f-aee1-bf8cfb4a2c07/tokens
```

**Response:**
```json
{
  "session_id": "5f31a620-ab94-402f-aee1-bf8cfb4a2c07",
  "total_input": 1338,
  "total_output": 67,
  "total_tokens": 1405,
  "total_cost_usd": 0.000361,
  "call_count": 1
}
```

---

## 10. Delete Session

**`DELETE /api/sessions/{session_id}`**

Clears a session and its conversation history.

```
DELETE https://ai5.ifieldsmart.com/construction/api/sessions/5f31a620-ab94-402f-aee1-bf8cfb4a2c07
```

**Response:**
```json
{"deleted": true}
```

---

## 11. Project Context

**`GET /api/projects/{project_id}/context`**

Returns available trades and CSI divisions for a project.

```
GET https://ai5.ifieldsmart.com/construction/api/projects/7276/context
```

**Response:**
```json
{
  "project_id": 7276,
  "trades": [],
  "csi_divisions": [],
  "total_text_items": 0,
  "cached": false
}
```

---

## 12. Scope Gap Pipeline — SSE Stream

**`POST /api/scope-gap/stream`**

Runs the full 7-agent scope gap pipeline with real-time SSE progress events.

```
POST https://ai5.ifieldsmart.com/construction/api/scope-gap/stream
Content-Type: application/json
```

**Request Body:**
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
| `trade` | string | Yes | Trade name exactly as returned by trades list |
| `set_ids` | list[int] | No | Filter to specific drawing sets |
| `session_id` | string | No | Continue an existing session |

**SSE Events (in order):**
```
event: data_fetch      → {"records_count": 107, "drawings_count": 15}
event: agent_start     → {"agent": "extraction"}
event: agent_complete  → {"agent": "extraction", "elapsed_ms": 2500}
event: agent_start     → {"agent": "classification"}
event: agent_complete  → {"agent": "classification", "elapsed_ms": 1200}
event: agent_start     → {"agent": "ambiguity"}
event: agent_complete  → {"agent": "ambiguity", "elapsed_ms": 800}
event: agent_start     → {"agent": "gotcha"}
event: agent_complete  → {"agent": "gotcha", "elapsed_ms": 900}
event: completeness    → {"overall_pct": 92.5, "is_complete": true}
event: pipeline_complete → {"items_count": 45, "completeness_pct": 92.5, "attempts": 1}
event: result          → { <full ScopeGapResult JSON> }
```

---

## 13. Scope Gap Pipeline — Synchronous

**`POST /api/scope-gap/generate`**

Same as streaming but returns the full result in one JSON response. Easier for Postman testing.

```
POST https://ai5.ifieldsmart.com/construction/api/scope-gap/generate
Content-Type: application/json
```

**Request Body:** Same as `/api/scope-gap/stream`.

**Response:**
```json
{
  "project_id": 7276,
  "project_name": "SINGH RESIDENCE",
  "trade": "Doors",
  "items": [
    {
      "id": "itm_b0a4fa53",
      "text": "Contractor shall furnish and install interior solid core paint grade wood doors...",
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
      "description": "Scope items reference 'allowance for doors' but do not specify values...",
      "severity": "high",
      "affected_trades": ["Doors", "Finish Carpentry"],
      "recommendation": "Clarify allowance values...",
      "drawing_refs": ["A-24"]
    }
  ],
  "completeness": {
    "drawing_coverage_pct": 66.7,
    "csi_coverage_pct": 100.0,
    "overall_pct": 83.3,
    "is_complete": false,
    "attempt": 3
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
    "total_ms": 71095,
    "attempts": 3,
    "tokens_used": 12808,
    "estimated_cost_usd": 0.025616,
    "records_processed": 3,
    "items_extracted": 6
  }
}
```

---

## 14. Trades List

**`GET /api/scope-gap/projects/{project_id}/trades`**

Returns all available trades for a project with record counts and pipeline status.

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/trades
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/trades?set_id=4730
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `set_id` | int | No | Optional set ID filter |

**Response:**
```json
{
  "project_id": 7276,
  "trades": [
    {"trade": "Concrete", "record_count": 131, "status": "pending", "color": {"hex": "#BCAAA4", "rgb": [188, 170, 164]}},
    {"trade": "Electrical", "record_count": 107, "status": "ready", "color": {"hex": "#F48FB1", "rgb": [244, 143, 177]}},
    {"trade": "Plumbing", "record_count": 154, "status": "pending", "color": {"hex": "#81D4FA", "rgb": [129, 212, 250]}}
  ],
  "total_trades": 15,
  "total_records": 1117
}
```

---

## 15. Drawings List

**`GET /api/scope-gap/projects/{project_id}/drawings`**

Returns drawings categorized by discipline for the sidebar tree.

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/drawings
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/drawings?set_id=4730
```

**Response:**
```json
{
  "project_id": 7276,
  "total_drawings": 25,
  "total_specs": 0,
  "categories": {
    "ARCHITECTURAL": {
      "drawings": [
        {"drawing_name": "A-12", "drawing_title": "", "source_type": "drawing"},
        {"drawing_name": "A-13", "drawing_title": "", "source_type": "drawing"}
      ],
      "specs": []
    }
  }
}
```

---

## 16. Run All Trades

**`POST /api/scope-gap/projects/{project_id}/run-all`**

Triggers the 7-agent pipeline for all trades in parallel. Returns 202 immediately. Poll status (endpoint 17) for progress.

```
POST https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/run-all
Content-Type: application/json
```

**Request Body:**
```json
{
  "force_rerun": false,
  "set_ids": null,
  "trades": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `force_rerun` | bool | No | false | Re-run even if cached results exist |
| `set_ids` | list[int] | No | null | Filter to specific drawing sets |
| `trades` | list[string] | No | null | Run only these trades (null = all) |

**Response (202):**
```json
{
  "accepted": true,
  "project_id": 7276,
  "force_rerun": false,
  "set_ids": null,
  "trades": null,
  "message": "Pipeline triggered for all trades. Poll /status for progress."
}
```

---

## 17. Pipeline Status

**`GET /api/scope-gap/projects/{project_id}/status`**

Returns progress dashboard for all trade pipelines after Run All.

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/status
```

**Response:**
```json
{
  "project_id": 7276,
  "session_id": null,
  "overall_progress": 0,
  "total_items": 0,
  "trades": []
}
```

---

## 18. System Status

**`GET /api/scope-gap/status`**

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/status
```

**Response:**
```json
{
  "status": "ok",
  "uptime_seconds": 155996,
  "redis_connected": false,
  "s3_connected": true
}
```

---

## 19. Pipeline Metrics

**`GET /api/scope-gap/metrics`**

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/metrics
```

**Response:**
```json
{
  "status": "ok",
  "uptime_seconds": 156002,
  "active_jobs": 0,
  "token_usage": {}
}
```

---

## 20. Highlights — Create

**`POST /api/scope-gap/highlights`**

Creates a highlight annotation on a drawing. Requires `X-User-Id` header.

```
POST https://ai5.ifieldsmart.com/construction/api/scope-gap/highlights
Content-Type: application/json
X-User-Id: testuser
```

**Request Body:**
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

**Response (201):**
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
  "created_at": "2026-04-10T07:26:51Z",
  "updated_at": "2026-04-10T07:26:51Z"
}
```

---

## 21. Highlights — List

**`GET /api/scope-gap/highlights`**

```
GET https://ai5.ifieldsmart.com/construction/api/scope-gap/highlights?project_id=7276&drawing_name=E0.03
X-User-Id: testuser
```

**Response:** Array of highlight objects.

---

## 22. Highlights — Update

**`PATCH /api/scope-gap/highlights/{id}`**

```
PATCH https://ai5.ifieldsmart.com/construction/api/scope-gap/highlights/hl_c9c2f7e9f3?project_id=7276&drawing_name=E0.03
Content-Type: application/json
X-User-Id: testuser
```

**Request Body (partial update):**
```json
{
  "label": "Updated Label",
  "critical": true
}
```

---

## 23. Highlights — Delete

**`DELETE /api/scope-gap/highlights/{id}`**

```
DELETE https://ai5.ifieldsmart.com/construction/api/scope-gap/highlights/hl_c9c2f7e9f3?project_id=7276&drawing_name=E0.03
X-User-Id: testuser
```

**Response:**
```json
{"deleted": true}
```

---

## Error Responses

| Scenario | HTTP Code | Response |
|----------|-----------|----------|
| Invalid session ID | 404 | `{"detail": "Session not found"}` |
| Invalid document ID | 404 | `{"detail": "Document not found or expired"}` |
| Missing required field | 422 | `{"detail": [{"msg": "Field required", ...}]}` |
| Invalid skip/limit | 422 | `{"detail": [{"msg": "Input should be >= 0", ...}]}` |
| Server error | 500 | `{"detail": "Internal server error"}` |

---

## Available Test Projects

| ID | Name | Trades | Records | Best For |
|----|------|--------|---------|----------|
| 7276 | Singh Residence | 15 | 1,117 | Quick tests (small project) |
| 7298 | AVE Horsham | 20 | 3,889 | Medium tests |
| 7212 | HSB Potomac | 20 | 38,994 | Large-scale / stress tests |
| 7292 | ACS Veterinary Hospital | — | — | byTradeAndSet with setId 4720 |

---

## Quick Postman Test Sequence

| # | Method | URL |
|---|--------|-----|
| 1 | GET | `https://ai5.ifieldsmart.com/construction/health` |
| 2 | GET | `https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/trades` |
| 3 | GET | `https://ai5.ifieldsmart.com/construction/api/scope-gap/projects/7276/drawings` |
| 4 | POST | `https://ai5.ifieldsmart.com/construction/api/chat` with `{"project_id":7276,"query":"generate concrete scope"}` |
| 5 | GET | `https://ai5.ifieldsmart.com/construction/api/documents/list?project_id=7276` |
| 6 | GET | `https://ai5.ifieldsmart.com/construction/api/documents/{file_id}/download` |
| 7 | GET | `https://ai5.ifieldsmart.com/construction/api/projects/7276/raw-data?trade=Concrete&limit=10` |
| 8 | POST | `https://ai5.ifieldsmart.com/construction/api/scope-gap/generate` with `{"project_id":7276,"trade":"Doors"}` |

---

## Streamlit UI Configuration

Point the Streamlit app at the production API:

```bash
cd scope-gap-ui
API_BASE_URL=https://ai5.ifieldsmart.com/construction streamlit run app.py
```

Or set in `scope-gap-ui/config.py`:
```python
API_BASE_URL = "https://ai5.ifieldsmart.com/construction"
```
