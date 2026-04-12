# Latency Optimization Design Spec — Construction Intelligence Agent

**Date:** 2026-04-12  
**Approach:** Smart Fetch + Tiered LLM + Warm Cache  
**Target:** Both endpoints under 1-2 minutes (from ~10 min current)  
**API Contract:** No breaking changes to `ChatRequest`/`ChatResponse`  
**Deployment:** Canary — sandbox first, then production  

---

## 1. User Story & Problem Statement

### User Story
As a construction estimator using the VCS AI agent, I want scope generation and chat responses to return in under 2 minutes, so I can iterate quickly on project scope analysis without waiting 10 minutes per query.

### Root Cause Analysis

The ~10 minute latency breaks down as follows:

| Component | Current Latency | Root Cause |
|-----------|----------------|------------|
| API Data Fetch | ~50s (parallel) | 228 paginated calls at 50 records/page, when API supports single bulk call in 20-30s |
| LLM Generation (chat) | ~2.4 min | 10,000 max output tokens on gpt-4.1-mini |
| LLM Intent + Follow-up | ~30s | Using gpt-4.1-mini for lightweight tasks |
| Scope Gap Backpropagation | ~60-300s | 95% completeness threshold triggers 3-5 retry rounds |
| Scope Gap Quality + Document | ~40s | Sequential execution when parallelizable |
| No persistent cache | variable | L1 in-memory only; every restart = cold cache |

### Key Discovery
The MongoDB API (`mongo.ifieldsmart.com`) returns **all records in a single call** (20-30s) when called without pagination parameters. Our code unnecessarily forces pagination (skip/limit/page), splitting one 25s call into 228 paginated calls.

---

## 2. Clarifying Questions & Answers

| # | Question | Answer | Impact on Design |
|---|----------|--------|-----------------|
| Q1 | Which endpoint? | Both (chat + scope gap) | Optimize both pipelines |
| Q2 | Target latency? | Under 1-2 minutes | Aggressive but achievable |
| Q3 | Dataset size? | All sizes (small to 11k+ records) | Must handle worst-case electrical |
| Q4 | MongoDB API control? | Partially; API returns 20-30s in Postman | Use bulk fetch, skip pagination |
| Q5 | Redis in prod? | No (L1 in-memory only) | Add disk-backed L2 cache |
| Q6 | Faster LLM? | Selective (intent + follow-up only) | gpt-4.1-nano for lightweight calls |
| Q7 | Quality degradation? | Minor OK (shorter answers) | Reduce max_output_tokens 10k -> 7k |
| Q8 | Pre-computation? | Hybrid (pre-compute data, fresh LLM) | Warm data cache with background refresh |
| Q9 | Streaming? | Yes, frontend supports SSE | Use /api/chat/stream for perceived speed |
| Q10 | Scope gap use case? | Real-time (user waits) | Aggressive pipeline optimization |
| Q11 | Concurrent users? | 5-20 moderate | Connection pool sufficient |
| Q12 | Slowest trades? | All equally slow | Universal optimization |
| Q13 | Backward compat? | No breaking changes | Add optional fields only |
| Q14 | Scope Gap UI? | Prototype, not active | Can restructure pipeline freely |
| Q15 | Deployment? | Canary (sandbox -> prod) | Deploy to 54.197.189.113 first |

---

## 3. Architecture: Five Optimization Layers

```
Layer 1: Smart Fetch          — Single bulk API call (50s -> 25s)
Layer 2: Tiered LLM           — gpt-4.1-nano for lightweight calls (30s -> 5s)
Layer 3: Token Reduction       — max_output_tokens 10k -> 7k (2.4min -> 1.5min)
Layer 4: Warm Data Cache       — Disk-backed L2 + background refresh
Layer 5: Pipeline Parallelism  — Quality || Document, force-extraction parallel
```

---

## 4. Layer 1: Smart Fetch (Single-Call API)

### Current Behavior
`api_client.py:_fetch_all_pages()` (line 420):
1. Fetches page 1 serially (no pagination params)
2. Discovers API page size = 50
3. Dispatches remaining pages in parallel batches (concurrency=30)
4. For 11,360 records: 228 pages / 30 concurrent = 8 rounds x 5.8s = ~50s

### New Behavior
Add `_fetch_bulk()` that attempts a single non-paginated call first:

```python
async def _fetch_bulk(
    self,
    project_id: int,
    trade: str,
    set_id: Optional[Union[int, str]] = None,
    endpoint_path: Optional[str] = None,
) -> Optional[list[dict[str, Any]]]:
    """
    Attempt to fetch ALL records in a single API call without pagination.
    Returns None if bulk fetch fails or times out (caller falls back to pagination).
    """
```

**Algorithm:**
1. Build params: `{projectId, trade}` + optional `{setId}` — NO skip/limit/page
2. Send request with `bulk_fetch_timeout` (60s, configurable)
3. If response is valid and contains records, return them
4. If timeout, error, or empty: return `None` (triggers fallback)

**Modified `_fetch_all_pages()` flow:**
```
_fetch_all_pages(project_id, trade, set_id):
  if settings.bulk_fetch_enabled:
    result = await _fetch_bulk(project_id, trade, set_id)
    if result is not None:
      return result  # Done in 20-30s
  # Fallback: existing parallel pagination
  ...existing code...
```

### Files Modified

| File | Change |
|------|--------|
| `services/api_client.py` | Add `_fetch_bulk()` method; modify `_fetch_all_pages()` to try bulk first |
| `config.py` | Add `bulk_fetch_enabled: bool = True`, `bulk_fetch_timeout: int = 60` |

### Config

```env
BULK_FETCH_ENABLED=true       # Try single-call fetch first
BULK_FETCH_TIMEOUT=60         # Timeout for bulk fetch (seconds)
```

### Rollback
Set `BULK_FETCH_ENABLED=false` in `.env` -> restart -> reverts to pagination-only.

---

## 5. Layer 2: Tiered LLM Routing

### Current Behavior
All LLM calls use `settings.openai_model` (gpt-4.1-mini) regardless of task complexity.

### New Behavior
Route lightweight tasks to gpt-4.1-nano:

| Call Site | File:Line | Current | New | Rationale |
|-----------|-----------|---------|-----|-----------|
| Intent fallback | `intent_agent.py:160` | `settings.openai_model` | `settings.intent_model` | Simple JSON classification, 500 tokens max |
| Follow-up questions | `generation_agent.py:918` | `settings.openai_model` | `settings.followup_model` | Short question generation, 400 tokens max |
| Main generation | `generation_agent.py:991` | `settings.openai_model` | `settings.openai_model` (unchanged) | Core quality-critical path |
| Scope gap agents | `scope_pipeline/config.py:68` | `scope_gap_model` | `scope_gap_model` (unchanged) | Core extraction accuracy |

### Files Modified

| File | Change |
|------|--------|
| `config.py` | Add `intent_model: str = "gpt-4.1-nano"`, `followup_model: str = "gpt-4.1-nano"` |
| `agents/intent_agent.py` | Replace `settings.openai_model` with `settings.intent_model` in `_llm_detect()` |
| `agents/generation_agent.py` | Replace `settings.openai_model` with `settings.followup_model` in `_generate_follow_up_questions()` |

### Config

```env
INTENT_MODEL=gpt-4.1-nano        # Fast model for intent detection
FOLLOWUP_MODEL=gpt-4.1-nano      # Fast model for follow-up questions
```

### Rollback
Set `INTENT_MODEL=gpt-4.1-mini` and `FOLLOWUP_MODEL=gpt-4.1-mini` -> restart.

---

## 6. Layer 3: Token Reduction

### Changes

| Setting | Current | New | Effect |
|---------|---------|-----|--------|
| `MAX_OUTPUT_TOKENS` | 10000 | 7000 | ~30% faster LLM generation |
| `NOTE_MAX_CHARS` | 300 | 200 | Smaller context = faster LLM processing |
| `API_TIMEOUT_SECONDS` | 30 | 60 | Allow bulk fetch to complete |
| `CACHE_TTL_SUMMARY_DATA` | 300 (5m) | 900 (15m) | Fewer redundant API calls |
| `PARALLEL_FETCH_CONCURRENCY` | 30 | 50 | Faster pagination fallback |

### Files Modified

| File | Change |
|------|--------|
| `.env` | Update values |
| `config.py` | Update defaults to match (so new deployments use optimized values) |

### Quality Impact
- `MAX_OUTPUT_TOKENS=7000`: Responses may be ~30% shorter. Still ~5,000 words, sufficient for scope documents.
- `NOTE_MAX_CHARS=200`: Slightly more aggressive note truncation. Drawing numbers and key terms preserved (truncation preserves first N chars).

---

## 7. Layer 4: Warm Data Cache (Disk-Backed L2)

### Current Behavior
- L1: `cachetools.TTLCache(maxsize=500, ttl=3600)` — in-memory, lost on restart
- L2: Redis — NOT installed in production
- Result: Every server restart = cold cache = full API fetch on first request

### New Behavior
Add disk-backed L2 cache that survives restarts:

```
Cache read:  L1 (memory, ~1us) -> L2 (disk, ~5ms) -> API fetch (~25s)
Cache write: Write to L1 + async write to L2 disk
```

**Implementation:**
- Cache directory: `{project_root}/.cache/` (configurable via `DISK_CACHE_DIR`)
- File format: `{cache_key_hash}.json` with metadata header (TTL, created_at)
- Cleanup: Background task purges expired files every 5 minutes
- Thread-safe: Use `asyncio.to_thread()` for disk I/O

**Background warm-up (lazy pre-computation):**
- After a successful API fetch + context build, schedule a background refresh at 80% of TTL
- Example: TTL=900s -> schedule refresh at 720s -> cache never goes cold for active projects
- Implemented via `asyncio.create_task()` with delay

### Files Modified

| File | Change |
|------|--------|
| `services/cache_service.py` | Add `DiskCache` class, integrate as L2, add background warm-up scheduler |
| `config.py` | Add `disk_cache_enabled: bool = True`, `disk_cache_dir: str = ".cache"`, `cache_warmup_enabled: bool = True` |
| `main.py` | Add cache cleanup task in lifespan startup |

### Config

```env
DISK_CACHE_ENABLED=true
DISK_CACHE_DIR=.cache
CACHE_WARMUP_ENABLED=true
CACHE_TTL_SUMMARY_DATA=900       # 15 minutes (raised from 5 min)
```

### Rollback
Set `DISK_CACHE_ENABLED=false` -> restart -> reverts to L1-only.

---

## 8. Layer 5: Scope Gap Pipeline Parallelism

### Current Behavior (orchestrator.py)

```
Data Fetch (sequential) -> Extraction (sequential batches)
  -> Classification | Ambiguity | Gotcha (parallel, line 195)
  -> Completeness (sequential)
  -> Quality (sequential)
  -> Document (sequential)
  -> Backpropagation loop (up to 5 attempts, 95% threshold)
```

Force-extraction (line 270-320): Sequential loop per missing drawing.

### New Behavior

```
Data Fetch (bulk) -> Extraction (sequential batches)
  -> Classification | Ambiguity | Gotcha (parallel, unchanged)
  -> Completeness (sequential, unchanged — must follow classification)
  -> Quality | Document (PARALLEL — document uses extraction results, not quality output)
  -> Backpropagation loop (up to 2 attempts, 90% threshold)
```

Force-extraction: Parallel batches of missing drawings via `asyncio.gather()`.

### Changes

| Change | File:Line | Current | New |
|--------|-----------|---------|-----|
| Quality \|\| Document | `orchestrator.py:~330` | Sequential | `asyncio.gather(quality_task, document_task)` |
| Force-extraction parallel | `orchestrator.py:270-320` | `for drawing in missing:` | `asyncio.gather(*[extract(d) for d in batch])` |
| Completeness threshold | `scope_pipeline/config.py:73` | 95.0 | 90.0 |
| Max attempts | `scope_pipeline/config.py:72` | 5 | 2 |

### Files Modified

| File | Change |
|------|--------|
| `scope_pipeline/orchestrator.py` | Parallelize quality + document; parallelize force-extraction batches |
| `scope_pipeline/config.py` | Update defaults: threshold=90.0, max_attempts=2 |

### Config

```env
SCOPE_GAP_COMPLETENESS_THRESHOLD=90.0   # was 95.0
SCOPE_GAP_MAX_ATTEMPTS=2                 # was 5
```

---

## 9. Expected Latency After Optimization

### Chat Pipeline (`POST /api/chat`)

| Phase | Current | After | Method |
|-------|---------|-------|--------|
| Session + cache check | ~50ms | ~50ms | Unchanged |
| Intent detection (keyword) | <1ms | <1ms | Unchanged |
| API Data Fetch | ~50s | ~25s | Bulk fetch |
| Context Build | ~3s | ~3s | Unchanged |
| Intent fallback (if needed) | ~15s | ~3s | gpt-4.1-nano |
| LLM Generation | ~2.4 min | ~1.5 min | 7k tokens |
| Follow-up Questions | ~15s | ~3s | gpt-4.1-nano |
| Document Generation | ~5s | ~5s | Unchanged (parallel with follow-up) |
| **Total (first request)** | **~4-5 min** | **~2 min** | **~60% reduction** |
| **Total (cached data)** | **~4-5 min** | **~1.5 min** | **Warm cache hit** |
| **Time-to-first-token (stream)** | **~90s** | **~30s** | **Bulk fetch + warm cache** |

### Scope Gap Pipeline (`POST /api/scope-gap/generate`)

| Phase | Current | After | Method |
|-------|---------|-------|--------|
| Data Fetch | ~50s | ~25s | Bulk fetch |
| Extraction (1 attempt) | ~40s | ~40s | Unchanged |
| Classification \| Ambiguity \| Gotcha | ~45s | ~45s | Already parallel |
| Completeness | ~5s | ~5s | Unchanged |
| Quality \| Document | ~40s (seq) | ~35s (parallel) | Parallelized |
| Backpropagation | ~60-300s | ~0-40s | 90% threshold, 2 max |
| **Total (no backprop)** | **~3 min** | **~2.5 min** | |
| **Total (1 backprop)** | **~6 min** | **~3 min** | |
| **Total (worst case, 2 attempts)** | **~10 min** | **~3.5 min** | **65% reduction** |

---

## 10. File Inventory (All Changes)

| File | Layer | Change Description |
|------|-------|--------------------|
| `config.py` | 1,2,3,4 | Add `bulk_fetch_enabled`, `bulk_fetch_timeout`, `intent_model`, `followup_model`, `disk_cache_enabled`, `disk_cache_dir`, `cache_warmup_enabled`; update defaults for `max_output_tokens`, `note_max_chars`, `api_timeout_seconds`, `cache_ttl_summary_data`, `parallel_fetch_concurrency` |
| `services/api_client.py` | 1 | Add `_fetch_bulk()` method; modify `_fetch_all_pages()` to try bulk first with fallback |
| `services/cache_service.py` | 4 | Add `DiskCache` inner class for file-based L2; integrate into `get()`/`set()` flow; add background warm-up scheduler; add cache cleanup method |
| `agents/intent_agent.py` | 2 | Use `settings.intent_model` instead of `settings.openai_model` in `_llm_detect()` |
| `agents/generation_agent.py` | 2 | Use `settings.followup_model` in `_generate_follow_up_questions()` |
| `scope_pipeline/orchestrator.py` | 5 | Parallelize quality + document via `asyncio.gather()`; parallelize force-extraction batches |
| `scope_pipeline/config.py` | 5 | Update defaults: `completeness_threshold=90.0`, `max_attempts=2` |
| `main.py` | 4 | Add cache cleanup background task in lifespan |
| `.env` | 3 | Update production values |

### New Files
None. All changes are modifications to existing files.

### New Dependencies
None. Uses existing `asyncio`, `json`, `pathlib`, `hashlib`.

---

## 11. Rollback Strategy

Each optimization layer has an independent `.env` toggle:

| Layer | Toggle | Rollback Value |
|-------|--------|----------------|
| Smart Fetch | `BULK_FETCH_ENABLED` | `false` (reverts to pagination) |
| Tiered LLM | `INTENT_MODEL` / `FOLLOWUP_MODEL` | `gpt-4.1-mini` (reverts to original model) |
| Token Reduction | `MAX_OUTPUT_TOKENS` | `10000` (reverts to original) |
| Disk Cache | `DISK_CACHE_ENABLED` | `false` (reverts to L1-only) |
| Pipeline Parallel | `SCOPE_GAP_COMPLETENESS_THRESHOLD` / `SCOPE_GAP_MAX_ATTEMPTS` | `95.0` / `5` |

All toggles are live-reloadable via server restart. No database migrations or irreversible changes.

---

## 12. Testing Strategy

### Unit Tests
- `test_api_client_bulk_fetch.py` — bulk fetch success, timeout fallback, error fallback
- `test_cache_disk.py` — disk write/read, TTL expiry, cleanup, concurrent access
- `test_tiered_llm.py` — correct model routing per call type
- `test_pipeline_parallel.py` — quality || document execution, force-extraction batches

### Integration Tests
- `test_chat_latency.py` — end-to-end chat pipeline timing (target: <120s)
- `test_scope_gap_latency.py` — end-to-end scope gap pipeline timing (target: <210s)
- `test_cache_warmup.py` — verify background refresh fires at 80% TTL
- `test_bulk_fetch_fallback.py` — verify pagination kicks in when bulk fails

### Performance Tests
- Benchmark: 5 sequential requests to same project/trade (measure cache hit rate)
- Benchmark: 3 concurrent requests to different projects (measure resource contention)
- Benchmark: Server restart + first request (measure disk cache recovery)

---

## 13. Deployment Plan

### Phase 1: Sandbox Deployment (54.197.189.113)
1. Deploy all code changes to sandbox VM
2. Run full test suite
3. Manual testing: chat + scope gap for 3 project sizes (small, medium, large)
4. Verify latency targets met
5. Verify rollback toggles work

### Phase 2: Production Deployment (13.217.22.125)
1. Deploy to production with `BULK_FETCH_ENABLED=true`
2. Monitor first 10 requests for latency regression
3. If issues: toggle `BULK_FETCH_ENABLED=false` (instant rollback)
4. Enable disk cache: `DISK_CACHE_ENABLED=true`
5. Monitor for 24 hours

### Phase 3: GitHub Push
1. Push all changes to GitHub repository
2. Update CLAUDE.md with optimization v4 section
3. Update ARCHITECTURE.md with new cache layer

---

## 14. Monitoring & Success Criteria

### Metrics to Track
- `pipeline_ms` in `ChatResponse` — target: <120,000ms (2 min)
- `token_log` per-step breakdown — verify LLM time reduction
- Cache hit rate (log L1/L2/disk hits) — target: >50% after warm-up
- Bulk fetch success rate — target: >95%

### Success Criteria
- [ ] Chat endpoint p95 latency < 2 minutes
- [ ] Scope gap pipeline p95 latency < 3.5 minutes
- [ ] No degradation in answer quality (groundedness score >= 0.70)
- [ ] All existing tests pass
- [ ] Cache survives server restart (disk L2)
- [ ] Rollback toggles verified working

---

## 15. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Bulk fetch returns different data shape than paginated | Low | High | Validate response shape matches; fallback to pagination |
| gpt-4.1-nano produces lower quality intent detection | Medium | Medium | Keyword detection handles 95% of cases; LLM is fallback only |
| Disk cache fills disk space | Low | Medium | Background cleanup every 5 min; configurable max size |
| 90% completeness threshold misses scope items | Medium | Low | User reported minor quality trade-off is acceptable |
| Bulk API endpoint gets rate-limited or throttled | Low | Medium | Fallback to pagination; monitor 429 responses |
