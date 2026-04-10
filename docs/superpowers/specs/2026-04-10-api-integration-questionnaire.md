# Design Questionnaire: New API Integration (`byTradeAndSet`)

**Date:** 2026-04-10
**Scope:** Core API migration, source references, document enrichment, UI raw data display
**Agent:** Construction Intelligence Agent
**Status:** AWAITING USER ANSWERS

---

## Context

The construction-intelligence-agent currently uses `summaryByTrade` and `summaryByTradeAndSet` endpoints. We are migrating to the richer `byTradeAndSet` endpoint which returns additional fields: `drawingId`, `s3BucketPath`, `pdfName`, `x`, `y`, `width`, `height`. These fields enable source traceability, PDF hyperlinks, and future annotation/highlighting features.

**What already exists:**
- SQL project name lookup (`services/sql_service.py`) — fully implemented
- Project name in both document generators — fully implemented
- `by_trade_and_set_path` config — already defined in `config.py`
- Scope pipeline partial S3 field usage — `data_fetcher.py` already extracts `s3BucketPath`/`pdfName`

**What's new:**
- Switch main agent from `summaryByTrade` → `byTrade`/`byTradeAndSet`
- Propagate new fields through pipeline for source references
- Clickable S3 PDF hyperlinks in Word documents
- Raw API response display in Streamlit UI

---

## 1. Scaling

### Q1.1 — API Endpoint Migration Strategy

Should we replace all API calls or run dual endpoints?

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **(A)** Replace all | Switch `summaryByTrade` → `byTrade` and `summaryByTradeAndSet` → `byTradeAndSet` globally | Simpler code, single data path, richer data everywhere | Breaking change if new endpoint is unavailable |
| **(B)** Add alongside | Keep `summaryByTrade` as fallback, prefer `byTradeAndSet` when possible | Zero-downtime migration, rollback capability | Two code paths to maintain, increased complexity |
| **(C)** Replace with fallback | Use `byTrade`/`byTradeAndSet` as primary, auto-fallback to `summaryByTrade` on HTTP 404/500 | Best of both — richer data + resilience | Slight latency on fallback, need retry logic |

**Recommendation: (C)** — Replace with fallback. The `byTrade`/`byTradeAndSet` endpoints return a superset of fields. If they fail, we gracefully degrade to `summaryByTrade` which still returns enough data for core functionality (just without S3 paths and coordinates). The fallback is a one-time check per request, not a persistent state.

**ANSWER**: (C)** — Replace with fallback. The `byTrade`/`byTradeAndSet` endpoints return a superset of fields. If they fail, we gracefully degrade to `summaryByTrade` which still returns enough data for core functionality (just without S3 paths and coordinates). The fallback is a one-time check per request, not a persistent state.


### Q1.2 — Data Volume Impact

The `byTradeAndSet` response includes ~7 additional fields per record. For a 11,360-record Electrical trade, that's ~80K extra field values in memory.

| Option | Description |
|--------|-------------|
| **(A)** Pass all fields through | Keep all fields in memory, let downstream components pick what they need |
| **(B)** Extract only needed fields | At API client level, extract only fields used by context_builder + document generators |
| **(C)** Two-tier extraction | Pass core fields to context_builder (text, drawingName, csi_division), store full records separately for document generator source references |

**Recommendation: (C)** — Two-tier extraction. Context builder needs lightweight records for LLM context (text, drawingName, drawingTitle, csi_division). Document generators and UI need the full record set for source references. Storing coordinates (x, y, width, height) in context would waste LLM tokens. A separate `source_index` dict keyed by `drawingName` → `{drawingId, s3BucketPath, pdfName, x, y, width, height}` keeps memory lean and lookup fast.

**ANSWER**: (C)** — Two-tier extraction. Context builder needs lightweight records for LLM context (text, drawingName, drawingTitle, csi_division). Document generators and UI need the full record set for source references. Storing coordinates (x, y, width, height) in context would waste LLM tokens. A separate `source_index` dict keyed by `drawingName` → `{drawingId, s3BucketPath, pdfName, x, y, width, height}` keeps memory lean and lookup fast.



### Q1.3 — Concurrent Request Scaling

Current parallel fetch concurrency is 30. The new endpoint may have different rate limits.

| Option | Description |
|--------|-------------|
| **(A)** Keep concurrency at 30 | Assume new endpoint has same rate limits |
| **(B)** Start conservative at 15, auto-tune | Begin at 15, increase if no 429s observed |
| **(C)** Add per-endpoint concurrency config | Separate `BY_TRADE_CONCURRENCY` and `SUMMARY_CONCURRENCY` settings |

**Recommendation: (A)** — Keep at 30. The new endpoint is on the same server (`mongo.ifieldsmart.com`). If rate limiting differs, the existing exponential backoff retry (3 attempts) already handles 429/503 gracefully. We can tune later if needed without code changes (it's an env var).

**ANSWER**: (A)** — Keep at 30. The new endpoint is on the same server (`mongo.ifieldsmart.com`). If rate limiting differs, the existing exponential backoff retry (3 attempts) already handles 429/503 gracefully. We can tune later if needed without code changes (it's an env var).


---

## 2. Optimization

### Q2.1 — Source Index Construction

How should we build the source reference mapping from API data?

| Option | Description |
|--------|-------------|
| **(A)** Build during pagination | Extract source fields as records stream in during parallel fetch |
| **(B)** Build after dedup | Build source index after all records are fetched and deduplicated |
| **(C)** Lazy build | Build source index only when document generation is triggered |

**Recommendation: (B)** — Build after dedup. Building during pagination risks duplicate entries and wasted work. Building after dedup means we process the final clean dataset once. Cost is negligible (~10ms for 11K records) and ensures consistency.

**ANSWER**: (B)** — Build after dedup. Building during pagination risks duplicate entries and wasted work. Building after dedup means we process the final clean dataset once. Cost is negligible (~10ms for 11K records) and ensures consistency.


### Q2.2 — S3 URL Construction

The S3 PDF URL format needs to be constructed from `s3BucketPath` + `pdfName`.

| Option | Description |
|--------|-------------|
| **(A)** Direct S3 URL | `https://{bucket}.s3.amazonaws.com/{s3BucketPath}/{pdfName}.pdf` |
| **(B)** Presigned URL | Generate time-limited presigned S3 URLs (e.g., 24h expiry) |
| **(C)** Application proxy URL | `https://ai5.ifieldsmart.com/construction/api/drawings/{drawingId}/pdf` — proxy through our API |
| **(D)** Use existing iFieldSmart viewer URL | Construct URL using the existing iFieldSmart web application's PDF viewer (if one exists) |

**Recommendation: (D) or (A)** — This depends on whether iFieldSmart has an existing PDF viewer that accepts these parameters. If yes, use it (users already know it). If no, use (A) for simplicity — direct S3 URLs work if the bucket has public read or the user's session has access. Presigned URLs (B) add complexity and expire. Proxy (C) is overhead unless access control is needed.

**Question for user:** Does iFieldSmart have an existing web-based PDF viewer URL pattern we should use? Or should we construct direct S3 bucket URLs?

**ANSWER**: (D) or (A)** — This depends on whether iFieldSmart has an existing PDF viewer that accepts these parameters. If yes, use it (users already know it). If no, use (A) for simplicity — direct S3 URLs work if the bucket has public read or the user's session has access. Presigned URLs (B) add complexity and expire. Proxy (C) is overhead unless access control is needed.  iFieldSmart have an existing web-based PDF viewer URL pattern but we need to construct direct S3 bucket URLs


### Q2.3 — Context Token Budget

Adding source reference metadata to the LLM context would consume tokens. Should source data go to LLM?

| Option | Description |
|--------|-------------|
| **(A)** No source data in LLM context | Source references only go to document generators, not the LLM prompt |
| **(B)** Minimal source data in LLM context | Include only `drawingName → drawingId` mapping so LLM can reference drawings by ID |
| **(C)** Full source data in LLM context | Include all S3 paths and coordinates in LLM prompt |

**Recommendation: (A)** — No source data in LLM context. The LLM's job is to analyze text content and generate scope documents. It doesn't need S3 paths, coordinates, or PDF names — those are rendering concerns. Adding them would waste ~15K tokens on a large project for zero analytical value. Source references are injected post-LLM by the document generators.

**ANSWER**: (A)** — No source data in LLM context. The LLM's job is to analyze text content and generate scope documents. It doesn't need S3 paths, coordinates, or PDF names — those are rendering concerns. Adding them would waste ~15K tokens on a large project for zero analytical value. Source references are injected post-LLM by the document generators.


---

## 3. Performance Metrics

### Q3.1 — Latency Tracking for New Endpoint

Should we add separate timing metrics for the new API endpoint?

| Option | Description |
|--------|-------------|
| **(A)** Reuse existing metrics | Same `fetch_duration_ms` metric regardless of endpoint |
| **(B)** Add endpoint-specific metrics | Track `byTrade_fetch_ms` vs `summaryByTrade_fetch_ms` separately |
| **(C)** Add comparative logging | Log both endpoints' performance during migration period, remove after stabilization |

**Recommendation: (C)** — Comparative logging during migration. We need to validate that `byTradeAndSet` performs comparably to `summaryByTradeAndSet`. After 2 weeks of stable operation, collapse to a single metric. This is zero-code-change removal (just log level adjustment).

**ANSWER**: (C)** — Comparative logging during migration. We need to validate that `byTradeAndSet` performs comparably to `summaryByTradeAndSet`. After 2 weeks of stable operation, collapse to a single metric. This is zero-code-change removal (just log level adjustment).


### Q3.2 — Source Index Build Time Tracking

Should we track source index construction as a pipeline metric?

| Option | Description |
|--------|-------------|
| **(A)** No tracking | It's fast (~10ms), not worth instrumenting |
| **(B)** Add to token_log | Include `source_index_build_ms` in the existing token_log dict |

**Recommendation: (B)** — Add to token_log. It's one line of code and gives visibility. If it ever regresses (e.g., 50K-record projects), we'll know immediately.

**ANSWER**: (B)** — Add to token_log. It's one line of code and gives visibility. If it ever regresses (e.g., 50K-record projects), we'll know immediately.


### Q3.3 — Document Generation Time Impact

Adding S3 hyperlinks to Word documents may increase generation time.

| Option | Description |
|--------|-------------|
| **(A)** No concern | Hyperlinks are cheap in python-docx, negligible impact |
| **(B)** Benchmark and cap | Set a 5s timeout on document generation, log if exceeded |

**Recommendation: (A)** — No concern. python-docx hyperlinks are XML attributes, not I/O operations. Even 500 hyperlinks add <50ms. The existing `generate_sync` timing already captures this.

**ANSWER**: (A)** — No concern. python-docx hyperlinks are XML attributes, not I/O operations. Even 500 hyperlinks add <50ms. The existing `generate_sync` timing already captures this.


---

## 4. Request Handling

### Q4.1 — ChatRequest Schema Changes

How should the request schema evolve?

| Option | Description |
|--------|-------------|
| **(A)** No request changes | The richer data is automatic — same request, richer response |
| **(B)** Add `include_source_references: bool = True` | Let callers opt out of source references in response |
| **(C)** Add `preferred_api_version: str = "v2"` | Let callers explicitly choose old vs new API |

**Recommendation: (A)** — No request changes. The richer data is a backend improvement, transparent to callers. Source references are always useful. Adding opt-out flags is YAGNI — if someone doesn't want them, they ignore them in the response. Backward compatibility is maintained because new response fields have defaults.

**ANSWER**: (A)** — No request changes. The richer data is a backend improvement, transparent to callers. Source references are always useful. Adding opt-out flags is YAGNI — if someone doesn't want them, they ignore them in the response. Backward compatibility is maintained because new response fields have defaults.

### Q4.2 — ChatResponse Schema Changes

What new fields should appear in the response?

| Option | Description |
|--------|-------------|
| **(A)** Add `source_references` dict | `{drawingName: {drawingId, s3Url, pdfName}}` — flat lookup |
| **(B)** Add `raw_api_data` list | Full raw API records for UI display |
| **(C)** Both (A) and (B) | Source references for documents, raw data for UI |
| **(D)** Add `source_references` + separate `/api/raw-data` endpoint for raw display | Keep response lean, UI fetches raw data separately |

**Recommendation: (D)** — Source references in ChatResponse + separate raw data endpoint. The raw API data for 11K records would bloat every ChatResponse by ~5MB. Instead: (1) add a compact `source_references` dict to ChatResponse for document hyperlinks, (2) create `GET /api/projects/{id}/raw-data?trade={trade}&setId={setId}` for the UI to fetch raw data on demand. This keeps the chat response fast and the UI can lazy-load raw data.

**Question for user:** Is the raw API data display meant to show ALL records (potentially 11K+) or just the records relevant to the current query/drawing?

**ANSWER**: (D)** — Source references in ChatResponse + separate raw data endpoint. The raw API data for 11K records would bloat every ChatResponse by ~5MB. Instead: (1) add a compact `source_references` dict to ChatResponse for document hyperlinks, (2) create `GET /api/projects/{id}/raw-data?trade={trade}&setId={setId}` for the UI to fetch raw data on demand. This keeps the chat response fast and the UI can lazy-load raw data.  the raw API data display meant to show ALL records respective to trade if user generated the exhibit for single trade. If user generated exhibit for all trade then it should display ALL records (potentially 11K+) of all trades for that respective project.


### Q4.3 — Error Handling for Missing Source Fields

What if the new API returns records without `s3BucketPath` or `pdfName`?

| Option | Description |
|--------|-------------|
| **(A)** Skip hyperlink for that drawing | No link = no click, but content still appears |
| **(B)** Use fallback URL pattern | Construct a search URL like `ifieldsmart.com/search?drawing={drawingName}` |
| **(C)** Log warning and skip | Same as (A) but with structured warning log |

**Recommendation: (C)** — Log warning and skip. Missing source fields shouldn't break document generation. Log a structured warning (`"drawing_name": "A102", "missing_field": "s3BucketPath"`) for ops visibility. The drawing name still appears in the document, just without a hyperlink.

**ANSWER**: (C)** — Log warning and skip. Missing source fields shouldn't break document generation. Log a structured warning (`"drawing_name": "A102", "missing_field": "s3BucketPath"`) for ops visibility. The drawing name still appears in the document, just without a hyperlink.


---

## 5. Vulnerability

### Q5.1 — S3 Path Injection

The `s3BucketPath` and `pdfName` come from an external API. Could they contain malicious paths?

| Option | Description |
|--------|-------------|
| **(A)** Trust the API | iFieldSmart is an internal/trusted system, no validation needed |
| **(B)** Sanitize paths | Strip `../`, validate URL-safe chars, reject paths with suspicious patterns |
| **(C)** Allowlist bucket prefix | Only accept paths starting with expected prefixes (e.g., `ifieldsmart/`) |

**Recommendation: (B) + (C)** — Sanitize AND allowlist. Even trusted APIs can have bugs. Validate: (1) no `../` path traversal, (2) path starts with expected prefix, (3) URL-encode special chars. This is 10 lines of code and prevents path injection if the API is ever compromised.

**ANSWER**: (B) + (C)** — Sanitize AND allowlist. Even trusted APIs can have bugs. Validate: (1) no `../` path traversal, (2) path starts with expected prefix, (3) URL-encode special chars. This is 10 lines of code and prevents path injection if the API is ever compromised.


### Q5.2 — Raw API Data Exposure

Displaying raw API data in the UI could expose internal field names, IDs, or paths.

| Option | Description |
|--------|-------------|
| **(A)** Display all fields | Trust that UI users are internal/authorized |
| **(B)** Filter sensitive fields | Remove `_id`, internal IDs, S3 paths from UI display |
| **(C)** Display all but mask S3 paths | Show everything except full S3 bucket paths (show only PDF name) |

**Recommendation: (A)** — Display all fields. This is an internal tool for construction professionals. The raw data display is specifically requested for transparency. The UI is already behind authentication (or will be in Phase 10). No PII is in these records — it's drawing metadata.

**ANSWER**: (A)** — Display all fields. This is an internal tool for construction professionals. The raw data display is specifically requested for transparency. The UI is already behind authentication (or will be in Phase 10). No PII is in these records — it's drawing metadata.


### Q5.3 — SQL Injection via Project ID

Project IDs flow from user input to SQL queries.

| Current Status | Assessment |
|-------|-------------|
| `sql_service.py` uses parameterized queries (`WHERE projectid = ?`) | **SAFE** — already protected |
| `api_client.py` passes project_id as URL query parameter | **SAFE** — httpx URL-encodes parameters |

**Recommendation:** No changes needed. Both SQL and API paths are already parameterized. Just confirm during code review.

**ANSWER**: No changes needed. Both SQL and API paths are already parameterized. Just confirm during code review.


---

## 6. SDLC Parameters

### Q6.1 — Testing Strategy

What test coverage is needed for the new integration?

| Layer | Tests Needed |
|-------|-------------|
| **Unit** | Source index builder, S3 URL constructor, path sanitizer, field extraction |
| **Integration** | API client with new endpoint (mock + live), document generator with hyperlinks |
| **E2E** | Full pipeline: request → new API → source references → document with links → download |
| **Regression** | All existing tests must pass unchanged (backward compatibility) |

**Recommendation:** Target **90% coverage** on new code. Create a test fixture with sample `byTradeAndSet` response data. Mock the API for unit tests, use a live test project (7292, Civil, setId 4720) for integration tests.

**ANSWER**: Target **90% coverage** on new code. Create a test fixture with sample `byTradeAndSet` response data. Mock the API for unit tests, use a live test project (7292, Civil, setId 4720) for integration tests.


### Q6.2 — Feature Flagging

Should the new API integration be behind a feature flag?

| Option | Description |
|--------|-------------|
| **(A)** No flag | Deploy directly, use fallback mechanism for safety |
| **(B)** Env var flag | `USE_NEW_API=true/false` in `.env` |
| **(C)** Per-request flag | `ChatRequest.use_new_api: bool = True` |

**Recommendation: (B)** — Env var flag. Simple, operator-controlled, no code change to toggle. Default `true` for new deployments, `false` for cautious rollout. Remove the flag after 2 weeks of stable operation. This combined with Q1.1's fallback mechanism gives double safety.

**ANSWER**: (B)** — Env var flag. Simple, operator-controlled, no code change to toggle. Default `true` for new deployments, `false` for cautious rollout. Remove the flag after 2 weeks of stable operation. This combined with Q1.1's fallback mechanism gives double safety.


### Q6.3 — Migration Rollback Plan

How do we roll back if the new API causes issues?

| Step | Action |
|------|--------|
| 1 | Set `USE_NEW_API=false` in `.env` |
| 2 | Restart service (`systemctl restart construction-agent`) |
| 3 | Agent reverts to `summaryByTrade`/`summaryByTradeAndSet` endpoints |
| 4 | Source references become empty (documents generate without hyperlinks) |
| 5 | All other functionality unchanged |

**Recommendation:** This is the rollback plan. Document it in the deployment runbook. Total rollback time: <30 seconds.

**ANSWER**: This is the rollback plan. Document it in the deployment runbook. Total rollback time: <30 seconds.


---

## 7. Compliance

### Q7.1 — Data Retention for Source References

Source references link to S3 PDFs. Do we need to retain these links?

| Option | Description |
|--------|-------------|
| **(A)** No retention concern | Links are in generated documents which are already stored in S3 |
| **(B)** Log source references | Store source reference mappings in a separate audit log |

**Recommendation: (A)** — No additional retention. Generated documents (which contain the hyperlinks) are already stored in S3 under `agentic-ai-production`. The S3 bucket has versioning. If audit is needed, the document itself is the evidence.

**ANSWER**: (A)** — No additional retention. Generated documents (which contain the hyperlinks) are already stored in S3 under `agentic-ai-production`. The S3 bucket has versioning. If audit is needed, the document itself is the evidence.


### Q7.2 — Data Accuracy Traceability

The new source references create an audit trail from scope item → drawing → PDF location.

| Option | Description |
|--------|-------------|
| **(A)** Implicit traceability | Document contains drawing names with hyperlinks — traceable by opening the link |
| **(B)** Explicit traceability table | Add a "Source Reference Table" appendix to each document mapping scope items → drawing → page → coordinates |

**Recommendation: (B)** — Explicit traceability table. Construction documents often require source traceability for legal/compliance purposes. A table at the end of the document listing `Drawing Name | Drawing Title | PDF Link | Page Coordinates` adds significant professional value at minimal cost. This leverages the `x, y, width, height` fields even before a PDF highlighting feature is built.

**Question for user:** Should the traceability table be in every document, or only in "exhibit" type documents?

**ANSWER**: (B)** — Explicit traceability table. Construction documents often require source traceability for legal/compliance purposes. A table at the end of the document listing `Drawing Name | Drawing Title | PDF Link | Page Coordinates` adds significant professional value at minimal cost. This leverages the `x, y, width, height` fields even before a PDF highlighting feature is built. The traceability table should be in every document.

---

## 8. Disaster Recovery & Backup

### Q8.1 — API Endpoint Availability

What if the new `byTradeAndSet` endpoint goes down?

| Current Mitigation | Assessment |
|-------|-------------|
| Fallback to `summaryByTrade` (Q1.1 option C) | Covers endpoint unavailability |
| Exponential backoff retry (3 attempts) | Covers transient failures |
| L1/L2 cache (5-min TTL on API data) | Covers repeated requests during outage |

**Recommendation:** The fallback mechanism (Q1.1 option C) IS the DR plan for the API layer. No additional infrastructure needed. Add a health check that tests the new endpoint: `GET /health` should report `new_api: "ok"` or `new_api: "degraded (using fallback)"`.

**ANSWER**: The fallback mechanism (Q1.1 option C) IS the DR plan for the API layer. No additional infrastructure needed. Add a health check that tests the new endpoint: `GET /health` should report `new_api: "ok"` or `new_api: "degraded (using fallback)"`.

### Q8.2 — Source Reference Data Loss

What if source reference data is lost mid-pipeline?

| Scenario | Impact | Mitigation |
|----------|--------|------------|
| API returns records without source fields | Documents generated without hyperlinks | Graceful degradation (Q4.3) |
| Source index build fails | Documents generated without hyperlinks | Try/catch around source index build, log error, continue pipeline |
| S3 PDF deleted after document generated | Broken hyperlinks in old documents | Not our concern — S3 lifecycle is managed separately |

**Recommendation:** All three scenarios are already handled by graceful degradation. Source references are an enhancement, not a requirement. The pipeline never fails due to missing source data — it just generates documents without hyperlinks.

**ANSWER**: All three scenarios are already handled by graceful degradation. Source references are an enhancement, not a requirement. The pipeline never fails due to missing source data — it just generates documents without hyperlinks.


---

## 9. Support & Helpdesk Framework

### Q9.1 — Diagnostic Logging for New Fields

What logging should support teams have access to?

| Log Entry | Purpose | Level |
|-----------|---------|-------|
| `"api_endpoint_used": "byTradeAndSet"` | Which endpoint was actually called | INFO |
| `"source_index_records": 342` | How many drawings have source references | INFO |
| `"source_index_build_ms": 8` | Source index performance | DEBUG |
| `"hyperlinks_added": 28` | How many clickable links in generated document | INFO |
| `"fallback_triggered": true` | Whether the agent fell back to old API | WARN |
| `"missing_source_fields": ["A102", "A103"]` | Drawings without S3 path/PDF name | WARN |

**Recommendation:** Add all of the above. These are structured log entries (JSON format), cost nothing at runtime, and give support teams immediate visibility into the new feature's health.

**ANSWER**: Add all of the above. These are structured log entries (JSON format), cost nothing at runtime, and give support teams immediate visibility into the new feature's health.


### Q9.2 — User-Facing Error Messages

If source references fail, what does the user see?

| Option | Description |
|--------|-------------|
| **(A)** Silent degradation | Document generates without links, no user notification |
| **(B)** Info banner | "Note: Source PDF links unavailable for some drawings" in the response |
| **(C)** Warning in document footer | "Some source references could not be resolved" at document end |

**Recommendation: (B)** — Info banner in the ChatResponse. Users should know if they're getting a degraded result. Add an optional `warnings: list[str]` field to ChatResponse. The UI can display these as non-blocking yellow banners.

**ANSWER**: (B)** — Info banner in the ChatResponse. Users should know if they're getting a degraded result. Add an optional `warnings: list[str]` field to ChatResponse. The UI can display these as non-blocking yellow banners. But this issue needs to solved any how, use reverse engineering bacckpropogation whatever methods which are useful to solve this issue.

---

## 10. System Maintenance

### Q10.1 — Configuration Management

How many new env vars are needed?

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_NEW_API` | `true` | Feature flag for new endpoint (remove after stabilization) |
| `S3_PDF_URL_PATTERN` | `https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf` | Configurable URL pattern for PDF links |
| `SOURCE_REF_ENABLED` | `true` | Enable/disable source reference generation |

**Recommendation:** 3 new env vars. All have sensible defaults. `USE_NEW_API` is temporary (remove after 2 weeks). `S3_PDF_URL_PATTERN` is essential — if iFieldSmart changes their S3 structure, we update the pattern without code changes. `SOURCE_REF_ENABLED` is a kill switch for source references if they cause issues.

**ANSWER**: 3 new env vars. All have sensible defaults. `USE_NEW_API` is temporary (remove after 2 weeks). `S3_PDF_URL_PATTERN` is essential — if iFieldSmart changes their S3 structure, we update the pattern without code changes. `SOURCE_REF_ENABLED` is a kill switch for source references if they cause issues.


### Q10.2 — Dependency Changes

Are new Python packages needed?

| Assessment | Result |
|-------|-------------|
| New API endpoint | No new deps — uses existing `httpx` |
| S3 URL construction | No new deps — string formatting |
| Word hyperlinks | No new deps — `python-docx` already supports hyperlinks |
| Path sanitization | No new deps — stdlib `re` + `urllib.parse` |
| Raw data UI display | No new deps — Streamlit already supports `st.json()` and `st.dataframe()` |

**Recommendation:** Zero new dependencies. This is a pure integration feature using existing libraries.

**ANSWER**: Zero new dependencies. This is a pure integration feature using existing libraries.


---

## 11. Network & Security Requirements

### Q11.1 — Network Topology

The new API endpoint is on the same server (`mongo.ifieldsmart.com`).

| Assessment | Result |
|-------|-------------|
| DNS resolution | Same as current — no change |
| Firewall rules | Same port (443/HTTPS) — no change |
| SSL/TLS | Same certificate — no change |
| Rate limiting | Same server, may share rate limits with current endpoints |

**Recommendation:** No network changes needed. The new endpoint is a sibling route on the same server. Confirm with the API team that `byTradeAndSet` doesn't have a lower rate limit than `summaryByTradeAndSet`.

**ANSWER**: No network changes needed. The new endpoint is a sibling route on the same server. Confirm with the API team that `byTradeAndSet` doesn't have a lower rate limit than `summaryByTradeAndSet`.


### Q11.2 — S3 PDF Access Control

Who can access the S3 PDFs linked in documents?

| Option | Description |
|--------|-------------|
| **(A)** Public bucket | PDFs are publicly readable — direct URLs work for anyone |
| **(B)** IAM-authenticated | Need AWS credentials to access — presigned URLs required |
| **(C)** Application-gated | Access through iFieldSmart app only — use app URLs, not S3 URLs |

**Question for user:** What is the current access model for the S3 bucket referenced in `s3BucketPath`? Is `ifieldsmart/acsveterinarianhospital2502202613322528/Drawings/...` a public bucket or does it require authentication?

**Recommendation:** This determines whether we use direct S3 URLs, presigned URLs, or application proxy URLs. Critical decision.

**ANSWER**: For testing phase keep it allow for all but once we will set it in production then keep it authenticated or application gated.

---

## 12. Resource Management: Efficiency through Automation

### Q12.1 — Cache Invalidation for New Endpoint

Should the cache strategy change?

| Current | New |
|---------|-----|
| Cache key includes endpoint path | Cache key will include `byTrade` or `byTradeAndSet` path |
| 5-min TTL on API data | Same TTL appropriate for new endpoint |
| Full response cached 1 hour | Full response still cacheable (source refs are deterministic) |

**Recommendation:** No cache strategy changes. The existing semantic query normalization already produces unique keys per endpoint+trade+project combination. New fields in the response are cached automatically. The 5-min API data TTL is appropriate — drawing data doesn't change frequently.

**ANSWER**: No cache strategy changes. The existing semantic query normalization already produces unique keys per endpoint+trade+project combination. New fields in the response are cached automatically. The 5-min API data TTL is appropriate — drawing data doesn't change frequently.


### Q12.2 — Automated Source Index Cleanup

Should source indexes be cleaned up after document generation?

| Option | Description |
|--------|-------------|
| **(A)** Garbage collect with session | Source index lives in session, cleaned with session TTL (24h) |
| **(B)** Immediate cleanup | Delete source index after document is generated |
| **(C)** Keep indefinitely | Source index is small, keep in L1 cache |

**Recommendation: (A)** — Garbage collect with session. The source index is per-request data, roughly 50-200KB for large projects. Tying it to session TTL means it's available for follow-up questions in the same session but automatically cleaned after 24h.

**ANSWER**: (A)** — Garbage collect with session. The source index is per-request data, roughly 50-200KB for large projects. Tying it to session TTL means it's available for follow-up questions in the same session but automatically cleaned after 24h.


### Q12.3 — Parallel Processing Optimization

Can source index build and document generation happen in parallel?

| Current Pipeline | Proposed |
|---------|-----|
| Fetch → Context → LLM → Document (sequential) | Fetch → [Context + Source Index] (parallel) → LLM → Document (uses source index) |

**Recommendation:** Yes — build the source index in parallel with context building during Phase 2. Both read from the same deduplicated record set. This adds zero latency since source index build (~10ms) runs alongside context building (~200ms).

**ANSWER**: Yes — build the source index in parallel with context building during Phase 2. Both read from the same deduplicated record set. This adds zero latency since source index build (~10ms) runs alongside context building (~200ms).


---

## 13. API Contract & Versioning

### Q13.1 — API Response Versioning

Should the ChatResponse indicate which API version was used?

| Option | Description |
|--------|-------------|
| **(A)** No version indicator | Transparent to callers |
| **(B)** Add `api_version` field | `"api_version": "byTradeAndSet"` or `"summaryByTrade"` in response |

**Recommendation: (B)** — Add `api_version` to ChatResponse. During migration, this tells the UI and ops team which endpoint served a particular response. Useful for debugging and A/B comparison.

**ANSWER**: B)** — Add `api_version` to ChatResponse. During migration, this tells the UI and ops team which endpoint served a particular response. Useful for debugging and A/B comparison.


### Q13.2 — Backward Compatibility Guarantee

What backward compatibility must be maintained?

| Guarantee | Enforcement |
|-----------|-------------|
| Existing `ChatRequest` fields work unchanged | All new fields have defaults |
| Existing `ChatResponse` fields remain | New fields are additive only |
| Documents without source references still generate | Source references are optional enhancement |
| All existing tests pass | Regression test suite run before merge |
| Streamlit UI works without changes | New UI features are additive (new tab/panel for raw data) |

**Recommendation:** Strict backward compatibility. Zero breaking changes to request/response schemas. All new fields are optional with defaults. Existing tests are the compatibility gate.

**ANSWER**: Strict backward compatibility. Zero breaking changes to request/response schemas. All new fields are optional with defaults. Existing tests are the compatibility gate.

---

## 14. Observability & Monitoring

### Q14.1 — Alerting on Fallback

Should we alert when the agent falls back to the old API?

| Option | Description |
|--------|-------------|
| **(A)** Log only | WARN-level log, no alert |
| **(B)** Alert after N fallbacks | If >5 fallbacks in 10 minutes, alert ops |
| **(C)** Alert immediately | Every fallback triggers an alert |

**Recommendation: (A)** for now — Log only. The fallback is designed to be seamless. Alerting on every fallback during initial rollout would create noise. After stabilization, upgrade to (B) to catch API degradation patterns.

**ANSWER**: **(C)** Alert immediately | Every fallback triggers an alert | Should disply on streamlit UI

### Q14.2 — Metrics Dashboard

What new metrics should be tracked?

| Metric | Type | Purpose |
|--------|------|---------|
| `api_endpoint_used` | Counter | Track old vs new endpoint usage ratio |
| `source_references_count` | Histogram | Distribution of source refs per document |
| `hyperlinks_per_document` | Histogram | How many clickable links per doc |
| `fallback_rate` | Gauge | Percentage of requests using old API |
| `source_index_build_ms` | Timer | Source index construction latency |

**Recommendation:** Add these to the existing `token_log` dict. No new monitoring infrastructure needed — the existing logging captures everything.

**ANSWER**: All of the above

---

## 15. UI Integration (Streamlit)

### Q15.1 — Raw API Data Display Location

Where should raw API data appear in the Streamlit UI?

| Option | Description |
|--------|-------------|
| **(A)** New tab on report page | "Raw Data" tab alongside existing report tabs |
| **(B)** Collapsible section below chat | Expandable `st.expander("Raw API Data")` after each response |
| **(C)** Separate page | New "Data Explorer" page in sidebar navigation |
| **(D)** Modal/dialog | Click "View Raw Data" button → modal overlay |

**Recommendation: (A)** — New tab on the report page. It's discoverable, doesn't clutter the chat flow, and fits the existing multi-tab pattern in the scope-gap UI. The tab shows a searchable `st.dataframe()` with all API fields.

**Question for user:** Should the raw data tab show ALL records for the trade, or only records that contributed to the current response?

**ANSWER**: **(B)** Collapsible section below chat | Expandable `st.expander("Raw API Data")` after each response | The raw data tab should show ALL records for the trade

### Q15.2 — Source Reference Display in UI

Should source references (S3 PDF links) be clickable in the UI chat response?

| Option | Description |
|--------|-------------|
| **(A)** Clickable drawing names in chat | Drawing names in the LLM response become hyperlinks |
| **(B)** Source panel sidebar | Separate panel showing all source drawings with links |
| **(C)** Both | Inline hyperlinks + dedicated source panel |

**Recommendation: (C)** — Both. Inline hyperlinks in the chat markdown give immediate context. A dedicated source panel (collapsible sidebar or tab) gives a complete overview. The chat links are post-processed from the `source_references` dict — we match drawing names in the LLM output and wrap them with `<a href>` tags.

**ANSWER**: **(C)** Both | Inline hyperlinks + dedicated source panel |

### Q15.3 — Raw Data Table Features

What features should the raw data table support?

| Feature | Priority | Implementation |
|---------|----------|----------------|
| Search/filter across all columns | High | `st.dataframe` with column filters |
| Sort by any column | High | Built-in `st.dataframe` sorting |
| Export raw data to CSV | Medium | `st.download_button` with CSV export |
| Column visibility toggle | Low | `st.multiselect` for column selection |
| Pagination | Medium | `st.dataframe` handles this natively for large datasets |

**Recommendation:** High-priority features only for v1. Search, sort, and pagination come free with `st.dataframe()`. CSV export is one line of code. Column toggle is nice-to-have for v2.

**ANSWER**:  High-priority features only for v1. Search, sort, and pagination come free with `st.dataframe()`. CSV export is one line of code. Column toggle is nice-to-have in v1.

---

## 16. Data Integrity

### Q16.1 — Field Validation on New API Response

Should we validate the new fields?

| Field | Validation | Action on Failure |
|-------|------------|-------------------|
| `drawingId` | Must be integer > 0 | Log warning, skip source ref for this record |
| `s3BucketPath` | Must be non-empty string, no `../` | Log warning, skip hyperlink |
| `pdfName` | Must be non-empty string, URL-safe chars | Log warning, skip hyperlink |
| `x`, `y` | Must be integer >= 0 | Log warning, set to 0 (coordinates optional) |
| `width`, `height` | Must be integer > 0 | Log warning, set to 0 (dimensions optional) |

**Recommendation:** Validate at the boundary (source index build step). Use a simple validator function. Invalid fields don't break the pipeline — they just result in missing hyperlinks or coordinates. Log structured warnings for ops.

**ANSWER**: Validate at the boundary (source index build step). Use a simple validator function. Invalid fields don't break the pipeline — they just result in missing hyperlinks or coordinates. Log structured warnings for ops.

### Q16.2 — Deduplication with New Fields

The current dedup is by `_id`. Should new fields affect dedup?

| Option | Description |
|--------|-------------|
| **(A)** No change | Dedup by `_id` only — same as current |
| **(B)** Dedup by `_id` + `drawingId` | Handle potential ID conflicts |

**Recommendation: (A)** — No change. `_id` is the MongoDB document ID, globally unique. Adding `drawingId` to dedup logic would be redundant and could mask legitimate duplicate entries.

**ANSWER**: (A)** — No change. `_id` is the MongoDB document ID, globally unique. Adding `drawingId` to dedup logic would be redundant and could mask legitimate duplicate entries.

---

## Summary of Questions Requiring User Input

| # | Question | Section |
|---|----------|---------|
| **U1** | Does iFieldSmart have an existing PDF viewer URL pattern, or should we use direct S3 URLs? | Q2.2 |
| **U2** | What is the S3 bucket access model — public, IAM-authenticated, or app-gated? | Q11.2 |
| **U3** | Should the raw data tab show ALL records or only records contributing to the current response? | Q15.1 |
| **U4** | Should the traceability table appear in every document type or only exhibits? | Q7.2 |
| **U5** | Should the raw data in UI show ALL records (potentially 11K+) or paginated subsets? | Q4.2 |

All other questions have recommendations that can proceed without user input. Please answer these 5 questions so I can finalize the design spec.

---

## Recommendation Summary (Quick Reference)

| # | Topic | Recommended Option |
|---|-------|-------------------|
| Q1.1 | Endpoint migration | **(C)** Replace with fallback |
| Q1.2 | Data volume | **(C)** Two-tier extraction |
| Q1.3 | Concurrency | **(A)** Keep at 30 |
| Q2.1 | Source index build | **(B)** Build after dedup |
| Q2.2 | S3 URL format | **(D) or (A)** — needs user input |
| Q2.3 | Source in LLM context | **(A)** No source data in LLM |
| Q3.1 | Latency tracking | **(C)** Comparative logging |
| Q3.2 | Source build tracking | **(B)** Add to token_log |
| Q3.3 | Doc gen impact | **(A)** No concern |
| Q4.1 | Request changes | **(A)** No request changes |
| Q4.2 | Response changes | **(D)** Source refs + separate raw endpoint |
| Q4.3 | Missing fields | **(C)** Log warning and skip |
| Q5.1 | Path injection | **(B+C)** Sanitize + allowlist |
| Q5.2 | Raw data exposure | **(A)** Display all fields |
| Q5.3 | SQL injection | Already protected |
| Q6.1 | Testing | 85% coverage, unit + integration + E2E |
| Q6.2 | Feature flag | **(B)** Env var flag |
| Q6.3 | Rollback | Env var toggle, <30s rollback |
| Q7.1 | Data retention | **(A)** No additional retention |
| Q7.2 | Traceability | **(B)** Explicit table — needs user input |
| Q8.1 | API DR | Fallback mechanism IS the DR plan |
| Q8.2 | Source data loss | Graceful degradation |
| Q9.1 | Diagnostic logging | All entries listed |
| Q9.2 | User error messages | **(B)** Info banner + warnings field |
| Q10.1 | Config management | 3 new env vars |
| Q10.2 | Dependencies | Zero new dependencies |
| Q11.1 | Network | No changes needed |
| Q11.2 | S3 access | Needs user input |
| Q12.1 | Cache | No changes |
| Q12.2 | Index cleanup | **(A)** Garbage collect with session |
| Q12.3 | Parallel processing | Yes — parallel with context build |
| Q13.1 | Response versioning | **(B)** Add api_version field |
| Q13.2 | Backward compat | Strict — zero breaking changes |
| Q14.1 | Fallback alerting | **(A)** Log only |
| Q14.2 | Metrics | Add to existing token_log |
| Q15.1 | Raw data location | **(A)** New tab — needs user input |
| Q15.2 | Source ref UI | **(C)** Inline links + source panel |
| Q15.3 | Raw table features | High-priority only (search, sort, export) |
| Q16.1 | Field validation | Validate at boundary, log warnings |
| Q16.2 | Dedup strategy | **(A)** No change — dedup by _id |
