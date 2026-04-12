# Latency Optimization — Clarifying Questions

**Project:** Construction Intelligence Agent  
**Current Latency:** ~10 minutes  
**Target:** As low as possible  
**Date:** 2026-04-12  

---

## Q1: Which endpoint has the ~10 minute latency?

- **A)** Chat endpoint (`POST /api/chat`) — general Q&A like "create scope for electrical"
- **B)** Scope Gap pipeline (`POST /api/scope-gap/generate`) — full 7-agent extraction pipeline
- **C)** Both — both endpoints are too slow and need optimization
- **D)** Something else — please describe the specific user flow

> **Why this matters:** Chat pipeline has ~4-5 min ceiling (1 LLM call + API fetch). Scope gap has ~3-8 min ceiling (7 agents + backpropagation). Optimization strategies differ significantly.

**Answer:** Both

---

## Q2: What is the acceptable target latency?

- **A)** Under 30 seconds (aggressive — requires architecture redesign, background pre-computation)
- **B)** Under 1-2 minutes (moderate — achievable with parallelization + caching + token reduction)
- **C)** Under 3-5 minutes (conservative — achievable with config tuning + minor code changes)
- **D)** Specific target: ______ seconds

> **Why this matters:** Sub-30s requires pre-computing results and serving from cache. Sub-2min requires aggressive parallelization and LLM token reduction. Sub-5min is achievable with config changes alone.

**Answer:** Under 1-2 minutes

---

## Q3: What is the typical dataset size you're optimizing for?

- **A)** Small projects (< 500 records, < 10 pages) — e.g., residential
- **B)** Medium projects (500-5,000 records, 10-100 pages) — e.g., commercial
- **C)** Large projects like Electrical 7212 (11,360 records, 228 pages) — worst case
- **D)** All of the above — must perform well across all sizes

> **Why this matters:** API pagination is the #1 bottleneck for large projects (50s for 228 pages). Small projects already complete in ~30-60s. Optimization ROI depends on typical workload.

**Answer:**  All of the above — must perform well across all sizes

---

## Q4: Is the MongoDB API (`mongo.ifieldsmart.com`) under your control?

- **A)** Yes — we can modify the API (increase page size, add filtering, add bulk endpoints)
- **B)** No — it's a third-party API, we can only consume it as-is (50 records/page hard cap)
- **C)** Partially — we can request changes but it takes time (weeks/months)

> **Why this matters:** If we can increase the API page size from 50 to 500, that alone reduces fetch time from 50s to ~5s (10x improvement). If not, we must optimize around the 50-record limit.

**Answer:** Partially — we can request changes but it takes time (weeks/months). But when I am testing this api : https://mongo.ifieldsmart.com/api/drawingText/byTradeAndSet?projectId=7292&trade=Civil&setId=4720 in postman for a project then it would take only 20 to 30 seconds to get the data.

---

## Q5: Is Redis currently running in production?

- **A)** Yes — Redis is active and connected on the production VM
- **B)** No — Redis is not installed/running (L1 in-memory cache only)
- **C)** Unsure — need to check

> **Why this matters:** Without Redis, cache is lost on every server restart. L2 Redis provides cross-request caching (1-hour TTL for full responses). A cache hit returns in <1ms vs 4-10 min uncached.

**Answer:** No — Redis is not installed/running (L1 in-memory cache only)

---

## Q6: Can we switch to a faster/cheaper LLM model for non-critical steps?

Currently all LLM calls use `gpt-4.1-mini` (chat) or `gpt-4.1` (scope gap).

- **A)** Yes — use faster models (gpt-4.1-nano, gpt-3.5-turbo) for intent detection, follow-up questions, classification
- **B)** No — quality is paramount, keep gpt-4.1 for all steps
- **C)** Selective — use faster models only for intent detection and follow-up questions, keep gpt-4.1 for extraction/generation
- **D)** Open to experimentation — let's test and compare quality vs speed

> **Why this matters:** Each LLM call takes 15-60s. Switching intent detection + follow-up questions to a faster model could save ~1-2 min per request with minimal quality loss.

**Answer:** Selective — use faster models only for intent detection and follow-up questions, keep gpt-4.1 for extraction/generation

---

## Q7: Is response quality degradation acceptable for speed?

- **A)** No — answer quality and completeness must remain identical
- **B)** Minor degradation OK — e.g., shorter answers (8000 tokens → 6000), slightly less detail
- **C)** Significant trade-off OK — e.g., summarized answers, skip follow-up questions, lower completeness threshold
- **D)** Speed is king — optimize for speed even if answers are shorter/less detailed

> **Why this matters:** Current `max_output_tokens=10,000` takes ~2.4 min for LLM generation. Reducing to 6,000 saves ~1 min. Lowering scope gap completeness threshold from 95% to 85% eliminates most backpropagation retries (saves 1-3 min).

**Answer:** Minor degradation OK — e.g., shorter answers (8000 tokens → 6000), slightly less detail

---

## Q8: Should we implement background pre-computation?

For frequently queried projects/trades, we could pre-compute and cache results.

- **A)** Yes — pre-compute top 10 projects × top 5 trades on a schedule (cron job)
- **B)** Yes — pre-compute on first query, serve cached for subsequent queries (lazy pre-computation)
- **C)** No — every query should be real-time with fresh data
- **D)** Hybrid — pre-compute API data fetch + context build, but always run LLM fresh

> **Why this matters:** Pre-computation can reduce latency to near-zero for cached queries. The trade-off is data freshness — cached results may be 5-60 min stale depending on TTL.

**Answer:**  Hybrid — pre-compute API data fetch + context build, but always run LLM fresh

---

## Q9: Is streaming response acceptable for the UI?

The `/api/chat/stream` endpoint already exists but may not be used by the frontend.

- **A)** Yes — the frontend supports SSE streaming (show tokens as they arrive)
- **B)** No — the frontend waits for the complete response before displaying
- **C)** Can be updated — we can modify the frontend to support streaming
- **D)** Not applicable — this is an API-only service (no frontend)

> **Why this matters:** Streaming doesn't reduce total latency but reduces *perceived* latency dramatically. First token appears in ~90s instead of waiting 4-10 min for the full response.

**Answer:** Yes — the frontend supports SSE streaming (show tokens as they arrive)

---

## Q10: What is the scope gap pipeline's primary use case?

- **A)** Real-time — user submits and waits for result on screen
- **B)** Background job — user submits, gets notified when done (can take 5-10 min)
- **C)** Batch processing — multiple projects processed overnight
- **D)** Mixed — some users wait, some submit and come back later

> **Why this matters:** If it's a background job, 5-10 min is acceptable and we focus on throughput. If real-time, we need aggressive latency optimization. The current job submission system (`POST /api/scope-gap/submit`) suggests background processing was intended.

**Answer:** Real-time — user submits and waits for result on screen

---

## Q11: How many concurrent users typically use the system?

- **A)** 1-5 users (low concurrency)
- **B)** 5-20 users (moderate)
- **C)** 20-100 users (high — need connection pooling, rate limiting)
- **D)** Unknown — need to check analytics

> **Why this matters:** High concurrency means shared resources (API connections, LLM rate limits, Redis) become bottlenecks. The current `max_concurrent_requests=50` and `parallel_fetch_concurrency=30` settings may need tuning.

**Answer:** 5-20 users (moderate)

---

## Q12: Are there specific trades/project types that are slowest?

- **A)** Electrical — largest datasets (11,000+ records)
- **B)** Mechanical/Plumbing — also large
- **C)** All trades are similarly slow
- **D)** Specific projects: ______ (please list project IDs)

> **Why this matters:** If 80% of latency comes from 20% of trades (electrical), we can apply targeted optimization (pre-caching electrical data, trade-specific token budgets, etc.).

**Answer:** All trades are similarly slow

---

## Q13: Should we preserve backward compatibility with the current API contract?

- **A)** Yes — `ChatRequest`/`ChatResponse` schema must stay identical (no breaking changes)
- **B)** Minor changes OK — can add new optional fields, but existing fields must remain
- **C)** Breaking changes OK — we can update the frontend/clients to match new API
- **D)** Versioned — add a `/v2/api/chat` endpoint alongside the existing one

> **Why this matters:** Some optimizations (e.g., chunked responses, deferred document generation, async result polling) require API contract changes. If we must preserve compatibility, the optimization options are more constrained.

**Answer:** Yes — `ChatRequest`/`ChatResponse` schema must stay identical (no breaking changes)

---

## Q14: Is the Scope Gap UI (`scope-gap-ui/`) actively used and needs to remain working?

- **A)** Yes — it's the primary interface for scope gap analysis
- **B)** No — it's a prototype, not actively used
- **C)** It's being replaced — new UI coming soon
- **D)** Unsure

> **Why this matters:** If the UI is actively used, any backend changes to the scope gap pipeline must maintain compatibility with the frontend's expectations (SSE events, job status polling, session management).

**Answer:** No — it's a prototype, not actively used

---

## Q15: What's the deployment constraint for the optimization?

- **A)** Hot deploy — changes must be deployable without downtime (rolling restart)
- **B)** Maintenance window OK — can take the service down briefly for deployment
- **C)** Canary deployment — deploy to sandbox first, validate, then production
- **D)** No constraints — deploy however needed

> **Why this matters:** Some optimizations (Redis schema changes, new background workers, database migrations) require careful deployment. Understanding the deployment model helps plan the rollout.

**Answer:** Canary deployment — deploy to sandbox first, validate, then production

---

## Summary Checklist

Please answer each question (A/B/C/D or custom) and return this file. Your answers will drive the optimization design.

| # | Question | Your Answer |
|---|----------|-------------|
| Q1 | Which endpoint? | |
| Q2 | Target latency? | |
| Q3 | Typical dataset size? | |
| Q4 | MongoDB API under control? | |
| Q5 | Redis running in prod? | |
| Q6 | Faster LLM for non-critical steps? | |
| Q7 | Quality degradation acceptable? | |
| Q8 | Background pre-computation? | |
| Q9 | Streaming response for UI? | |
| Q10 | Scope gap use case? | |
| Q11 | Concurrent users? | |
| Q12 | Slowest trades? | |
| Q13 | Backward compatibility? | |
| Q14 | Scope Gap UI actively used? | |
| Q15 | Deployment constraint? | |
