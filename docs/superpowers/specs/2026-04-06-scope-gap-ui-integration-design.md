# Scope Gap Pipeline — UI Integration & Production Hardening Design Spec

**Date:** 2026-04-06
**Status:** APPROVED (all 8 design sections reviewed by user)
**Approach:** B — Parallel Trade Orchestrator
**Predecessor:** `2026-04-05-scope-gap-pipeline-design.md` (Phase 11, 7-agent pipeline)
**Clarifying Questions:** `SCOPE_GAP_CLARIFYING_QUESTIONS (2).md` + `CLARIFYING_QUESTIONS_FOR_USER.md`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [User Answers Summary](#2-user-answers-summary)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Session Architecture](#4-session-architecture)
5. [Worker Pool & Concurrency](#5-worker-pool--concurrency)
6. [Webhook & Pre-computation](#6-webhook--pre-computation)
7. [Highlight Persistence](#7-highlight-persistence)
8. [New API Endpoints](#8-new-api-endpoints)
9. [Contractual Language & Model Changes](#9-contractual-language--model-changes)
10. [Production Review — 12 Perspectives](#10-production-review--12-perspectives)
11. [Development Phases](#11-development-phases)
12. [Configuration Reference](#12-configuration-reference)
13. [Success Criteria](#13-success-criteria)

---

## 1. Executive Summary

Phase 11 delivered a working 7-agent scope gap extraction pipeline (56 tests, 77% coverage, 21 files). This design closes the **10 gaps** between the production UI (`scopegap-agent-v3.html`) and the backend, adds project-level orchestration for **50-150 trades per project**, webhook-triggered pre-computation, per-user highlight persistence in S3, contractual language output, and production hardening across 12 evaluation perspectives.

**Key numbers:**
- 17 new API endpoints (17 existing untouched)
- 8 development phases (~20 days)
- 150 trades per project at concurrency 10 → ~60 min cold, ~3 sec cached
- ~$15-19/project/month estimated LLM cost
- Existing 7-agent pipeline is **untouched** — wrapped by a new ProjectOrchestrator

---

## 2. User Answers Summary

### Original 15 Questions

| # | Topic | Answer | Implication |
|---|-------|--------|-------------|
| Q1 | Drawing/Spec source | Separate API endpoint (c) | New API integration (TBD URL, existing iFieldSmart API) |
| Q2 | Revisions/Sets | Hardcoded per project (c) | Frontend owns revision list, we provide sets endpoint |
| Q3 | Drawing Viewer | External viewer (c) | Backend does NOT need x/y annotation coords |
| Q4 | Highlight Persistence | MVP (a) | Must build highlight save/load endpoints |
| Q5 | Multi-Trade | Auto-run all trades on open (b) | Parallel pipeline for ALL trades simultaneously |
| Q6 | Trade Colors | Backend owns palette (a) | Add color mapping to API response |
| Q7 | Checkbox State | Client-side only (b) | No backend change needed |
| Q8 | Reference Panel | Multiple drawing_refs per item (a) | Extend ScopeItem model with `drawing_refs: list[str]` |
| Q9 | Export Format | Word + PDF (b) | Remove CSV/JSON from export, keep Word+PDF |
| Q10 | Findings Count | From pipeline result (a) | Group-by counting on `drawing_name` |
| Q11 | Pipeline Trigger | Auto on open + pre-computed (b+d) | Background pre-computation on project creation |
| Q12 | Drawing Viewer checkboxes | Visual toggle only (a) | No persistence needed |
| Q13 | 23 Trades | Dynamic from MongoDB (c) | Add trades discovery endpoint per project |
| Q14 | Scope Item Text | Contractual language | Change LLM prompt to output contractual terms |
| Q15 | Session Scope | Per project (b) | Restructure session model — one session holds ALL trades |

### Follow-Up Questions

| # | Topic | Answer | Implication |
|---|-------|--------|-------------|
| FQ1 | Drawing/Spec API | Existing iFieldSmart API (URL TBD) | Pluggable interface, prefix mapping fallback |
| FQ2 | External Viewer | Already integrated in iFieldSmart | No backend viewer work needed |
| FQ3 | Highlight Storage | S3 JSON, per-user, full data (rect+color+label+scope_item) | S3 path: `highlights/{project_id}/{user_id}/{drawing}.json` |
| FQ4a | Trades per project | 50-150 | Requires parallel orchestrator (Approach B) |
| FQ4b | LLM cost acceptable | Yes | $15/project cold run, $19/project/month |
| FQ4c | Pre-computation trigger | Webhook from iFieldSmart | Webhook receiver + HMAC signature |
| FQ4d | Re-run on new drawings | Yes | Smart re-computation (only changed trades) |
| FQ4e | Partial results | Yes, as each trade completes | Progressive SSE streaming |
| FQ5a | Old sessions | Migrate | Lazy migration on first access |
| FQ5b | Trade results storage | Separate, linked by parent session ID | `TradeResultContainer` per trade in `ProjectSession` |
| FQ5c | Re-run behavior | Keep version history | `versions: list[TradeRunRecord]` per trade |
| FQ5d | Session size | Archive older runs | Max 5 versions per trade, archive to S3 |
| FQ6a | Contractual examples | "Consider on your own" | Built-in AIA/CSI standard phrases |
| FQ6b | Standard phrases | Yes (furnish and install, coordinate with, etc.) | Embedded in extraction prompt |
| FQ6c | Contract divisions | Yes (per Division 26 — Electrical, etc.) | CSI MasterFormat references in output |
| FQ6d | Reference document | Yes (exists, not yet shared) | Pluggable few-shot examples in prompt |
| FQ7a | Frontend passes set_id | Yes | Accept set_id param on all endpoints |
| FQ7b | Provide sets list | Yes | `GET /projects/{id}/sets` endpoint |
| FQ7c | Default when none selected | Latest/most recent set | `default_set_id` = highest drawing_count |
| FQ8a | Use 23 UI colors | Yes | Copy TC object from scopegap-agent-v3.html |
| FQ8b | Auto-generate for unknown | Yes (hash-based) | `hash(trade) → HSL(S=70%, L=65%)` |
| FQ8c | Color format | Both hex and RGB | `{"hex": "#F48FB1", "rgb": [244, 143, 177]}` |
| FQ9a | PDF = Word conversion | Yes | Direct docx → pdf conversion |
| FQ9b | Different PDF layout | No, same as Word | Single generation path |
| FQ9c | All trades in one file | Yes | Combined multi-trade document |
| FQ9d | Export All = combined or ZIP | Yes (both options) | `mode=combined` or `mode=zip` param |
| FQ10a | Trades API | Two APIs: `project_id/trade` and `project_id/setid/trade` | Both integrated in DataFetcher |
| FQ10b | Derive vs API | Maintain accordingly | Use API for discovery, cache for session |
| FQ10c | Cache trades list | Yes, for session duration | Redis cache, key: `trades:{project_id}:{set_id}` |

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL TRIGGERS                                 │
│                                                                             │
│  iFieldSmart Webhook ──────┐      User Opens Workspace ──────┐             │
│  (project.created)          │      (browser request)           │             │
│  (drawings.uploaded)        │                                  │             │
└─────────────────────────────┼──────────────────────────────────┼─────────────┘
                              ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        WEBHOOK RECEIVER (new)                               │
│  POST /api/scope-gap/webhooks/project-event                                │
│  Validates HMAC-SHA256 signature → enqueues pre-computation job            │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PROJECT ORCHESTRATOR (new)                             │
│                                                                             │
│  1. Trade Discovery ── GET trades from MongoDB (2 APIs)                    │
│  2. Session Lookup ─── Find/create per-project session                     │
│  3. Worker Pool ────── Semaphore(10) concurrent trade pipelines             │
│  4. Progress SSE ───── Emit trade-by-trade results as they complete        │
│  5. Result Merge ───── Aggregate all trades into project-level summary     │
│  6. Export Trigger ─── Combined Word+PDF if requested                      │
│                                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     ┌─────────────┐     │
│  │ Trade 1     │ │ Trade 2     │ │ Trade 3     │ ... │ Trade N     │     │
│  │ (existing   │ │ (existing   │ │ (existing   │     │ (existing   │     │
│  │  7-agent    │ │  7-agent    │ │  7-agent    │     │  7-agent    │     │
│  │  pipeline)  │ │  pipeline)  │ │  pipeline)  │     │  pipeline)  │     │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘     └──────┬──────┘     │
│         │               │               │                    │             │
│         ▼               ▼               ▼                    ▼             │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │              PER-PROJECT SESSION (restructured)                   │     │
│  │  session_id: "proj_7276"                                        │     │
│  │  ├── trade_results: {                                           │     │
│  │  │     "Electrical": TradeResultContainer(versions=[v1,v2])     │     │
│  │  │     "Plumbing": TradeResultContainer(versions=[v1])          │     │
│  │  │     ...up to 150 trades                                      │     │
│  │  │   }                                                          │     │
│  │  ├── highlights: S3 → per-user JSON                             │     │
│  │  └── messages: [...follow-up chat]                              │     │
│  └──────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐
  │  MongoDB    │     │    Redis     │     │     S3       │
  │  HTTP APIs  │     │  L1+L2      │     │  Sessions    │
  │  (existing) │     │  Cache      │     │  Highlights  │
  │             │     │  Sessions   │     │  Documents   │
  └─────────────┘     └──────────────┘     └──────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestrator concurrency | Semaphore(10) | 10 trades × ~5 LLM calls = 50 concurrent OpenAI calls. Within rate limits. |
| Existing pipeline | Untouched | 7-agent pipeline is proven (56 tests, 77% coverage). Orchestrator wraps it. |
| Session key | `project_id` only | One session per project, all trades linked. Trade results stored separately. |
| Highlight storage | S3 JSON, per-user | `s3://{bucket}/highlights/{project_id}/{user_id}/{drawing_name}.json` |
| Pre-computation | Webhook-triggered | iFieldSmart fires event → we pre-compute all trades in background |
| Progressive results | SSE per-trade | Each trade emits result as soon as its pipeline completes |

---

## 4. Session Architecture

### Per-Project Session Model

```
ProjectSession
├── id: "proj_7276"
├── project_id: 7276
├── project_name: "Granville Hotel"
├── created_at, updated_at
│
├── trade_results: dict[str, TradeResultContainer]
│     "Electrical" → TradeResultContainer
│       ├── current_version: 2
│       ├── versions: [
│       │     v1: TradeRunRecord (archived)
│       │     v2: TradeRunRecord (active)
│       │   ]
│       └── latest_result: ScopeGapResult
│     "Plumbing" → TradeResultContainer
│       ├── current_version: 1
│       └── latest_result: ScopeGapResult
│     ... up to 150 trades
│
├── Shared State
│     ├── ambiguity_resolutions: dict[str, str]
│     ├── gotcha_acknowledgments: list[str]
│     ├── ignored_items: list[str]
│     └── messages: list[SessionMessage]
│
└── Archival Policy
      ├── max_versions_per_trade: 5
      ├── archive_after_days: 30
      └── When version 6 created → v1 archived to S3, removed from Redis
```

### Storage Tiers

| Tier | Storage | Contents | TTL | Size |
|------|---------|----------|-----|------|
| L1 (hot) | Memory TTLCache | latest_result per trade (LRU, max 20 trades) | 1 hour | ~1 MB per trade |
| L2 (warm) | Redis | Full session with all active versions | 7 days | ~15 MB per project |
| L3 (cold) | S3 | Archived versions + complete history (gzipped JSON) | Permanent | Unlimited |

### Session Size Management

- **Redis** holds: session metadata + `latest_result` per trade + version metadata (stats only, no full result)
- **Full historical results** written to S3 immediately on completion, only `latest_result` stays in Redis
- **L1 memory** holds only the most recently accessed trades (LRU, max 20 per session)
- **Max Redis session size**: ~15 MB (well within Redis limits)

### Migration from Old Sessions

Strategy: lazy migration on first access.

1. On first access to `project_id`, check for old-format keys: `session:{project_id}_*`
2. If found: read all old keys, create new `ProjectSession`, import each trade as `TradeResultContainer` v1
3. Delete old keys
4. If not found: create fresh `ProjectSession`
5. Manual migration endpoint also available: `POST /api/scope-gap/sessions/migrate/{project_id}`

---

## 5. Worker Pool & Concurrency

### Execution Flow

```
ProjectOrchestrator.run_all_trades(project_id)
    │
    ├─ 1. Trade Discovery ─── fetch trades from MongoDB (2 APIs)
    │     Returns: ["Electrical", "Plumbing", "HVAC", ... × 150]
    │
    ├─ 2. Diff against session ── skip trades with fresh results (< RESULT_FRESHNESS_TTL)
    │     Returns: trades_to_run (only stale/missing trades)
    │
    ├─ 3. Worker Pool ──── Semaphore(TRADE_CONCURRENCY=10)
    │     10 trades run in parallel, each using existing 7-agent pipeline
    │     When slot frees → next trade starts
    │     Each completed trade immediately:
    │       → Saves TradeRunRecord to session
    │       → Emits SSE event
    │       → Updates progress counter
    │
    ├─ 4. Aggregation ──── Merge all trades into project-level summary
    │
    └─ 5. Combined Export (if requested)
```

### Rate Limiting

| Metric | Per Trade | 10 Concurrent | OpenAI Limit | Headroom |
|--------|-----------|---------------|-------------|----------|
| Requests | 5 calls | 50 burst | 500 RPM | 70% |
| Tokens | ~32K | ~320K | 800K TPM | 60% |

**Adaptive throttling:** On OpenAI 429, reduce `TRADE_CONCURRENCY` by 2 (min 4). Restore after 60s with no 429s.

### Progressive SSE Events

```
event: session_loaded     → {total_trades: 150, completed: 45, cached: 45}
event: trade_complete     → {trade, items_count, ambiguities, gotchas, elapsed_ms}
event: trade_failed       → {trade, error, retry_in_ms}
event: progress           → {completed, total, pct, estimated_remaining_ms}
event: all_complete       → {total_trades, successful, failed, total_items, total_cost_usd}
```

### Failure Handling

| Scenario | Behavior |
|----------|----------|
| Single trade fails | Other trades continue. Failed trade marked with error. User can retry individually. |
| OpenAI 429 rate limit | Adaptive throttle — reduce concurrency, backoff, auto-restore |
| OpenAI 500/503 | 3 retries with exponential backoff per trade (existing pipeline behavior) |
| Redis unavailable | Degrade to L1 memory + S3 only. Warn in logs. |
| User disconnects SSE | Pipeline continues in background. User reconnects → loads current state. |
| >50% trades fail | Emit `pipeline_degraded` event. Surface to user, no auto-retry. |

### Smart Scheduling

```python
for trade in discovered_trades:
    existing = session.trade_results.get(trade)
    if existing and existing.latest_result:
        age = now - existing.latest_result.completed_at
        if age < RESULT_FRESHNESS_TTL:     # default: 24 hours
            emit_sse("trade_cached", trade)  # instant, $0
            continue
    trades_to_run.append(trade)
```

- First open: all 150 trades run (~60 min, ~$15)
- Subsequent opens within 24h: instant from cache ($0)
- After drawing upload: only changed trades re-run (~$1)

---

## 6. Webhook & Pre-computation

### Webhook Receiver

```
POST /api/scope-gap/webhooks/project-event

Headers:
  X-Webhook-Signature: sha256=<hmac_hex>
  X-Webhook-Event-Id: <unique_event_id>

Events:
  project.created   → enqueue full pre-computation for all trades
  drawings.uploaded  → re-run only changed trades (or all if changed_trades not provided)

Response:
  202 Accepted  {"job_id": "pre_abc123", "message": "Pre-computation queued"}
  200 OK        {"message": "Duplicate event, already processed"}
  401 Unauthorized  (bad signature)
```

### Webhook Security

1. **HMAC-SHA256** signature verification (shared secret in .env)
2. **Timestamp freshness** — reject events >5 min old (replay protection)
3. **IP allowlist** (optional, configurable in .env)
4. **Idempotency** — track event_id in Redis (1h TTL), skip duplicates

### Pre-computation Priority

- User-initiated pipelines: **HIGH** priority (runs first)
- Webhook pre-computation: **LOW** priority (yields to users)
- If user opens workspace while pre-compute is running: attach to in-progress SSE, serve already-completed trades

### Smart Re-computation on Drawing Upload

```
drawings.uploaded event arrives
  ├─ changed_trades provided? → Re-run only those trades
  └─ changed_trades NOT provided?
       → Re-discover trades from MongoDB
       → Compare record_count with session
       → Re-run only trades where count changed or trade is new
```

---

## 7. Highlight Persistence

### S3 Storage Layout

```
s3://{bucket}/highlights/{project_id}/{user_id}/{drawing_name}.json
s3://{bucket}/highlights/{project_id}/{user_id}/_index.json
```

### Highlight Data Model

```python
class Highlight(BaseModel):
    id: str                           # "hl_a3f7b2c1"
    drawing_name: str                 # "E0.03"
    page: int = 1
    # Region
    x: float                          # left position (points)
    y: float                          # top position (points)
    width: float                      # rectangle width
    height: float                     # rectangle height
    # Visual
    color: str = "#FFEB3B"            # highlight color
    opacity: float = 0.3
    # Metadata
    label: str = ""                   # user-supplied label
    trade: str = ""                   # trade assignment
    critical: bool = False            # flagged as critical
    comment: str = ""                 # user comment
    # Linking
    scope_item_id: Optional[str]      # linked scope item
    scope_item_ids: list[str] = []    # multiple linked items
    # Timestamps
    created_at: datetime
    updated_at: datetime
```

### Caching

- **Redis cache**: `hl:{project_id}:{user_id}:{drawing_name}` with 5 min TTL
- **Invalidated** on create/update/delete
- **Index**: `hl_idx:{project_id}:{user_id}` — lightweight drawing counts

### API Endpoints

```
POST   /api/scope-gap/highlights                          Create highlight
GET    /api/scope-gap/highlights?project_id&drawing_name   List highlights
GET    /api/scope-gap/highlights/index?project_id          Get index (counts)
PATCH  /api/scope-gap/highlights/{id}                     Update highlight
DELETE /api/scope-gap/highlights/{id}                     Delete one
DELETE /api/scope-gap/highlights?project_id&drawing_name   Delete all for drawing
GET    /api/scope-gap/highlights/export?project_id         Export as ZIP
```

---

## 8. New API Endpoints

### Complete Endpoint Map

| Category | Endpoint | Gap | Purpose |
|----------|----------|-----|---------|
| **Project** | `GET /projects/{id}/trades` | G5, Q13 | Trade list with status + color + record count |
| | `GET /projects/{id}/sets` | G2 | Revision/set dropdown data |
| | `GET /projects/{id}/drawings` | G1 | Categorized drawing/spec tree |
| | `GET /projects/{id}/drawings/meta` | G3 | Batch drawing metadata for Reference Panel |
| | `GET /projects/{id}/trade-colors` | Q6 | Backend-owned trade color palette |
| | `GET /projects/{id}/status` | G10 | Project pipeline status dashboard |
| | `POST /projects/{id}/run-all` | Q5 | Trigger all-trades pipeline |
| | `GET /projects/{id}/stream` | Q5 | Progressive SSE for project pipeline |
| | `GET /projects/{id}/export` | Q9 | Combined Word+PDF export |
| **Highlights** | 7 CRUD endpoints | G4 | Per-user highlight persistence |
| **Webhook** | `POST /webhooks/project-event` | Q11 | Pre-computation trigger |
| **Migration** | `POST /sessions/migrate/{id}` | Q15 | Old session migration |
| **Monitoring** | `GET /health` | — | Service health check |
| | `GET /metrics` | — | Prometheus metrics |

All endpoints prefixed with `/api/scope-gap/`.

### Key Response Shapes

**GET /projects/{id}/trades**
```json
{
  "project_id": 7276,
  "trades": [
    {"trade": "Electrical", "record_count": 107, "status": "ready", "color": "#F48FB1"},
    {"trade": "HVAC", "record_count": 89, "status": "running", "color": "#90A4AE"}
  ],
  "total_trades": 67
}
```

Status values: `ready` | `stale` | `running` | `pending` | `failed`

**GET /projects/{id}/drawings**
```json
{
  "project_id": 7276,
  "categories": {
    "ELECTRICAL": {
      "drawings": [{"drawing_name": "E0.03", "drawing_title": "Schedules", "source_type": "drawing"}],
      "specs": [{"drawing_name": "260000", "drawing_title": "Electrical General", "source_type": "specification"}]
    }
  }
}
```

**GET /projects/{id}/trade-colors**
```json
{
  "colors": {
    "Electrical": {"hex": "#F48FB1", "rgb": [244, 143, 177]},
    "Custom Trade": {"hex": "#7B1FA2", "rgb": [123, 31, 162]}
  }
}
```

**POST /projects/{id}/run-all**
```json
{
  "job_id": "proj_run_abc123",
  "trades_to_run": 67,
  "trades_cached": 45,
  "estimated_minutes": 25,
  "estimated_cost_usd": 6.70,
  "stream_url": "/api/scope-gap/projects/7276/stream?job_id=proj_run_abc123"
}
```

**GET /projects/{id}/export**
Query params: `format=both`, `trades=Electrical,Plumbing`, `mode=combined|per_trade|zip`

---

## 9. Contractual Language & Model Changes

### Extraction Agent Prompt

Every scope item now begins with "Contractor shall" and uses standard AIA/CSI construction contract terminology:

**Standard phrases (mandatory):**
- "Contractor shall furnish and install" (supply + labor)
- "Contractor shall provide" (inclusive)
- "coordinate with [Division XX — Trade]" (interface)
- "provide allowance for" (cost allocation)
- "verify in field" (verification)
- "as indicated on Drawing [number]" (drawing reference)
- "per Division [number] — [name]" (CSI MasterFormat)
- "in accordance with" (specification reference)
- "including but not limited to" (non-exhaustive)
- "prior to" (sequencing)

**Example output:**
```
"Contractor shall furnish and install Panel LP-1, 480V/3Ph, on the first
floor electrical room as indicated on Drawing E-101, per Division 26 —
Electrical. Verify in field all dimensions and existing conditions prior
to installation. Coordinate with Division 23 — Mechanical for ceiling
space routing."
```

**Reference document:** User confirmed a reference scope-of-work document exists. When provided, 3-5 examples will be extracted and embedded as few-shot examples in the prompt. Until then, built-in examples are used. This is a pluggable interface — swap examples without code changes.

### ScopeItem Model Extensions

```python
class ScopeItem(BaseModel):
    # Existing (unchanged)
    id: str
    text: str                         # now contractual language
    drawing_name: str                 # primary drawing
    drawing_title: Optional[str]
    page: int = 1
    source_snippet: str = ""
    confidence: float = 0.0
    csi_hint: Optional[str]
    source_record_id: Optional[str]
    # New fields
    drawing_refs: list[str] = []      # Q8: multiple drawing references
    discipline: Optional[str] = None  # G1: "ELECTRICAL", "MECHANICAL", etc.
    source_type: str = "drawing"      # G8: "drawing" or "specification"
    csi_division: Optional[str] = None  # "Division 26 — Electrical"

class ClassifiedItem(ScopeItem):
    # Existing (unchanged)
    trade: str
    csi_code: str
    csi_division: str
    classification_confidence: float
    classification_reason: str
    # New field
    trade_color: str = ""             # Q6: hex color from palette
```

### Discipline Derivation

Two-layer strategy:
1. **Drawing name prefix mapping** (reliable for 90%+ of drawings):
   `E→ELECTRICAL, M→MECHANICAL, A→ARCHITECTURAL, S→STRUCTURAL, P→PLUMBING, FP→FIRE PROTECTION`, etc.
2. **iFieldSmart API override** (pluggable — when FQ1 URL is provided, use API-returned discipline)

### drawing_refs Population

- Extraction agent returns `drawing_refs` from source drawings
- Classification agent enriches by finding related drawings (same CSI + same trade + overlapping keywords)
- Max 5 refs per item

### Backward Compatibility

| Change | Migration |
|--------|-----------|
| `drawing_refs` added | Existing items get `drawing_refs = [drawing_name]` |
| `discipline` added | Derived at read time from `drawing_name` if missing |
| `source_type` added | Default `"drawing"` — no migration needed |
| `trade_color` added | Populated on read from TradeColorService |
| `text` now contractual | Only new runs use contractual style; old results unchanged |

---

## 10. Production Review — 12 Perspectives

### 10.1 Scaling

| Dimension | Capacity | Limit |
|-----------|----------|-------|
| Trades per project | 150 concurrent (pool of 10) | 200 (configurable) |
| Concurrent projects | 3 × 10 trades = 30 parallel pipelines | OpenAI RPM |
| Records per trade | 11,360 tested | Millions (paginated) |
| Session size (Redis) | ~15 MB per project | Redis 512 MB default |
| Highlights per project | 10,000 (cap) | S3 unlimited |
| Users per project | Unlimited (per-user highlights) | S3 unlimited |

**Bottlenecks:** OpenAI RPM (70% headroom at concurrency 10), MongoDB API throughput (mitigated by caching), Redis memory (~100 MB for 3 concurrent projects).

### 10.2 Optimization

- Skip fresh trades (`RESULT_FRESHNESS_TTL=24h`) — $0 for repeated opens
- Smart re-computation on webhook — only changed trades re-run
- Batch drawing metadata — single API call, cached 30 min
- Highlight read caching — Redis 5 min TTL, 95%+ hit rate
- Progressive delivery — first results in ~4 min, not 60 min
- Monthly cost per active project: ~$19

### 10.3 Performance Metrics

| Metric | Target |
|--------|--------|
| Trade discovery (cold) | < 5 sec |
| Trade discovery (cached) | < 100 ms |
| Single trade pipeline | < 5 min |
| Full project (150 trades, cold) | < 70 min |
| Full project (all cached) | < 3 sec |
| Time-to-first-trade-result | < 5 min |
| Highlight create | < 500 ms |
| Highlight load (cached) | < 10 ms |
| Export generation (all trades) | < 30 sec |
| Webhook → job queued | < 100 ms |

Prometheus metrics endpoint: `GET /api/scope-gap/metrics`

### 10.4 Request Handling

- Per-project `asyncio.Lock` prevents duplicate pipeline starts
- If pipeline already running, new users attach to existing SSE
- Redis WATCH for optimistic locking on session writes
- S3 conditional PUTs for highlight writes
- Timeouts: 600s per trade, 7200s per project, graceful shutdown with 60s drain

### 10.5 Vulnerability (OWASP Top 10)

| # | Vulnerability | Risk | Mitigation |
|---|--------------|------|------------|
| A01 | Broken Access Control | MEDIUM | X-User-Id validated against Phase 10 auth. Per-user highlight isolation. |
| A02 | Cryptographic Failures | LOW | HMAC-SHA256 webhooks. S3 SSE. No PII. |
| A03 | Injection | LOW | Pydantic validation. No raw SQL. No shell exec. |
| A04 | Insecure Design | LOW | Immutable models. Rate limiting all endpoints. |
| A05 | Security Misconfig | MEDIUM | .env for secrets. Fail at startup if missing. |
| A06 | Vulnerable Components | LOW | Pinned deps. No known CVEs. |
| A07 | Auth Failures | MEDIUM | Webhook signature + timestamp + idempotency. |
| A08 | Data Integrity | LOW | S3 versioning. Redis WATCH. |
| A09 | Logging/Monitoring | LOW | Prometheus + structured JSON logging. |
| A10 | SSRF | LOW | No user-supplied URLs in API calls. |

Additional: Prompt injection guard on user queries, S3 private bucket, Redis requirepass, 100 req/min rate limit per IP.

### 10.6 SDLC Parameters

8 development phases, ~20 days total. Every phase includes: unit tests (80%+ coverage), code review, security scan. Integration tests at Phase 12H. See Section 11 for full breakdown.

### 10.7 Compliance

- No PII stored (user_id is pseudonymous)
- OpenAI API data NOT used for training (business API terms)
- Construction drawing text sent to OpenAI — recommend enterprise agreement for IP protection
- S3 encryption at rest (AWS default)
- Redis requirepass + localhost binding
- TLS termination at Nginx (Let's Encrypt)

### 10.8 Disaster Recovery & Backup

| Component | RPO | RTO | Method |
|-----------|-----|-----|--------|
| Redis sessions | 0 (write-through to S3) | 5 min | Rebuild from S3 on restart |
| S3 data | 0 | 0 | Versioning + optional cross-region replication |
| Pipeline state | In-memory | Restartable | Jobs are idempotent — restart = re-run incomplete |
| MongoDB | N/A | N/A | Not our data — owned by iFieldSmart |

Failure scenarios covered: Redis crash, S3 outage, OpenAI outage, app crash, full server failure.

### 10.9 Support & Helpdesk Framework

- `GET /api/scope-gap/health` — service health (Redis, S3, OpenAI, MongoDB)
- `GET /api/scope-gap/metrics` — Prometheus metrics
- `GET /api/scope-gap/projects/{id}/status` — full pipeline status
- `GET /api/scope-gap/debug/session/{id}` — session dump (admin only)
- Structured JSON logging with correlation IDs
- Alerting: health failure (CRITICAL), >50% trade failures (HIGH), spend >$50/hr (HIGH)

### 10.10 System Maintenance

- Session archival: daily cron, versions > 5 → S3
- Redis cleanup: TTL-based (automatic)
- S3 lifecycle: highlights > 90 days → Glacier
- Stale job cleanup: hourly, cancel jobs running > 2h
- Dependency audit: weekly (`pip-audit`)
- Zero-downtime deployment via Nginx upstream swap

### 10.11 Network & Security

- Nginx reverse proxy on port 443 (Let's Encrypt TLS)
- FastAPI bound to localhost:8003 (not exposed)
- Redis bound to localhost with requirepass
- Firewall: 443 open, 8003/6379 blocked from external
- CORS: ifieldsmart.com origins only
- Webhook: HMAC + timestamp + optional IP allowlist

### 10.12 Resource Management: Efficiency Through Automation

- **Adaptive concurrency**: auto-reduce on 429, auto-restore
- **Smart cache invalidation**: webhook → invalidate only affected trades
- **Cost autopilot**: pre-compute at LOW priority, freshness TTL skips redundant runs
- **Memory management**: LRU L1, TTL L2, lifecycle L3
- **Job lifecycle**: stale jobs auto-cancelled, failed trades logged (no runaway retries)
- **Deployment automation**: systemd services, health checks, Prometheus, structured logs

---

## 11. Development Phases

| Phase | Name | Scope | Estimated |
|-------|------|-------|-----------|
| **12A** | Session Architecture Restructure | ProjectSession model, TradeResultContainer, migration logic, 3-layer persistence | 3 days |
| **12B** | Project Orchestrator & Worker Pool | Orchestrator, worker pool, adaptive throttle, progressive SSE, smart scheduling | 4 days |
| **12C** | New API Endpoints (Gaps) | Trades, sets, drawings, metadata, status, colors (G1-G5, G8, G10) | 3 days |
| **12D** | Highlight Persistence | S3 storage, Redis cache, 7 CRUD endpoints, per-user isolation | 2 days |
| **12E** | Contractual Language & Model Changes | Prompt rewrite, ScopeItem extensions, discipline derivation, drawing_refs enrichment | 2 days |
| **12F** | Webhook & Pre-computation | Webhook receiver, HMAC validation, smart re-computation, priority queue | 2 days |
| **12G** | Combined Export (Word + PDF) | Multi-trade document generation, combined + ZIP modes, PDF conversion | 2 days |
| **12H** | Integration Testing & Hardening | E2E tests, load tests, Prometheus metrics, structured logging, health check | 2 days |
| | **Total** | | **~20 days** |

### Quality Gates Per Phase

- Unit tests: 80%+ coverage
- Code review: code-reviewer agent
- Security scan: security-reviewer agent
- All existing 56 tests must pass (zero regression)

---

## 12. Configuration Reference

### New .env Variables

```env
# Project Orchestrator
TRADE_CONCURRENCY=10                          # max parallel trade pipelines
TRADE_CONCURRENCY_MIN=4                       # floor during adaptive throttle
RESULT_FRESHNESS_TTL=86400                    # 24h — skip re-run if result is fresh
MAX_TRADES_PER_PROJECT=200                    # safety cap
PROJECT_PIPELINE_TIMEOUT=7200                 # 2h max for full project run
TRADE_PIPELINE_TIMEOUT=600                    # 10 min max per single trade
ADAPTIVE_THROTTLE_COOLDOWN=60                 # seconds before restoring concurrency

# Webhook
WEBHOOK_SECRET=<shared-secret-with-ifieldsmart>
WEBHOOK_ALLOWED_IPS=                          # empty = accept all
WEBHOOK_TIMESTAMP_TOLERANCE=300               # 5 min replay window
WEBHOOK_IDEMPOTENCY_TTL=3600                  # 1h dedup window

# Pre-computation
PRECOMPUTE_PRIORITY=low
PRECOMPUTE_CONCURRENCY=5                      # lower than user-initiated (10)
PRECOMPUTE_ENABLED=true                       # feature flag

# Highlights
HIGHLIGHT_S3_PREFIX=highlights
HIGHLIGHT_CACHE_TTL=300                       # 5 min Redis cache
HIGHLIGHT_MAX_PER_DRAWING=500                 # safety cap
HIGHLIGHT_MAX_PER_PROJECT=10000               # safety cap

# Session
SESSION_MAX_VERSIONS_PER_TRADE=5
SESSION_ARCHIVE_AFTER_DAYS=30
SESSION_REDIS_TTL=604800                      # 7 days
SESSION_L1_MAX_TRADES=20                      # LRU cache per session
```

---

## 13. Success Criteria

| Criteria | Target | Measurement |
|----------|--------|-------------|
| All 10 UI-backend gaps closed | 10/10 | Endpoint availability + response shape validation |
| 150-trade project completes | < 70 min cold | `total_ms` in pipeline stats |
| Cached project loads | < 3 sec | Session load time |
| Time-to-first-trade | < 5 min | SSE event timing |
| Highlight CRUD works | < 500 ms writes, < 10 ms cached reads | Endpoint response times |
| Webhook triggers pre-computation | 202 within 100 ms | Response time |
| Contractual language output | All items start with "Contractor shall" | Prompt validation test |
| Existing tests pass | 56/56 | Zero regression |
| New test coverage | 80%+ per phase | pytest --cov |
| Combined export | Word + PDF, all trades | Document content validation |
| Session migration | Old sessions imported correctly | Migration test |
| Security | OWASP Top 10 reviewed, all MEDIUM+ mitigated | Security scan |

---

## Appendix A: Files to Create/Modify

### New Files (~15)

```
scope_pipeline/
├── project_orchestrator.py          # Master project-level orchestrator
├── services/
│   ├── project_session_manager.py   # Per-project session with trade containers
│   ├── highlight_service.py         # S3 highlight CRUD + Redis cache
│   ├── trade_color_service.py       # 23 base colors + hash-based generation
│   ├── trade_discovery_service.py   # MongoDB trade listing (2 APIs)
│   ├── drawing_index_service.py     # Drawing categorization + metadata
│   ├── webhook_handler.py           # HMAC validation + event processing
│   ├── export_service.py            # Combined Word+PDF generation
│   └── metrics_service.py           # Prometheus metrics collection
├── routers/
│   ├── project_endpoints.py         # /projects/{id}/trades, sets, drawings, etc.
│   ├── highlight_endpoints.py       # /highlights CRUD
│   └── webhook_endpoints.py         # /webhooks/project-event
├── models_v2.py                     # ProjectSession, TradeResultContainer, Highlight
└── migration.py                     # Old session → new session migration
```

### Modified Files (~8)

```
scope_pipeline/
├── models.py                        # Add drawing_refs, discipline, source_type, trade_color
├── agents/extraction_agent.py       # Contractual language prompt rewrite
├── agents/classification_agent.py   # drawing_refs enrichment
├── services/data_fetcher.py         # Drawing metadata index building
├── services/document_agent.py       # Multi-trade combined document support
├── config.py                        # New configuration variables
├── routers/scope_gap.py             # Mount new sub-routers
└── __init__.py                      # Register new components
```

### Existing Files (Untouched)

```
scope_pipeline/
├── orchestrator.py                  # Existing trade-level orchestrator (wrapped, not modified)
├── agents/base_agent.py
├── agents/ambiguity_agent.py
├── agents/gotcha_agent.py
├── agents/completeness_agent.py
├── agents/quality_agent.py
├── services/job_manager.py          # Extended (not rewritten) for project jobs
├── services/session_manager.py      # Kept for backward compat during migration
├── services/chat_handler.py
└── services/progress_emitter.py
```
