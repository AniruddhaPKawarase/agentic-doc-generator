# iFieldSmart ScopeAI — Multi-Agent Scope Gap Pipeline Design Spec

**Date:** 2026-04-05
**Status:** APPROVED — Ready for implementation planning
**Author:** Claude (Opus 4.6)
**Approach:** Pipeline of Specialists (Approach A)

---

## 1. Executive Summary

### What We're Building

A **multi-agent scope gap pipeline** inside the existing construction-intelligence-agent (port 8003) that extracts, classifies, validates, and exports per-trade scope inclusions from construction drawings with source traceability, ambiguity detection, gotcha scanning, and multi-pass backpropagation for completeness.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Pipeline of Specialists (Approach A) | Parallel fan-out hits 5-min target with full agent specialization |
| Speed vs thoroughness | Speed (parallel agents) | User requirement: under 5 minutes |
| Agent count | 7 (6 processing + 1 document) | User confirmed: all agents |
| Backpropagation | Incremental + targeted (b+c) | Only re-extract missing items + fix specific agent errors |
| Multi-trade | Single-trade per request | User explicitly chooses trade |
| LLM model | Latest GPT (gpt-4.1 now, gpt-5 when available) | Min latency, max accuracy |
| Blocking/background | Hybrid | <2000 records: blocking+SSE. >=2000: background job |
| Output format | Word + PDF + CSV + JSON | JSON powers frontend interactive report |
| Templates | Deferred to v2 | Ship faster |
| Source traceability | Item-level + page-level | Structured JSON from LLM with drawing_name, page, source_snippet |
| Completeness definition | Drawing coverage + CSI coverage + no hallucinations | Pure Python check (no LLM) |
| Drawing Viewer | Frontend team responsibility | Backend provides structured JSON data |
| Session persistence | 3-layer: L1 memory + L2 Redis + L3 S3 | Survives restarts, supports follow-up chat |

---

## 2. Pipeline Architecture

### System Overview

New API endpoints alongside existing `/api/chat` — not a replacement. Zero changes to existing pipeline.

```
POST /api/scope-gap/generate          — Blocking (< 2000 records)
POST /api/scope-gap/stream            — SSE streaming
POST /api/scope-gap/submit            — Background job (>= 2000 records)
GET  /api/scope-gap/jobs/{id}/status  — Poll job progress
GET  /api/scope-gap/jobs/{id}/result  — Download result
POST /api/scope-gap/jobs/{id}/continue — Continue partial extraction
GET  /api/scope-gap/jobs              — List jobs
DELETE /api/scope-gap/jobs/{id}       — Cancel job
GET  /api/scope-gap/sessions          — List sessions
GET  /api/scope-gap/sessions/{id}     — Session detail
DELETE /api/scope-gap/sessions/{id}   — Delete session
POST /api/scope-gap/sessions/{id}/resolve-ambiguity
POST /api/scope-gap/sessions/{id}/acknowledge-gotcha
POST /api/scope-gap/sessions/{id}/ignore-item
POST /api/scope-gap/sessions/{id}/restore-item
POST /api/scope-gap/sessions/{id}/chat       — Follow-up Q&A
POST /api/scope-gap/sessions/{id}/chat/stream — Streaming Q&A
```

### Pipeline Flow

```
Data Fetch ──→ Extraction Agent ──→ ┌─ Classification Agent ─┐
(existing       (structured JSON)   │  (parallel fan-out)     │
 APIClient)                         ├─ Ambiguity Agent ───────┤
                                    ├─ Gotcha Agent ──────────┤
                                    └─────────┬───────────────┘
                                              │ MERGE
                                              ▼
                                    Completeness Agent (Python, no LLM, ~1ms)
                                              │
                                     < 100%? ─┼─ YES → Targeted re-extraction (loop ≤ 3)
                                              │
                                              ▼ NO
                                    Quality Agent (final review)
                                              │
                                              ▼
                                    Document Agent (Word+PDF+CSV+JSON, parallel)
```

### Timing Budget (5-minute target, 11k records)

| Phase | What | Time |
|-------|------|------|
| 1 | Data fetch (parallel pagination, 15 concurrency) | ~90s |
| 2 | Extraction Agent (GPT-latest, 120k context) | ~60s |
| 3 | Classification + Ambiguity + Gotcha (parallel) | ~25s |
| 4 | Completeness check (pure Python) | ~1s |
| 5 | Quality Agent (lightweight review) | ~20s |
| 6 | Document generation (4 formats parallel) | ~10s |
| **1st pass total** | | **~3.5 min** |
| 7 | Backpropagation (if needed, only missing items) | ~60s |
| **Worst case (1 retry)** | | **~4.5 min** |

---

## 3. Agent Specifications

### Agent Registry

| # | Agent | LLM? | Input | Output | Latency |
|---|-------|------|-------|--------|---------|
| 1 | Extraction | Yes | Raw drawing text by page | `ScopeItem[]` | ~60s |
| 2 | Classification | Yes | `ScopeItem[]` | `ClassifiedItem[]` (adds trade, CSI) | ~20s |
| 3 | Ambiguity | Yes | `ScopeItem[]` | `AmbiguityItem[]` (overlaps, severity) | ~20s |
| 4 | Gotcha | Yes | `ScopeItem[]` | `GotchaItem[]` (hidden risks) | ~20s |
| 5 | Completeness | **No** | Merged results + source lists | `CompletenessReport` (% coverage) | ~1ms |
| 6 | Quality | Yes | Full merged results | `QualityReport` (corrections, validated items) | ~20s |
| 7 | Document | **No** | Validated items + reports | `DocumentSet` (Word/PDF/CSV/JSON) | ~10s |

### Agent Base Class

All agents inherit from `BaseAgent` which provides:
- Automatic timing measurement
- Per-agent retry (2 attempts with backoff)
- SSE progress emission
- Token tracking
- Structured error handling

### Agent 1: Extraction Agent

**Purpose:** Convert raw drawing text into structured scope items with source traceability.

**System prompt strategy:**
- 30+ years construction scope extraction expert persona
- Every item MUST include: drawing_name, page, source_snippet (5-15 words verbatim)
- Authoritative drawing list injected to prevent hallucination
- Output: JSON array only, no markdown

**Context management:**
- Records grouped by drawing_name
- Adaptive compression (300→200→150→100 chars/note)
- Token budget: 120k input, 8k output

### Agent 2: Classification Agent

**Purpose:** Assign trade + CSI MasterFormat code to each extracted item.

**Runs in parallel** with Agents 3 and 4. Receives Extraction output independently.

**System prompt strategy:**
- CSI MasterFormat classification expert persona
- Available trades list provided
- Each item gets: trade, csi_code (XX XX XX), csi_division, confidence, reason

### Agent 3: Ambiguity Agent

**Purpose:** Detect scope items that could belong to multiple trades.

**Runs in parallel** with Agents 2 and 4. Independent judgment (doesn't see Classification output).

**Common ambiguities targeted:**
- Flashing/waterproofing (Roofing vs Sheet Metal)
- Fire stopping (Fire Protection vs General)
- Backing/blocking (Framing vs requiring trade)
- Electrical connections for mechanical equipment
- Pipe insulation (Plumbing vs Insulation)

**Output:** severity (high/medium/low), competing trades, recommendation, drawing refs

### Agent 4: Gotcha Agent

**Purpose:** Proactively detect hidden costs, coordination issues, missing scope, spec conflicts.

**Differentiator feature** — ScoreboardAI does not have this.

**Risk types detected:**
- `hidden_cost` — implied but not explicitly scoped items
- `coordination` — items requiring multi-trade coordination
- `missing_scope` — standard items for trade that are absent
- `spec_conflict` — contradictory requirements across drawings

### Agent 5: Completeness Agent (Pure Python)

**Purpose:** Measure extraction completeness. NO LLM — pure set comparison.

**Metrics calculated:**
- Drawing coverage: `extracted_drawings / source_drawings * 100`
- CSI coverage: `extracted_csi / source_csi * 100`
- Hallucination count: items with drawing_name NOT in source data
- Overall: `(drawing * 0.5) + (csi * 0.3) + (no_hallucination * 0.2)`
- Complete threshold: overall >= 95.0%

**Backpropagation trigger:** If not complete AND attempt < 3, loop back with:
- Missing drawing names (targeted re-extraction)
- Hallucinated item IDs (for removal)
- Specific agent corrections (from Quality Agent if available)

### Agent 6: Quality Agent

**Purpose:** Final accuracy review. Catches duplicates, misclassifications, vague items.

**Checks performed:**
- Duplicate detection (same scope described differently)
- Trade misclassification
- Incorrect CSI codes
- Vague items needing specificity
- Hallucinated items flagged by Completeness Agent

**Output:** Corrections list + final validated items + accuracy score

### Agent 7: Document Agent (No LLM)

**Purpose:** Generate 4 output formats in parallel.

**Formats:**
1. **Word (.docx)** — Branded exhibit format (existing styling). Sections: Executive Summary, Scope Inclusions (grouped by drawing), Ambiguities, Gotchas, Completeness Report, Source Drawing Index
2. **PDF (.pdf)** — Generated via `reportlab`. Same structure as Word.
3. **CSV (.csv)** — Flat table: Trade, CSI, Item, Drawing, Page, Source Snippet, Confidence, Critical
4. **JSON (.json)** — Full pipeline output. Powers frontend interactive report.

---

## 4. Data Models

### Input

```python
class ScopeGapRequest:
    project_id: int
    trade: str
    set_ids: Optional[list[int]] = None
    session_id: Optional[str] = None
```

### Pipeline Items

```python
class ScopeItem:
    id: str                          # uuid
    text: str                        # scope description
    drawing_name: str                # "E-103"
    drawing_title: Optional[str]     # "Power Plan Level 2"
    page: int                        # page/record number
    source_snippet: str              # 5-15 word verbatim quote
    confidence: float                # 0.0-1.0
    csi_hint: Optional[str]          # if obvious from text
    source_record_id: Optional[str]  # MongoDB _id

class ClassifiedItem(ScopeItem):
    trade: str                       # "Electrical"
    csi_code: str                    # "26 24 16"
    csi_division: str                # "26 - Electrical"
    classification_confidence: float
    classification_reason: str

class AmbiguityItem:
    id: str
    scope_text: str
    competing_trades: list[str]
    severity: str                    # high | medium | low
    recommendation: str
    source_items: list[str]          # scope item IDs
    drawing_refs: list[str]

class GotchaItem:
    id: str
    risk_type: str                   # hidden_cost | coordination | missing_scope | spec_conflict
    description: str
    severity: str                    # high | medium | low
    affected_trades: list[str]
    recommendation: str
    drawing_refs: list[str]

class CompletenessReport:
    drawing_coverage_pct: float
    csi_coverage_pct: float
    hallucination_count: int
    overall_pct: float
    missing_drawings: list[str]
    missing_csi_codes: list[str]
    hallucinated_items: list[str]
    is_complete: bool                # overall >= 95.0
    attempt: int

class QualityReport:
    accuracy_score: float
    corrections: list[QualityCorrection]
    validated_items: list[ClassifiedItem]
    removed_items: list[str]
    summary: str

class QualityCorrection:
    item_id: str
    field: str                       # trade | csi_code | text
    old_value: str
    new_value: str
    reason: str
```

### Pipeline Output

```python
class ScopeGapResult:
    project_id: int
    project_name: str
    trade: str
    items: list[ClassifiedItem]
    ambiguities: list[AmbiguityItem]
    gotchas: list[GotchaItem]
    completeness: CompletenessReport
    quality: QualityReport
    documents: DocumentSet
    pipeline_stats: PipelineStats

class PipelineStats:
    total_ms: int
    attempts: int
    tokens_used: int
    estimated_cost_usd: float
    per_agent_timing: dict[str, int]
    records_processed: int
    items_extracted: int

class DocumentSet:
    word_path: Optional[str]         # S3 presigned URL or local path
    pdf_path: Optional[str]
    csv_path: Optional[str]
    json_path: Optional[str]
```

### Session Models

```python
class ScopeGapSession:
    id: str
    user_id: Optional[str]
    project_id: int
    trade: str
    set_ids: Optional[list[int]]
    created_at: datetime
    updated_at: datetime
    runs: list[PipelineRun]                    # run history (max 10)
    ambiguity_resolutions: dict[str, str]      # {ambiguity_id: assigned_trade}
    gotcha_acknowledgments: list[str]          # acknowledged gotcha IDs
    ignored_items: list[str]                   # ignored item IDs
    messages: list[SessionMessage]             # follow-up chat history (max 20)
    latest_result: Optional[ScopeGapResult]

class PipelineRun:
    run_id: str
    job_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    status: str                                # completed | partial | failed
    attempts: int
    completeness_pct: float
    items_count: int
    ambiguities_count: int
    gotchas_count: int
    token_usage: int
    cost_usd: float
    documents: Optional[DocumentSet]

class SessionMessage:
    role: str                                  # user | assistant
    content: str
    timestamp: datetime
    context: Optional[str]                     # scope_review | ambiguity | gotcha
```

---

## 5. File Structure

```
construction-intelligence-agent/
├── scope_pipeline/                          ← NEW MODULE (all new code)
│   ├── __init__.py
│   ├── orchestrator.py                      ← Master pipeline controller
│   ├── models.py                            ← All Pydantic models above
│   ├── config.py                            ← Pipeline-specific settings
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py                    ← Abstract base: retry, logging, timing
│   │   ├── extraction_agent.py              ← Agent 1
│   │   ├── classification_agent.py          ← Agent 2
│   │   ├── ambiguity_agent.py               ← Agent 3
│   │   ├── gotcha_agent.py                  ← Agent 4
│   │   ├── completeness_agent.py            ← Agent 5 (pure Python)
│   │   └── quality_agent.py                 ← Agent 6
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_agent.py                ← Agent 7: Word/PDF/CSV/JSON
│   │   ├── job_manager.py                   ← Background job tracking
│   │   ├── session_manager.py               ← 3-layer session persistence
│   │   ├── chat_handler.py                  ← Follow-up Q&A about reports
│   │   └── progress_emitter.py              ← SSE event streaming
│   └── routers/
│       ├── __init__.py
│       └── scope_gap.py                     ← All API endpoints
├── existing files unchanged...
```

### Existing Files Modified (minimal)

| File | Change | Lines |
|------|--------|-------|
| `main.py` | Import + register scope_gap router, init pipeline in lifespan | ~15 lines |
| `config.py` | Add pipeline env vars to Settings class | ~20 lines |
| **Total** | | **~35 lines** |

---

## 6. Job Manager

- **In-memory** job tracking with asyncio.Task execution
- **Semaphore(3)** — max 3 concurrent pipelines
- **Progress queues** — per-job asyncio.Queue for SSE streaming
- **Hybrid routing** — <2000 records: blocking. >=2000: background job (auto or user choice)
- **Record count** — single lightweight API call (page 1 only) to determine routing

### Job States

`queued → running → completed | partial | failed | cancelled`

- **partial** = <100% after 3 attempts. User can call `/continue` to resume.
- **cancelled** = user called DELETE. In-flight LLM calls complete but result discarded.

---

## 7. Session Management

### 3-Layer Persistence

| Layer | Backend | TTL | Max | Read Latency |
|-------|---------|-----|-----|-------------|
| L1 | In-memory TTLCache | 1 hour | 100 sessions | ~1us |
| L2 | Redis | 7 days | Unlimited | ~0.5ms |
| L3 | S3 | Permanent | Unlimited | ~50ms |

### Session Key

`{project_id}_{trade_lowercase}` (e.g., `7298_electrical`)
With set_ids: `7298_electrical_sets_4730_4731`

### Session Lifecycle

1. First request creates session → persisted to all 3 layers
2. Pipeline runs stored in `session.runs[]` (max 10)
3. User decisions (ambiguity resolutions, ignored items) persisted
4. Follow-up chat messages stored in `session.messages[]` (max 20)
5. Re-runs reuse session — previous results inform current run
6. Resolved ambiguities NOT re-flagged on subsequent runs

### Follow-up Chat

`POST /api/scope-gap/sessions/{id}/chat` answers questions about the scope report using the latest result as context. Supports SSE streaming.

---

## 8. Backpropagation Logic

```
Attempt 1: Full extraction → all 3 parallel agents → completeness check
  → If >= 95%: proceed to quality + document (DONE)
  → If < 95%: identify gaps

Attempt 2: Targeted re-extraction (only missing drawings/CSI) → merge with attempt 1 results
  → Parallel agents on new items only → completeness check
  → If >= 95%: proceed (DONE)
  → If < 95%: one more try

Attempt 3: Final targeted attempt → merge → completeness check
  → Regardless of result: proceed to quality + document
  → If < 95%: return as "partial" with % remaining + ask user to /continue
```

**Merge strategy:** New items added to existing set. Duplicates removed by source_record_id. Hallucinated items from previous attempts removed if still not in source data.

---

## 9. SSE Progress Events

```
event: pipeline_start     → {"attempt": 1, "total_records": 11360}
event: agent_start        → {"agent": "extraction", "message": "Extracting..."}
event: agent_complete     → {"agent": "extraction", "elapsed_ms": 62000, "items": 847}
event: agent_start        → {"agent": "classification", ...}  (3 agents start simultaneously)
event: agent_start        → {"agent": "ambiguity", ...}
event: agent_start        → {"agent": "gotcha", ...}
event: agent_complete     → {"agent": "classification", ...}
event: agent_complete     → {"agent": "ambiguity", "items": 12}
event: agent_complete     → {"agent": "gotcha", "items": 7}
event: completeness       → {"attempt": 1, "pct": 87.3, "missing": ["E-104","E-107"]}
event: backpropagation    → {"attempt": 2, "reason": "2 drawings missing"}
event: completeness       → {"attempt": 2, "pct": 98.6, "is_complete": true}
event: agent_complete     → {"agent": "quality", "accuracy": 0.972}
event: agent_complete     → {"agent": "document", "formats": ["docx","pdf","csv","json"]}
event: pipeline_complete  → {full ScopeGapResult}
```

---

## 10. Environment Variables (New)

```env
SCOPE_GAP_MAX_CONCURRENT_JOBS=3
SCOPE_GAP_COMPLETENESS_THRESHOLD=95.0
SCOPE_GAP_MAX_ATTEMPTS=3
SCOPE_GAP_RECORD_THRESHOLD=2000
SCOPE_GAP_MODEL=gpt-4.1
SCOPE_GAP_EXTRACTION_MAX_TOKENS=8000
SCOPE_GAP_CLASSIFICATION_MAX_TOKENS=4000
SCOPE_GAP_QUALITY_MAX_TOKENS=4000
```

### New Dependency

```
reportlab>=4.0    # PDF generation
```

---

## 11. S3 Storage Structure (New Paths)

```
agentic-ai-production/
└── construction-intelligence-agent/
    ├── scope_gap_reports/
    │   └── {ProjectName}_{ProjectID}/
    │       └── {Trade}/
    │           └── {timestamp}_{job_id}/
    │               ├── scope_report.docx
    │               ├── scope_report.pdf
    │               ├── scope_items.csv
    │               └── scope_full.json
    ├── scope_gap_sessions/
    │   └── {user_id}/
    │       └── {project}_{trade}.json
    ├── scope_gap_jobs/
    │   └── {job_id}.json
    ├── generated_documents/          ← existing (unchanged)
    ├── conversation_memory/          ← existing (unchanged)
    └── api_logs/                     ← existing (unchanged)
```

---

## 12. Production Review (12-Point)

### 1. Scaling
- Semaphore(3) for concurrent pipelines
- Auto-background for >=2000 records
- Horizontal: Redis-backed queue in v2
- LLM rate limits: max 9 simultaneous API calls (3 parallel agents x 3 jobs)

### 2. Optimization
- Parallel fan-out (3 agents simultaneously)
- Parallel document generation (4 formats)
- Parallel S3 uploads
- Incremental backpropagation (only missing items)
- Pure Python completeness check (~1ms)
- Existing cache reuse for API data

### 3. Performance Metrics
- Per-agent timing, token usage, cost tracking
- Pipeline-level: total_ms, attempts, items_extracted, completeness_pct
- All metrics in PipelineStats, emitted via SSE, persisted in session

### 4. Request Handling
- Rate limiting: 10/min per user for pipeline endpoints
- Backpressure: semaphore queue, visible via job list API
- Timeout: 5 min blocking, unlimited background
- Cancellation: asyncio.Task.cancel()
- Idempotency: same params within 60s returns cached result
- Error recovery: per-agent retry, partial result on failure

### 5. Security
- Prompt injection defense: explicit delimiters, instruction hierarchy
- LLM output: strict Pydantic JSON validation
- API keys: .env only, never in responses/logs
- S3: presigned URLs, 1-hour expiry
- Auth: Nginx auth_request (Phase 10)
- Input validation: Pydantic-enforced types
- Cost abuse: max concurrent + rate limiting
- Session isolation: user_id scoped, no cross-user access

### 6. SDLC
- Branch: `feature/scope-gap-pipeline`
- Commits: conventional (`feat(scope-gap): ...`)
- Testing: unit (mocked LLM) + integration (real API) + E2E
- Coverage: 80%+ target
- Review: code-reviewer agent per implementation step

### 7. Compliance
- Data stays in MongoDB (read-only). Generated docs in S3 (encrypted at rest).
- Audit logging: every run logged with who/what/when/result/cost.
- No PII. OpenAI API data not used for training.

### 8. Disaster Recovery
- RPO: zero data loss for completed pipelines (synchronous S3 write)
- RTO: ~30s (systemd auto-restart)
- Redis crash: S3 fallback. S3 outage: local fallback. OpenAI outage: partial result.

### 9. Support
- Clear error messages for users
- Structured JSON logs per-agent
- Job inspection API with full progress tree
- PipelineStats in every result

### 10. Maintenance
- Agent prompts: string constants, update + restart
- Model upgrades: env var change + restart
- Trade list: from user request (no hardcoded list)
- 1 new dependency (reportlab)
- Session cleanup: S3 lifecycle 90-day archive

### 11. Network & Security
- TLS everywhere (existing Let's Encrypt)
- Port 8003 internal only (Nginx proxy)
- Auth: JWT validation via auth_request
- Rate limiting at Nginx + application layer
- No new inbound ports

### 12. Resource Management
- Memory: chunked processing, token budget enforcement, L1 cache capped
- CPU: document gen in thread pool, non-blocking
- LLM cost: per-job tracking, incremental backpropagation
- Storage: S3 lifecycle policies
- Monitoring: v1 structured logs + health. v2 Prometheus/Grafana.

---

## 13. Integration with Existing System

| Component | Reuse Strategy | Changes |
|-----------|---------------|---------|
| APIClient | Import directly | 0 changes |
| CacheService | New cache keys `scope_gap:*` | 0 changes |
| SessionService | Separate ScopeGapSessionManager (not reusing chat sessions) | 0 changes |
| SQL Service | Project name lookup for doc headers | 0 changes |
| S3 Utils | Upload/download for docs + sessions | 0 changes |
| TokenTracker | Reuse for cost accounting | 0 changes |
| Config | Extend Settings class with pipeline vars | ~20 lines |
| main.py | Register router + init pipeline in lifespan | ~15 lines |

**Total existing code changes: ~35 lines across 2 files.**

---

## 14. What This Spec Does NOT Cover (Deferred)

| Feature | Deferred To | Reason |
|---------|-------------|--------|
| Template/preset system | V2 | Ship pipeline first |
| Drawing Viewer frontend | Frontend team | Backend provides JSON data |
| Multi-trade batch processing | V2 | Single-trade MVP |
| PDF upload workflow | V2 | MongoDB data source first |
| Prometheus/Grafana monitoring | V2 | Structured logs sufficient for v1 |
| Redis-backed job queue (Celery/ARQ) | V2 | In-memory sufficient for single VM |
| Admin API for trade/CSI management | V2 | Config file sufficient for v1 |
| Interactive web report frontend | Frontend team | Backend provides JSON |

---

## 15. Success Criteria

| Metric | Target |
|--------|--------|
| Pipeline latency (11k records) | < 5 minutes |
| Drawing coverage | >= 95% |
| CSI coverage | >= 95% |
| Hallucination rate | < 2% of items |
| Quality accuracy score | >= 0.95 |
| Concurrent pipelines | 3 simultaneous |
| Document formats | 4 (Word, PDF, CSV, JSON) |
| Session persistence | Survives server restart |
| Existing tests | All pass (zero regression) |
| New test coverage | >= 80% |
