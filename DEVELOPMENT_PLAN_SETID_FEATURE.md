# Development Plan: SetId Filter Feature

**Date:** 2026-03-31
**Status:** APPROVED — Ready for Development
**Feature:** Optional `set_ids` parameter for document generation filtered by drawing set

---

## User Story

As a construction project user, I want to generate scope documents filtered by **trade AND setId** (drawing set), so that I get documents scoped to a specific set of construction documents rather than all drawings for the entire trade.

Currently, documents are generated using all drawing notes for a trade via `summaryByTrade`. The new feature adds an **optional** `set_ids` parameter:

- **No set_ids provided** → Use existing `summaryByTrade` API (no behavior change)
- **set_ids provided** → Use new `summaryByTradeAndSet` API for each setId, merge results

---

## Clarifying Q&A (User Answers)

| # | Question | Answer |
|---|----------|--------|
| Q1 | Empty result when setId returns 0 records? | **(a)** Return error: "No records found for this trade and set combination" |
| Q2 | Include setName in document header/footer/filename/response? | **Yes** — all of them |
| Q3 | Include set info in LLM system prompt? | **Yes** — straightforward: trade + setId, retrieve data, create document |
| Q4 | Multiple setIds in single request? | **Yes** — could be multiple or single |
| Q5 | Frontend: how will users provide setId? | **Text field** — user types numeric ID |
| Q6 | SetId type — always integer? | **Maybe both** int and string |
| Q7 | Existing tests must pass? | **Yes** — backward compatible, add new tests |

---

## API Discovery

### New API Endpoint (verified 2026-03-31)

```
GET https://mongo.ifieldsmart.com/api/drawingText/summaryByTradeAndSet
    ?projectId=7298
    &trade=Specialty Trade
    &setId=4730
```

### Response Shape (identical to summaryByTrade)

```json
{
  "success": true,
  "data": {
    "list": [
      {
        "_id": "69aad8126f38512da3b2166b",
        "projectId": 7298,
        "setName": "100% CONSTRUCTION DOCUMENTS",
        "setTrade": "Civil",
        "drawingName": "CG-105",
        "drawingTitle": "BUILDING DRAINAGE PLAN",
        "text": "ALL EXISTING AND PROPOSED STORMWATER...",
        "csi_division": ["31 - Earthwork", "01 - General Requirements"],
        "trades": ["Civil", "Specialty Trade"]
      }
    ],
    "totalCount": 868
  }
}
```

### Key Findings

| Property | summaryByTrade (old) | summaryByTradeAndSet (new) |
|----------|---------------------|---------------------------|
| Response shape | `{success, data: {list, count}}` | `{success, data: {list, totalCount}}` |
| Record fields | Identical | Identical |
| Pagination | 50 records/page, `skip`/`limit` | 50 records/page, `skip`/`limit` |
| Total field | `count` (unreliable page count) | `totalCount` (actual record count) |
| Tested data | projectId=7298, trade="Specialty Trade" | same + setId=4730 → 868 records |

---

## Architecture Design

### Data Flow (Current vs New)

```
CURRENT:
  ChatRequest(project_id, query)
    → IntentAgent.detect(query) → trade
    → APIClient.get_summary_by_trade(project_id, trade)
    → ContextBuilder.build() → context
    → LLM → answer → DocumentGenerator → docx

NEW (set_ids provided):
  ChatRequest(project_id, query, set_ids=[4730, 4731])
    → IntentAgent.detect(query) → trade
    → APIClient.get_summary_by_trade_and_set(project_id, trade, set_ids)
       → parallel API calls per setId
       → merge + dedup by _id
    → ContextBuilder.build() → context (with set metadata)
    → LLM → answer (system prompt includes set info)
    → DocumentGenerator → docx (header/footer/filename include set info)

NEW (no set_ids):
  Identical to CURRENT — zero behavior change
```

### Multiple SetIds Strategy

The `summaryByTradeAndSet` API accepts a **single setId**. For multiple setIds:

1. Fire **parallel** API calls (one per setId) using `asyncio.gather`
2. Each call uses the same parallel pagination as `get_summary_by_trade`
3. Merge results with `_id` deduplication (same record may appear in multiple sets)
4. Extract unique `setName` values from merged results for document metadata

### Cache Key Strategy

Cache keys must differentiate by set_ids:
```python
# Old: "summary:{project_id}:{trade}"
# New: "summary:{project_id}:{trade}:sets:{sorted_set_ids_joined}"
```

---

## Files to Modify

| # | File | Change | LOC Est. |
|---|------|--------|----------|
| 1 | `config.py` | Add `SUMMARY_BY_TRADE_AND_SET_PATH` setting | ~3 |
| 2 | `models/schemas.py` | Add `set_ids` to `ChatRequest`, `set_names` to `ChatResponse` | ~8 |
| 3 | `services/api_client.py` | Add `get_summary_by_trade_and_set()` method | ~60 |
| 4 | `services/context_builder.py` | Pass `set_ids` to API, include set metadata in context header | ~20 |
| 5 | `agents/data_agent.py` | Pass `set_ids` through to context builder | ~10 |
| 6 | `agents/generation_agent.py` | Pass `set_ids` through pipeline, include in system prompt, cache key | ~30 |
| 7 | `services/document_generator.py` | Include set info in header/footer/filename | ~15 |
| 8 | `routers/chat.py` | No changes needed (Pydantic model handles new field) | 0 |

### Files to Create

| # | File | Purpose | LOC Est. |
|---|------|---------|----------|
| 1 | `tests/test_set_id_feature.py` | Unit tests for setId feature | ~150 |

**Total estimated changes:** ~296 LOC across 8 modified + 1 new file

---

## Detailed Change Specifications

### 1. `config.py` — New Setting

```python
# MongoDB API — SetId endpoint
summary_by_trade_and_set_path: str = "/api/drawingText/summaryByTradeAndSet"
```

### 2. `models/schemas.py` — Schema Changes

**ChatRequest** — add optional field:
```python
set_ids: Optional[list[Union[int, str]]] = Field(
    None,
    description="Optional list of set IDs to filter drawings. "
                "If provided, uses summaryByTradeAndSet API. "
                "If omitted, uses summaryByTrade (existing behavior).",
)
```

**ChatResponse** — add metadata:
```python
set_ids: Optional[list[Union[int, str]]] = Field(None, description="Set IDs used for filtering")
set_names: list[str] = Field(default_factory=list, description="Set names from API response")
```

### 3. `services/api_client.py` — New Method

```python
async def get_summary_by_trade_and_set(
    self,
    project_id: int,
    trade: str,
    set_ids: list[Union[int, str]],
    bypass_cache: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Fetch records filtered by trade AND setId(s).

    For multiple set_ids, fires parallel API calls and merges results.
    Returns (records, set_names) — set_names extracted from response data.
    """
```

- Uses same `_fetch_all_pages` logic but with `summaryByTradeAndSetPath`
- For multiple setIds: `asyncio.gather` over all setIds, merge with `_id` dedup
- Returns `(merged_records, unique_set_names)`
- Cache key includes sorted set_ids

### 4. `services/context_builder.py` — Set Metadata in Context

- `build()` method gains optional `set_ids` and `set_names` params
- Context header includes set info when present:
  ```
  ## Drawing Notes — Trade: Specialty Trade | Sets: 100% CONSTRUCTION DOCUMENTS (4730)
  ```
- Stats dict includes `set_ids` and `set_names`

### 5. `agents/data_agent.py` — Pass-Through

- `prepare_context()` gains optional `set_ids` param
- Calls appropriate API method based on presence of `set_ids`

### 6. `agents/generation_agent.py` — Pipeline Integration

- Read `request.set_ids` from ChatRequest
- Pass to `DataAgent.prepare_context()`
- Include set info in system prompt metadata block
- Include `set_ids` in cache key
- Pass set info to document generator
- Populate `ChatResponse.set_ids` and `ChatResponse.set_names`

### 7. `services/document_generator.py` — Document Metadata

- `generate_sync()` gains optional `set_names` and `set_ids` params
- Document header: `"Set: 100% CONSTRUCTION DOCUMENTS"`
- Document footer: includes set info
- Filename: `scope_specialtytrade_set4730_GranvilleHotel_7298_abc123.docx`
  - For multiple: `scope_specialtytrade_set4730_4731_GranvilleHotel_7298_abc123.docx`

---

## Backward Compatibility

| Aspect | Guarantee |
|--------|-----------|
| `set_ids` not provided | 100% identical to current behavior |
| Existing `ChatRequest` payloads | Work unchanged (new field is `Optional[None]`) |
| Cache keys | Old keys without set_ids remain valid |
| Existing tests | Must pass without modification |
| API response schema | Additive only (new fields have defaults) |
| Document filename format | Unchanged when no set_ids |

---

## Test Plan

### Unit Tests (test_set_id_feature.py)

1. **ChatRequest validation** — set_ids accepts int, str, list, None
2. **APIClient.get_summary_by_trade_and_set** — single setId, multiple setIds, empty result
3. **APIClient** — falls back to summaryByTrade when no set_ids
4. **ContextBuilder** — includes set metadata in context header
5. **Cache key** — different keys for different set_ids
6. **Document filename** — includes set info when set_ids present
7. **Backward compat** — all existing ChatRequest shapes still work

### Integration Tests (manual on VM)

1. `POST /api/chat` with `set_ids: [4730]` → filtered document
2. `POST /api/chat` with `set_ids: [4730, 4731]` → merged document
3. `POST /api/chat` without `set_ids` → same as before
4. `POST /api/chat` with invalid `set_ids: [99999]` → error message
5. Streaming: `POST /api/chat/stream` with `set_ids` → SSE events include set metadata

---

## Deployment Plan

1. Run existing tests → all pass
2. Implement feature
3. Run new + existing tests → all pass
4. SCP to PROD VM (13.217.22.125) → restart construction-agent
5. SCP to Sandbox VM (54.197.189.113) → restart construction-agent
6. Live integration tests on both VMs
7. Push to GitHub
