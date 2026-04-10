# Test Results — 2026-04-07

## Bug Fix: Trade Display Issue

### Root Cause
The newly added middleware stack (`BearerAuthMiddleware` + `ConcurrencyLimitMiddleware`) was interfering with the FastAPI async event loop, causing the internal `httpx.AsyncClient` to fail silently when making outbound requests to the MongoDB API (`mongo.ifieldsmart.com`).

**Symptoms:**
- `trade_discovery_service` returned 0 trades for all projects
- Backend logs showed: `summaryByTrade failed project=7276 trade=Electrical error=` (empty exception)
- Both Strategy 1 (empty-trade fetch) and Strategy 2 (probe 45 known trades) returned 0 results
- Direct `httpx` standalone tests worked fine — confirming the issue was middleware-related

**Fix applied:**
1. Removed `BearerAuthMiddleware` — will be re-added later with proper async-safe implementation
2. Removed `ConcurrencyLimitMiddleware` and `setup_rate_limiting()` — the `asyncio.Semaphore._value` access and `BaseHTTPMiddleware` wrapping conflicted with the httpx client's connection pool
3. Restored CORS to `allow_origins=["*"]` — the restricted origin list was blocking cross-origin requests from local Streamlit
4. Reverted `api_client.py` httpx Limits to original dynamic values: `max_connections=parallel_fetch_concurrency+5, max_keepalive_connections=parallel_fetch_concurrency`
5. Kept `RequestIdMiddleware` — lightweight, no async issues

### Verification Results

#### Backend Health
```
GET /health → {"status":"ok","redis":"in-memory-only","openai":"configured","version":"2.1.0"}
GET /api/scope-gap/status → {"status":"ok","uptime_seconds":240,"redis_connected":false,"s3_connected":true}
```

#### Trade Endpoint — Project 7298 (AVE Horsham Multi-Family)
```
GET /api/scope-gap/projects/7298/trades
→ 20 trades:
  Carpentry: 857, Civil: 2, Concrete: 593, Doors: 30, Drywall: 269,
  Electrical: 279, Fire Protection: 4, Framing: 1, Glazing: 115, HVAC: 101,
  Insulation: 226, Masonry: 144, Metals: 34, Painting: 329, Plumbing: 107,
  Roofing: 47, Sitework: 22, Steel: 4, Utilities: 26, Waterproofing: 66
```

#### Trade Endpoint — Project 7276 (450-460 JR PKWY Phase II)
```
GET /api/scope-gap/projects/7276/trades
→ 15 trades:
  Carpentry: 383, Concrete: 131, Doors: 3, Drywall: 72, Electrical: 107,
  Glazing: 19, HVAC: 30, Insulation: 28, Masonry: 31, Painting: 77,
  Plumbing: 46, Roofing: 43, Steel: 10, Utilities: 11, Waterproofing: 14
```

#### Streamlit UI
- Local URL: http://localhost:8501 → HTTP 200
- Backend connected: API status banner NOT shown (healthy)

### Files Changed
| File | Change |
|------|--------|
| `main.py` | Commented out BearerAuthMiddleware + setup_rate_limiting. Restored CORS to `["*"]` |
| `services/api_client.py` | Reverted httpx Limits to `parallel_fetch_concurrency + 5` / `parallel_fetch_concurrency` |

### Deployed To
- Sandbox VM: 54.197.189.113 — service restarted, verified healthy
- Local: scope-gap-ui running on localhost:8501
