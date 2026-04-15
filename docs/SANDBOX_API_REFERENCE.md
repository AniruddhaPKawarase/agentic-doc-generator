# Construction Intelligence Agent — Sandbox API Reference

**Sandbox VM:** `54.197.189.113`
**Protocol:** HTTP (no SSL, no Nginx)
**Access pattern:** `http://54.197.189.113:{port}`
**Deployed:** S3 Scope Gap Documents + Latency Optimization v4 (2026-04-15)

> For full endpoint documentation (request bodies, response schemas, field tables), see [PRODUCTION_API_REFERENCE.md](./PRODUCTION_API_REFERENCE.md). This document covers sandbox-specific URLs and service topology only. Replace any `https://ai5.ifieldsmart.com/construction` URL with `http://54.197.189.113:8003` for the construction agent, or the appropriate port for other agents.

---

## Active Services

| Port | Agent | Base URL |
|------|-------|----------|
| 8001 | Unified RAG | `http://54.197.189.113:8001` |
| 8002 | SQL Intelligence | `http://54.197.189.113:8002` |
| 8003 | Construction Intelligence | `http://54.197.189.113:8003` |
| 8004 | Ingestion | `http://54.197.189.113:8004` |
| 8005 | Gateway | `http://54.197.189.113:8005` |
| 8006 | Document QA | `http://54.197.189.113:8006` |

---

## Port 8001 — Unified RAG

**`GET http://54.197.189.113:8001/health`**

```json
{
  "status": "healthy",
  "engines": {
    "agentic": {"initialized": true},
    "traditional": {"faiss_loaded": false}
  },
  "fallback_enabled": true
}
```

Note: `faiss_loaded: false` is expected on sandbox — vector index not pre-loaded. Agentic engine is active and `fallback_enabled` means queries will not hard-fail.

---

## Port 8002 — SQL Intelligence

**`GET http://54.197.189.113:8002/health`**

```json
{
  "status": "healthy",
  "database": "connected",
  "environment": "production"
}
```

---

## Port 8003 — Construction Intelligence

This agent is identical to production. All 23 endpoints from [PRODUCTION_API_REFERENCE.md](./PRODUCTION_API_REFERENCE.md) are active.

**`GET http://54.197.189.113:8003/health`**

```json
{
  "status": "ok",
  "redis": "in-memory-only",
  "openai": "configured",
  "new_api": "ok",
  "version": "2.1.0"
}
```

### Endpoint Map (Port 8003)

Replace `https://ai5.ifieldsmart.com/construction` → `http://54.197.189.113:8003`

| # | Method | Path |
|---|--------|------|
| 1 | GET | `/health` |
| 2 | POST | `/api/chat` |
| 3 | POST | `/api/chat/stream` |
| 4 | GET | `/api/documents/list` |
| 5 | GET | `/api/documents/{file_id}/download` |
| 6 | GET | `/api/documents/{file_id}/info` |
| 7 | GET | `/api/projects/{project_id}/raw-data` |
| 8 | GET | `/api/sessions/{session_id}/history` |
| 9 | GET | `/api/sessions/{session_id}/tokens` |
| 10 | DELETE | `/api/sessions/{session_id}` |
| 11 | GET | `/api/projects/{project_id}/context` |
| 12 | POST | `/api/scope-gap/stream` |
| 13 | POST | `/api/scope-gap/generate` |
| 14 | GET | `/api/scope-gap/projects/{project_id}/trades` |
| 15 | GET | `/api/scope-gap/projects/{project_id}/drawings` |
| 16 | POST | `/api/scope-gap/projects/{project_id}/run-all` |
| 17 | GET | `/api/scope-gap/projects/{project_id}/status` |
| 18 | GET | `/api/scope-gap/status` |
| 19 | GET | `/api/scope-gap/metrics` |
| 20 | POST | `/api/scope-gap/highlights` |
| 21 | GET | `/api/scope-gap/highlights` |
| 22 | PATCH | `/api/scope-gap/highlights/{id}` |
| 23 | DELETE | `/api/scope-gap/highlights/{id}` |

### Changes in This Release (2026-04-15)

**POST /api/scope-gap/generate — S3 document persistence**
- `documents` field now returns download URLs (e.g., `https://ai.ifieldsmart.com/construction/api/documents/{file_id}/download`) instead of local paths.
- All 4 formats (DOCX, PDF, CSV, JSON) uploaded to S3 on generation.
- `GET /api/documents/list?project_id=X` now also returns scope gap documents.
- Fix: `documents.json_path` was `null` (quality=None crash) — now generates correctly.

**No breaking changes** — API response shape is identical, only `documents.*_path` values changed from local paths to download URLs.

### Previous Breaking Changes (2026-04-13)

**POST /api/chat**
- `set_ids` is now **required** when `generate_document=true`. Omitting it returns HTTP 422: `"set_ids is required when generate_document is true"`.
- Response includes new `documents: list[GeneratedDocument]` array (one per set_id). The existing `document` field is retained for backward compatibility.
- `source_references` entries now include `text` (string|null) and `annotations` (array) fields.

**GET /api/documents/list**
- `project_id` is now **required**. Omitting it returns HTTP 422.
- New optional `set_name` filter (partial match, case-insensitive).
- Response includes `set_id` and `set_name` per document.

**S3 path format changed**
- Old: `{agent}/generated_documents/{ProjectName}_{ProjectID}/{Trade}/{file}`
- New: `{agent}/generated_documents/{ProjectName}({ProjectID})/{SetName}({SetID})/{Trade}/{file}`
- Both formats are handled by `/api/documents/list`.

**Document overwrite behavior**
- Regenerating a document for the same Project + Set + Trade overwrites the previous S3 file.

> S3 bucket: `agentic-ai-production` — shared with production. Use sandbox-only project IDs or set names to avoid overwriting production documents.

---

## Port 8004 — Ingestion

**`GET http://54.197.189.113:8004/health`**

```json
{
  "status": "ok",
  "pipeline_available": true,
  "running_jobs": 0
}
```

---

## Port 8005 — Gateway

**`GET http://54.197.189.113:8005/health`**

```json
{
  "status": "all_healthy",
  "healthy": 5,
  "total": 5
}
```

The gateway health check polls all 5 downstream agents. A `healthy: 5 / total: 5` response confirms the full stack is up.

---

## Port 8006 — Document QA

**`GET http://54.197.189.113:8006/health`**

```json
{
  "status": "ok",
  "model": "gpt-4o-mini",
  "embedding_model": "text-embedding-3-small"
}
```

---

## Latency Optimization v4 (Deployed 2026-04-12)

The sandbox is running the Latency Optimization v4 build. Key changes vs previous production build:

- See [superpowers/specs/2026-04-12-latency-optimization-design.md](./superpowers/specs/2026-04-12-latency-optimization-design.md) for design details
- See [superpowers/plans/2026-04-12-latency-optimization.md](./superpowers/plans/2026-04-12-latency-optimization.md) for implementation plan

Production is still on the prior build. Sandbox is the pre-prod gate for this release.

---

## Quick Sandbox Test Sequence

Run in order to verify the full stack is healthy before promoting to production.

| # | Method | URL | Expected |
|---|--------|-----|----------|
| 1 | GET | `http://54.197.189.113:8005/health` | `all_healthy`, `healthy: 5` |
| 2 | GET | `http://54.197.189.113:8003/health` | `status: ok`, `new_api: ok` |
| 3 | GET | `http://54.197.189.113:8001/health` | `status: healthy` |
| 4 | GET | `http://54.197.189.113:8002/health` | `database: connected` |
| 5 | GET | `http://54.197.189.113:8004/health` | `pipeline_available: true` |
| 6 | GET | `http://54.197.189.113:8006/health` | `status: ok` |
| 7 | GET | `http://54.197.189.113:8003/api/scope-gap/projects/7276/trades` | trades list with record counts |
| 8 | POST | `http://54.197.189.113:8003/api/chat` | body: `{"project_id":7276,"query":"generate concrete scope","generate_document":true,"set_ids":[4720]}` |
| 9 | POST | `http://54.197.189.113:8003/api/scope-gap/generate` | body: `{"project_id":7276,"trade":"Doors"}` |

---

## Sandbox vs Production Differences

| Aspect | Sandbox (54.197.189.113) | Production (ai5.ifieldsmart.com) |
|--------|--------------------------|----------------------------------|
| Protocol | HTTP | HTTPS (TLS 1.2+) |
| Routing | Direct port access | Nginx reverse proxy → port 8003 |
| Base URL | `http://54.197.189.113:{port}` | `https://ai5.ifieldsmart.com/construction` |
| Build | 2026-04-15 release (S3 scope gap docs, set_ids required, documents array) | Same — both on 2026-04-15 release |
| SSL cert | None | Let's Encrypt |
| Domain | None | ai5.ifieldsmart.com |

---

## Streamlit UI — Point at Sandbox

```bash
cd scope-gap-ui
API_BASE_URL=http://54.197.189.113:8003 streamlit run app.py
```

Or in `scope-gap-ui/config.py`:

```python
API_BASE_URL = "http://54.197.189.113:8003"
```
