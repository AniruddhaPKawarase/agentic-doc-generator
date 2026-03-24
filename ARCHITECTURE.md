# Construction Intelligence Agent — Complete Architecture Guide

## Table of Contents
1. [System Overview](#1-system-overview)
2. [End-to-End Request Flow](#2-end-to-end-request-flow)
3. [Full Architecture Diagram](#3-full-architecture-diagram)
4. [Component Reference](#4-component-reference)
5. [Context Window Management](#5-context-window-management)
6. [Caching Strategy](#6-caching-strategy)
7. [Hallucination Guard & Rollback](#7-hallucination-guard--rollback)
8. [Session Memory](#8-session-memory)
9. [Token Tracking](#9-token-tracking)
10. [Streaming Architecture](#10-streaming-architecture)
11. [Document Generation — Exhibit Format](#11-document-generation--exhibit-format)
12. [Testing Module (Excel-based)](#12-testing-module-excel-based)
13. [Scalability Design](#13-scalability-design)
14. [API Reference](#14-api-reference)
15. [Setup Guide](#15-setup-guide)

---

## 1. System Overview

The Construction Intelligence Agent converts raw MongoDB drawing-text data into
professional Word documents (scopes, exhibits, reports, takeoffs) via a fully
agentic pipeline:

```
User selects Project → User asks query → Intent Detection → Trade-filtered
Data Retrieval → Context Compression → LLM Generation → Hallucination Guard
→ Word Document → Download Link
```

**Key design constraints addressed:**

| # | Constraint | Solution |
|---|---|---|
| 1 | Latency < 500 ms (for cached) | Two-level cache + parallel async phases |
| 2 | Accuracy > 70 % | Groundedness scoring + clarification rollback |
| 3 | Context window management | Token-budgeted context builder + trade-filter |
| 4 | Token tracking | Per-call + per-session counters with cost estimates |
| 5 | Hallucination rollback | Heuristic guard → follow-up questions |
| 6 | Session memory | TTL-backed conversation history per session |
| 7 | Memory caching | Sliding-window summary to avoid history bloat |
| 8 | Response caching | Redis L2 + in-process L1 (cachetools TTLCache) |
| 9 | Scalability | Stateless FastAPI + Redis + parallel API fetches |
| 10 | Streaming | SSE endpoint `/api/chat/stream` |

---

## 2. End-to-End Request Flow

```
POST /api/chat  {project_id, query, session_id, generate_document}
│
├─ Phase 1 (parallel asyncio.gather) ──────────────────────────────────────
│    ├─ SessionService.get_or_create()      load or create session
│    ├─ Cache.get(pre_cache_key)            check query cache (no-trade key)
│    └─ DataAgent.get_project_metadata()   fetch trades + CSI divisions
│         └─ APIClient → Redis cache or MongoDB API
│
├─ Early return if cached ──────────────────────────────────────────────────
│
├─ Phase 2 (parallel asyncio.gather) ──────────────────────────────────────
│    ├─ IntentAgent.detect_sync()          keyword-only, <1 ms
│    │    → preliminary trade
│    ├─ DataAgent.prepare_context()        with preliminary trade
│    │    ├─ APIClient.get_all_drawing_data_for_trade()
│    │    │    └─ parallel page fetches → Redis cache
│    │    ├─ APIClient.get_unique_text_values()
│    │    └─ ContextBuilder.build()
│    │         ├─ group_drawing_records()
│    │         ├─ rank_trade_texts()
│    │         └─ truncate_to_token_budget()  ← context window guard
│    ├─ IntentAgent.detect()              full detect (LLM fallback if needed)
│    └─ Cache.get(prelim_cache_key)       check with preliminary trade key
│
├─ If trade changed: rebuild context for corrected trade ──────────────────
│
├─ GenerationAgent._generate_with_openai() ────────────────────────────────
│    ├─ Build system_prompt (trade + task + metadata)
│    ├─ Build user_message (history summary + context + query)
│    ├─ TokenTracker.enforce_context_budget()
│    └─ OpenAI chat.completions.create()
│
├─ HallucinationGuard.check() ─────────────────────────────────────────────
│    ├─ Guard 1: empty/short response
│    ├─ Guard 2: refusal phrase detection
│    ├─ Guard 3: specific claim verification vs. source context
│    └─ Guard 4: trade mention check
│         → recommendation: proceed | clarify | reject
│
├─ If needs_clarification: replace answer with clarification questions ─────
│
├─ DocumentGenerator.generate_sync() (in thread pool) ─────────────────────
│    ├─ ExhibitDocumentGenerator — styled Word document
│    └─ Save to generated_docs/ → return download URL
│
└─ Parallel persist ────────────────────────────────────────────────────────
     ├─ SessionService.add_turn()          save user + assistant messages
     ├─ TokenTracker.accumulate()          update session token stats
     └─ Cache.set(response)               cache full response (if reliable)
```

---

## 3. Full Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser / CLI)                       │
│                                                                      │
│  POST /api/chat          POST /api/chat/stream   GET /api/documents  │
└─────────────┬───────────────────┬──────────────────────┬────────────┘
              │                   │                      │
              ▼                   ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Application (main.py)                   │
│                                                                      │
│  ┌────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │
│  │ ChatRouter │  │ StreamRouter   │  │ DocumentsRouter            │ │
│  │ /api/chat  │  │ /api/chat/     │  │ /api/documents/{id}/       │ │
│  │            │  │  stream (SSE)  │  │  download                  │ │
│  └─────┬──────┘  └───────┬────────┘  └────────────────────────────┘ │
│        │                 │                                           │
│        └────────┬─────────┘                                         │
│                 ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   GenerationAgent                            │   │
│  │                                                              │   │
│  │  process()  ─────── parallel phases ──────────────────────   │   │
│  │  process_stream()  ─ SSE async generator ─────────────────   │   │
│  └──┬──────────────┬────────────────┬──────────────────────────┘   │
│     │              │                │                               │
│     ▼              ▼                ▼                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────┐   │
│  │ Intent   │ │  Data    │ │       Services                   │   │
│  │  Agent   │ │  Agent   │ │                                  │   │
│  │          │ │          │ │  SessionService  (conversation)  │   │
│  │ keyword  │ │ Context  │ │  TokenTracker    (cost tracking) │   │
│  │  +LLM    │ │ Builder  │ │  HallucinationGuard (rollback)   │   │
│  │ fallback │ │ (trade   │ │  ExhibitDocumentGenerator        │   │
│  └──────────┘ │  filter) │ │  CacheService    (L1+L2)        │   │
│               └─────┬────┘ └──────────────────────────────────┘   │
│                     │                                               │
└─────────────────────┼───────────────────────────────────────────────┘
                      │
         ┌────────────┴──────────┐
         │                       │
         ▼                       ▼
  ┌─────────────┐        ┌──────────────┐
  │  MongoDB    │        │    Redis     │
  │  HTTP APIs  │        │  L2 Cache    │
  │             │        │  Session     │
  │ 1. Drawing  │        │  Store       │
  │    data     │        └──────────────┘
  │ 2. CSI divs │
  │ 3. Texts    │
  │ 4. Trades   │
  └─────────────┘
```

---

## 4. Component Reference

### agents/intent_agent.py
- `detect_sync(query)` — keyword-only, <1 ms, no I/O
- `detect(query)` — keyword first; falls back to LLM if confidence < 0.7
- Maps trade name → CSI division codes
- Updates available_trades dynamically from project metadata

### agents/data_agent.py
- `prepare_context(project_id, intent)` — main entry: validate trade + build context
- `get_project_metadata(project_id)` — parallel fetch of trades + CSI

### agents/generation_agent.py
- `process(request)` — full pipeline, returns `ChatResponse`
- `process_stream(request)` — SSE async generator, yields `{type, delta/response}`

### services/api_client.py
- Wraps 4 MongoDB HTTP APIs with Redis caching and shape-tolerant parsing
- `get_all_drawing_data_for_trade()` — parallel page fetches
- `fetch_project_metadata()` — parallel trades + CSI in one call

### services/context_builder.py
- `build(project_id, trade, csi, query, budget)` — token-budgeted context
- Groups drawing records, ranks texts by trade relevance, truncates to budget

### services/cache_service.py
- L1: cachetools.TTLCache (in-process, ~1 µs reads)
- L2: Redis (network, ~0.5 ms reads)
- Graceful fallback to in-process only if Redis unavailable

### services/hallucination_guard.py
- Pure heuristic — no extra LLM call (keeps latency low)
- Extracts specific claims (dimensions, codes, part numbers)
- Groundedness = fraction of claims found in source context
- `recommendation`: proceed | clarify | reject

### services/exhibit_document_generator.py (NEW)
- Generates styled Word exhibit matching sample file format
- Cover block: project metadata, exhibit title, date
- Scope content: parses LLM markdown → Word headings/bullets/tables
- Drawing reference table: Drawing No | Source Trade | CSI | Scope Note
- Alternating row shading, branded colours (dark blue #1E3A5F / mid blue #2E75B6)

### services/session_service.py
- Per-session conversation history stored in Redis with TTL
- Sliding-window summary prefix (oldest messages summarised, not dropped)
- `build_history_messages(session, last_n=8)` — last N turns for LLM

### services/token_tracker.py
- Per-call: `record_usage(input, output)` → `TokenUsage` with cost_usd
- Per-session: `accumulate_session_tokens()` → running totals in Redis
- `enforce_context_budget()` — trims user_message to fit token limit

---

## 5. Context Window Management

**Problem:** MongoDB trade data can be millions of tokens.

**Solution — 4-layer filter:**

```
MongoDB API response (potentially 100 000+ records)
    ↓
Layer 1: Trade filter — only records where trade == detected_trade
         (drawing_max_records = 500 by default)
    ↓
Layer 2: CSI division filter — only records matching CSI codes for trade
    ↓
Layer 3: Ranking — rank_trade_texts() scores texts by query similarity
         (context_max_unique_lines = 80 top texts kept)
    ↓
Layer 4: Token budget truncation — truncate_to_token_budget(budget=20000)
    ↓
LLM receives ≤ 20 000 context tokens
```

**Config knobs** (in `.env`):
```
DRAWING_MAX_RECORDS=500
CONTEXT_MAX_UNIQUE_LINES=80
MAX_CONTEXT_TOKENS=20000
MAX_OUTPUT_TOKENS=1500
```

---

## 6. Caching Strategy

```
Query arrives
    │
    ├─ L1 in-process TTLCache  →  ~1 µs  (hot path)
    │
    ├─ L2 Redis                →  ~0.5 ms (warm path)
    │
    └─ Full pipeline           →  seconds (cold path)
         └─ Result cached to L1 + L2

Cache keys:
  api:{type}:{project_id}[:{suffix}]   — API response data (5-30 min TTL)
  query:{project_id}:{trade}:{hash}    — Full ChatResponse (60 min TTL)
  session:{session_id}                 — Conversation history (24 hr TTL)
```

**Repetitive queries:** same project + same trade + same (normalised) query → instant cache hit, zero LLM cost.

---

## 7. Hallucination Guard & Rollback

**Trigger:** `groundedness_score < 0.70` (configurable via `HALLUCINATION_CONFIDENCE_THRESHOLD`)

**What happens:**
1. LLM answer is discarded
2. `needs_clarification: true` returned in response
3. 2-3 targeted follow-up questions sent back to user
4. No Word document generated for this turn
5. Response is NOT cached (forces fresh LLM call next time)

**Why heuristic (not a second LLM call):**
A second LLM call would double latency. Heuristic check takes < 5 ms.

**Claim patterns checked:**
- Drawing sheet refs: `E-101`, `A-011`
- Electrical values: `480V`, `20 amp`
- CSI codes: `26 - Electrical`
- Material sizes: `2x4`, `3/4"`, `#4 rebar`

---

## 8. Session Memory

```
Session (Redis, 24h TTL)
├── messages: [{role, content, timestamp, metadata}]  ← full history
├── token_summary: {total_input, total_output, call_count}
└── session_id, project_id, created_at, updated_at

LLM receives:
  ├── history_summary (oldest turns → compressed prefix)
  └── last 8 turns (verbatim)
```

**Memory caching guard:** Sliding window ensures old messages are summarised,
not dropped, so the model retains project context without token bloat.

---

## 9. Token Tracking

Every LLM call records:
```json
{
  "input_tokens": 4521,
  "output_tokens": 892,
  "total_tokens": 5413,
  "cost_usd": 0.003234
}
```

Session totals (accumulated in Redis):
```json
{
  "session_id": "abc123",
  "total_input": 18234,
  "total_output": 3412,
  "total_tokens": 21646,
  "total_cost_usd": 0.0129,
  "call_count": 4
}
```

Endpoint: `GET /api/sessions/{session_id}/tokens`

---

## 10. Streaming Architecture

```
POST /api/chat/stream
    │
    ├─ Phases 1 & 2 run identically to non-streaming
    │
    ├─ SSE event: {"type": "metadata", "intent": {...}, "trade": "Electrical"}
    │
    ├─ client.chat.completions.stream() ← OpenAI streaming call
    │    └─ For each chunk:
    │         SSE event: {"type": "token", "delta": "...text..."}
    │
    ├─ HallucinationGuard + DocumentGeneration (after stream completes)
    │
    └─ SSE event: {"type": "done", "response": <full ChatResponse JSON>}

Cached responses are "replayed" by chunking the cached answer in 80-char blocks.
```

**Client usage (JavaScript):**
```js
const response = await fetch('/api/chat/stream', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ project_id: 7276, query: 'Generate exhibit for electrical' })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value);
  const lines = buffer.split('\n');
  buffer = lines.pop();
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6));
      if (event.type === 'token') appendText(event.delta);
      if (event.type === 'done') handleFinalResponse(event.response);
    }
  }
}
```

---

## 11. Document Generation — Exhibit Format

`ExhibitDocumentGenerator` (`services/exhibit_document_generator.py`) produces
Word files styled after the sample exhibit files:

```
┌─────────────────────────────────────────────────────┐
│ iFieldSmart | Construction Intelligence Platform    │
│─────────────────────────────────────────────────────│
│ Exhibit — Electrical Scope of Work         [H1 18pt]│
│                                                     │
│ Project:      Granville Project                     │
│ Trade:        Electrical                            │
│ Document Type: Exhibit                              │
│ Prepared:     March 03, 2026                        │
│ Prepared by:  AI Construction Intelligence          │
│ Status:       DRAFT — Verify against source drawings│
│─────────────────────────────────────────────────────│
│                                                     │
│ ## Scope Summary                          [Heading] │
│ ...LLM-generated summary paragraph...              │
│                                                     │
│ ## Scope of Work by Drawing               [Heading] │
│ **Drawing E-101 — Electrical**            [Bold]   │
│ • Furnish and install panel LP-1...                │
│ • Coordinate with structural for...                │
│                                                     │
│ ## Scope of Work — Drawing Reference Table         │
│ ┌──────────┬──────────────┬──────────────┬───────┐ │
│ │Drawing No│ Source Trade │ CSI Division │ Note  │ │  ← dark blue header
│ ├──────────┼──────────────┼──────────────┼───────┤ │
│ │ E-101    │ Electrical   │ 26-Electrical│ ...   │ │
│ │ A-011    │ Architecture │ 26-Electrical│ ...   │ │  ← alternating grey
│ └──────────┴──────────────┴──────────────┴───────┘ │
│─────────────────────────────────────────────────────│
│ iFieldSmart | Granville Project | Electrical | DRAFT│  ← footer
└─────────────────────────────────────────────────────┘
```

---

## 12. Testing Module (Excel-based)

### Purpose
Test scope generation without a live MongoDB connection using
`Scope Gap - Electrical.xlsx` as a mock data source.

### Architecture
```
tests/excel_loader.py    — Reads Excel, provides trade-filtered context
tests/test_scope.py      — Full pipeline CLI: intent → context → LLM → Word doc
```

### Usage

**Interactive conversation (default):**
```bash
python tests/test_scope.py
```

**Single query:**
```bash
python tests/test_scope.py --query "Generate exhibit for electrical"
python tests/test_scope.py --query "Create scope for plumbing" --stream
python tests/test_scope.py --query "Generate full report on HVAC" --no-doc
```

**Batch run all trades:**
```bash
python tests/test_scope.py --batch
```

**Custom Excel file:**
```bash
python tests/test_scope.py --excel path/to/MyProject.xlsx
```

### Sample session
```
You: Generate exhibit for electrical
→ Intent: trade=Electrical, doc_type=exhibit
→ Context: 52 drawings, 1306 records → 41 KB
→ LLM: gpt-4.1-mini, 4521 in / 892 out tokens, $0.003
→ Groundedness: 84%
→ Document: generated_docs/Exhibit_Electrical_exhibit_abc12345.docx

You: What panels are mentioned?
→ (uses session history) → answers with specific panel references

You: tokens
→ Session abc1 | Input: 5413 | Output: 1120 | Total: 6533 | Est. cost: $0.0039
```

### Excel data format expected
| Column | Description |
|--------|-------------|
| Project Name | Project identifier |
| Trade Name | Drawing's originating trade |
| Drawing No | Sheet number (e.g., E-101) |
| Note | Scope/drawing note text |
| Scope Trades | Comma-separated trades this note applies to |
| CSI Division | Comma-separated CSI codes |

---

## 13. Scalability Design

| Concern | Solution |
|---------|---------|
| Hundreds of thousands of records | Trade-filter API param → server-side filtering in MongoDB |
| Large page counts | Parallel page fetches (asyncio.gather) |
| Many concurrent users | Stateless FastAPI + Redis session store |
| Token explosion | 4-layer context filter (trade→CSI→rank→budget) |
| Repeated queries | Redis cache with 60-min TTL |
| Slow doc generation | asyncio.to_thread() — non-blocking |
| High drawing_max_records | Increase drawing_page_size + drawing_max_records in .env |

**For 100 000+ record projects:**
1. Set `DRAWING_DATA_PATH` with a server-side `trade` filter parameter
2. Increase `DRAWING_PAGE_SIZE` to 1000 with larger `DRAWING_MAX_RECORDS`
3. The parallel page fetching still runs in O(log N) round trips
4. Redis caches the filtered result for 5 min (TTL tunable)

---

## 14. API Reference

### POST /api/chat
```json
// Request
{
  "project_id": 7276,
  "query": "Generate exhibit for electrical",
  "session_id": null,
  "generate_document": true
}

// Response
{
  "session_id": "uuid",
  "answer": "## Electrical Scope of Work...",
  "document": {
    "file_id": "uuid",
    "filename": "Exhibit_Electrical_exhibit_abc12345.docx",
    "download_url": "http://localhost:8000/api/documents/uuid/download",
    "trade": "Electrical",
    "size_bytes": 42031
  },
  "intent": {"trade": "Electrical", "document_type": "exhibit", "confidence": 0.95},
  "token_usage": {"input_tokens": 4521, "output_tokens": 892, "cost_usd": 0.003},
  "groundedness_score": 0.84,
  "needs_clarification": false,
  "pipeline_ms": 3240,
  "cached": false
}
```

### POST /api/chat/stream
Same request body. Response is `text/event-stream` (SSE).

### GET /api/sessions/{session_id}/history
Returns full conversation history with timestamps.

### GET /api/sessions/{session_id}/tokens
Returns cumulative token usage and estimated cost for the session.

### DELETE /api/sessions/{session_id}
Clears session history.

### GET /api/documents/{file_id}/download
Returns the generated Word file as a downloadable attachment.

### GET /api/projects/{project_id}/context
Returns available trades, CSI divisions, and data counts for a project.

---

## 15. Setup Guide

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env:
#   OPENAI_API_KEY=sk-...
#   API_BASE_URL=https://mongo.ifieldsmart.com
#   API_AUTH_TOKEN=...
#   DRAWING_DATA_PATH=/api/drawingText/list
#   REDIS_URL=redis://localhost:6379/0

# 3. Start Redis (optional but recommended)
docker run -d -p 6379:6379 redis:alpine

# 4. Run the API server
python main.py
# or: uvicorn main:app --reload

# 5. Run the Excel test module (no MongoDB needed)
python tests/test_scope.py
python tests/test_scope.py --query "Generate exhibit for electrical"
python tests/test_scope.py --batch
```
