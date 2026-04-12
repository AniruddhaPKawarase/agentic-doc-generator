# Latency Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce construction intelligence agent latency from ~10 min to under 2 min for both chat and scope gap endpoints.

**Architecture:** 5-layer optimization — (1) bulk API fetch replacing pagination, (2) tiered LLM routing for lightweight calls, (3) token budget reduction, (4) disk-backed persistent cache with background warm-up, (5) scope gap pipeline parallelism improvements.

**Tech Stack:** Python 3.11+, FastAPI, httpx, asyncio, OpenAI API, pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-04-12-latency-optimization-design.md`

---

## Task 1: Add New Config Settings

**Files:**
- Modify: `config.py` (lines 29, 35, 46-51, 54-55, 58)

- [ ] **Step 1: Write the failing test**

Create `tests/test_latency_config.py`:

```python
"""Tests for latency optimization config settings."""
import os
from unittest.mock import patch


def test_bulk_fetch_defaults():
    """New bulk fetch settings have correct defaults."""
    # Clear cached settings
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.bulk_fetch_enabled is True
    assert s.bulk_fetch_timeout == 60


def test_tiered_model_defaults():
    """New tiered LLM model settings have correct defaults."""
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.intent_model == "gpt-4.1-nano"
    assert s.followup_model == "gpt-4.1-nano"


def test_disk_cache_defaults():
    """New disk cache settings have correct defaults."""
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.disk_cache_enabled is True
    assert s.disk_cache_dir == ".cache"
    assert s.cache_warmup_enabled is True


def test_updated_defaults():
    """Updated performance defaults are applied."""
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.max_output_tokens == 7000
    assert s.note_max_chars == 200
    assert s.api_timeout_seconds == 60
    assert s.cache_ttl_summary_data == 900
    assert s.parallel_fetch_concurrency == 50


def test_env_override_bulk_fetch():
    """Bulk fetch settings can be overridden via env vars."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "BULK_FETCH_ENABLED": "false",
        "BULK_FETCH_TIMEOUT": "120",
    }):
        from config import Settings
        s = Settings()
        assert s.bulk_fetch_enabled is False
        assert s.bulk_fetch_timeout == 120


def test_env_override_tiered_models():
    """Tiered model settings can be overridden via env vars."""
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "INTENT_MODEL": "gpt-4.1-mini",
        "FOLLOWUP_MODEL": "gpt-4.1-mini",
    }):
        from config import Settings
        s = Settings()
        assert s.intent_model == "gpt-4.1-mini"
        assert s.followup_model == "gpt-4.1-mini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_latency_config.py -v`
Expected: FAIL — `Settings` has no attribute `bulk_fetch_enabled`

- [ ] **Step 3: Implement config changes**

In `config.py`, add these new fields after line 35 (`parallel_fetch_concurrency`):

```python
    # ── Bulk Fetch (Layer 1) ──────────────────────────────────────
    bulk_fetch_enabled: bool = True
    bulk_fetch_timeout: int = 60
```

Add these fields after line 18 (`openai_output_cost_per_million`):

```python
    # ── Tiered LLM Models (Layer 2) ──────────────────────────────
    intent_model: str = "gpt-4.1-nano"
    followup_model: str = "gpt-4.1-nano"
```

Add these fields after line 59 (`cache_ttl_query`):

```python
    # ── Disk Cache (Layer 4) ──────────────────────────────────────
    disk_cache_enabled: bool = True
    disk_cache_dir: str = ".cache"
    cache_warmup_enabled: bool = True
```

Update these existing defaults:

```python
    api_timeout_seconds: int = 60          # was 30
    parallel_fetch_concurrency: int = 50   # was 30
    max_output_tokens: int = 7000          # was 10000
    note_max_chars: int = 200              # was 300
    cache_ttl_summary_data: int = 900      # was 300
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_latency_config.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/ -v --timeout=60 2>&1 | head -80`
Expected: All existing tests still pass (config changes are backward compatible)

- [ ] **Step 6: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add config.py tests/test_latency_config.py
git commit -m "feat: add latency optimization config settings (Layer 1-4)"
```

---

## Task 2: Smart Bulk Fetch in API Client

**Files:**
- Modify: `services/api_client.py` (add `_fetch_bulk()`, modify `_fetch_all_pages()` line 420)
- Create: `tests/test_bulk_fetch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bulk_fetch.py`:

```python
"""Tests for bulk fetch optimization in APIClient."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.api_client import APIClient
from services.cache_service import CacheService


def _make_bulk_response(records: list[dict]) -> dict:
    """Build API response shape matching real MongoDB API."""
    return {"success": True, "data": {"list": records}}


def _make_records(n: int) -> list[dict]:
    """Generate n fake drawing records."""
    return [
        {
            "_id": f"id_{i}",
            "projectId": 7292,
            "setName": "Set A",
            "drawingName": f"E-{i:03d}",
            "text": f"Note for drawing {i}",
            "trades": ["Electrical"],
        }
        for i in range(n)
    ]


@pytest.fixture
def cache():
    cache = MagicMock(spec=CacheService)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def api_client(cache):
    client = APIClient(cache=cache)
    return client


@pytest.mark.asyncio
async def test_fetch_bulk_returns_all_records(api_client):
    """_fetch_bulk returns all records from single non-paginated call."""
    records = _make_records(500)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_bulk_response(records)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    api_client._http = mock_http

    result = await api_client._fetch_bulk(7292, "Electrical")
    assert result is not None
    assert len(result) == 500
    # Verify no pagination params sent
    call_kwargs = mock_http.get.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
    assert "skip" not in params
    assert "limit" not in params
    assert "page" not in params


@pytest.mark.asyncio
async def test_fetch_bulk_returns_none_on_timeout(api_client):
    """_fetch_bulk returns None when request times out (triggers pagination fallback)."""
    import httpx
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    api_client._http = mock_http

    result = await api_client._fetch_bulk(7292, "Electrical")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_bulk_returns_none_on_http_error(api_client):
    """_fetch_bulk returns None on HTTP error (triggers pagination fallback)."""
    import httpx
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock_resp,
    )
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    api_client._http = mock_http

    result = await api_client._fetch_bulk(7292, "Electrical")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_bulk_returns_none_on_empty_response(api_client):
    """_fetch_bulk returns None when API returns empty list."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_bulk_response([])

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    api_client._http = mock_http

    result = await api_client._fetch_bulk(7292, "Electrical")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_bulk_with_set_id(api_client):
    """_fetch_bulk includes setId param when provided."""
    records = _make_records(100)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_bulk_response(records)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    api_client._http = mock_http

    result = await api_client._fetch_bulk(7292, "Civil", set_id=4720)
    assert result is not None
    assert len(result) == 100
    call_kwargs = mock_http.get.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
    assert params.get("setId") == 4720


@pytest.mark.asyncio
@patch("config.get_settings")
async def test_fetch_all_pages_tries_bulk_first(mock_settings):
    """_fetch_all_pages tries bulk fetch before pagination when enabled."""
    settings = MagicMock()
    settings.bulk_fetch_enabled = True
    settings.bulk_fetch_timeout = 60
    settings.api_base_url = "https://mongo.ifieldsmart.com"
    settings.api_auth_token = ""
    settings.api_timeout_seconds = 60
    settings.parallel_fetch_concurrency = 50
    settings.summary_by_trade_path = "/api/drawingText/summaryByTrade"
    settings.summary_by_trade_and_set_path = "/api/drawingText/summaryByTradeAndSet"
    settings.max_pagination_pages = 200
    mock_settings.return_value = settings

    cache = MagicMock(spec=CacheService)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    client = APIClient(cache=cache)

    records = _make_records(200)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _make_bulk_response(records)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client._http = mock_http

    result = await client._fetch_all_pages(7292, "Electrical")
    assert len(result) == 200
    # Should have been called exactly once (bulk fetch, no pagination)
    assert mock_http.get.call_count == 1


@pytest.mark.asyncio
@patch("config.get_settings")
async def test_fetch_all_pages_falls_back_to_pagination_on_bulk_failure(mock_settings):
    """_fetch_all_pages falls back to pagination when bulk fetch fails."""
    settings = MagicMock()
    settings.bulk_fetch_enabled = True
    settings.bulk_fetch_timeout = 60
    settings.api_base_url = "https://mongo.ifieldsmart.com"
    settings.api_auth_token = ""
    settings.api_timeout_seconds = 60
    settings.parallel_fetch_concurrency = 50
    settings.summary_by_trade_path = "/api/drawingText/summaryByTrade"
    settings.summary_by_trade_and_set_path = "/api/drawingText/summaryByTradeAndSet"
    settings.max_pagination_pages = 200
    mock_settings.return_value = settings

    cache = MagicMock(spec=CacheService)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    client = APIClient(cache=cache)

    import httpx

    # First call (bulk) fails, subsequent calls (pagination) succeed
    page1_records = _make_records(50)
    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.raise_for_status = MagicMock()
    page1_resp.json.return_value = _make_bulk_response(page1_records[:10])

    mock_http = AsyncMock()
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Bulk fetch fails
            raise httpx.TimeoutException("timeout")
        # Pagination returns partial page (done in 1 page)
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = _make_bulk_response(page1_records[:10])
        return resp

    mock_http.get = AsyncMock(side_effect=side_effect)
    client._http = mock_http

    result = await client._fetch_all_pages(7292, "Electrical")
    # Should have fallen back to pagination after bulk failure
    assert call_count >= 2
    assert len(result) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_bulk_fetch.py -v`
Expected: FAIL — `APIClient` has no method `_fetch_bulk`

- [ ] **Step 3: Implement `_fetch_bulk()` method**

Add this method to `services/api_client.py` class `APIClient`, before `_fetch_all_pages()` (before line 420):

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

        Returns the record list on success, or None if the call fails/times out
        (caller should fall back to paginated fetch).
        """
        if not settings.bulk_fetch_enabled:
            return None

        path = endpoint_path
        if path is None:
            path = (
                settings.summary_by_trade_and_set_path
                if set_id is not None
                else settings.summary_by_trade_path
            )

        params: dict[str, Any] = {"projectId": project_id, "trade": trade}
        if set_id is not None:
            params["setId"] = set_id

        t0 = time.perf_counter()
        try:
            resp = await self._http.get(
                path,
                params=params,
                timeout=httpx.Timeout(settings.bulk_fetch_timeout, connect=10.0),
            )
            resp.raise_for_status()
            records = self._extract_list(resp.json())

            elapsed = int((time.perf_counter() - t0) * 1000)

            if not records:
                logger.info(
                    "Bulk fetch returned empty for project=%s trade=%s set_id=%s (%d ms)",
                    project_id, trade, set_id, elapsed,
                )
                return None

            logger.info(
                "Bulk fetch success: project=%s trade=%s set_id=%s → %d records (%d ms)",
                project_id, trade, set_id, len(records), elapsed,
            )
            return records

        except httpx.TimeoutException:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "Bulk fetch timeout for project=%s trade=%s set_id=%s (%d ms) — falling back to pagination",
                project_id, trade, set_id, elapsed,
            )
            return None
        except Exception as exc:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "Bulk fetch failed for project=%s trade=%s set_id=%s (%d ms): %s — falling back to pagination",
                project_id, trade, set_id, elapsed, exc,
            )
            return None
```

- [ ] **Step 4: Modify `_fetch_all_pages()` to try bulk first**

At the beginning of `_fetch_all_pages()` method body, after the docstring and before the existing `t0 = time.perf_counter()` line, add:

```python
        # Layer 1: Try bulk fetch first (single API call, no pagination)
        bulk_result = await self._fetch_bulk(
            project_id, trade, set_id=set_id, endpoint_path=endpoint_path,
        )
        if bulk_result is not None:
            return bulk_result

        # Fallback: paginated fetch (existing logic below)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_bulk_fetch.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Run existing API client tests**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_api_migration.py tests/test_set_id_feature.py -v --timeout=60`
Expected: Existing tests still pass

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add services/api_client.py tests/test_bulk_fetch.py
git commit -m "feat: add bulk fetch to API client — single call replaces 228 paginated calls"
```

---

## Task 3: Tiered LLM Routing

**Files:**
- Modify: `agents/intent_agent.py` (line 161)
- Modify: `agents/generation_agent.py` (line 918)
- Create: `tests/test_tiered_llm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tiered_llm.py`:

```python
"""Tests for tiered LLM model routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage = MagicMock()
    mock_resp.usage.prompt_tokens = 100
    mock_resp.usage.completion_tokens = 50
    return mock_resp


@pytest.mark.asyncio
async def test_intent_agent_uses_intent_model():
    """IntentAgent._llm_detect() uses settings.intent_model, not openai_model."""
    from agents.intent_agent import IntentAgent

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(
            '{"trade": "Electrical", "csi_divisions": ["26"], "document_type": "scope", "intent": "generate", "confidence": 0.9}'
        )
    )

    agent = IntentAgent(openai_client=mock_client)

    with patch("agents.intent_agent.settings") as mock_settings:
        mock_settings.intent_model = "gpt-4.1-nano"
        mock_settings.openai_model = "gpt-4.1-mini"
        mock_settings.intent_max_tokens = 500

        await agent._llm_detect("generate electrical scope", ["Electrical", "Plumbing"])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4.1-nano"


@pytest.mark.asyncio
async def test_followup_uses_followup_model():
    """_generate_follow_up_questions() uses settings.followup_model."""
    from agents.generation_agent import GenerationAgent

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_openai_response(
            '["What trades are included?", "Any exclusions?"]'
        )
    )

    # Minimal agent construction
    agent = GenerationAgent.__new__(GenerationAgent)
    agent._client = mock_client

    with patch("agents.generation_agent.settings") as mock_settings:
        mock_settings.followup_model = "gpt-4.1-nano"
        mock_settings.openai_model = "gpt-4.1-mini"
        mock_settings.follow_up_questions_enabled = True
        mock_settings.follow_up_questions_count = 2
        mock_settings.follow_up_max_tokens = 400

        questions = await agent._generate_follow_up_questions(
            answer="Electrical scope includes...",
            query="generate electrical scope",
            trade="Electrical",
            document_type="scope",
        )

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4.1-nano"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_tiered_llm.py -v`
Expected: FAIL — model is `gpt-4.1-mini`, not `gpt-4.1-nano`

- [ ] **Step 3: Modify intent_agent.py**

In `agents/intent_agent.py`, line 161, change:

```python
            model=settings.openai_model,
```

to:

```python
            model=settings.intent_model,
```

- [ ] **Step 4: Modify generation_agent.py**

In `agents/generation_agent.py`, line 918, change:

```python
                model=settings.openai_model,
```

to:

```python
                model=settings.followup_model,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_tiered_llm.py -v`
Expected: Both tests PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/ -v --timeout=60 2>&1 | tail -20`
Expected: No regressions

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add agents/intent_agent.py agents/generation_agent.py tests/test_tiered_llm.py
git commit -m "feat: tiered LLM routing — gpt-4.1-nano for intent detection and follow-up questions"
```

---

## Task 4: Disk-Backed L2 Cache

**Files:**
- Modify: `services/cache_service.py`
- Modify: `main.py` (lifespan)
- Create: `tests/test_disk_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_disk_cache.py`:

```python
"""Tests for disk-backed L2 cache."""
import asyncio
import json
import os
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def cache_dir(tmp_path):
    """Provide a temp directory for disk cache."""
    return str(tmp_path / "disk_cache")


@pytest.mark.asyncio
async def test_disk_cache_write_and_read(cache_dir):
    """DiskCache writes JSON files and reads them back."""
    from services.cache_service import DiskCache

    dc = DiskCache(cache_dir)
    await dc.set("test_key", {"data": [1, 2, 3]}, ttl=300)

    result = await dc.get("test_key")
    assert result == {"data": [1, 2, 3]}


@pytest.mark.asyncio
async def test_disk_cache_returns_none_for_missing_key(cache_dir):
    """DiskCache returns None for keys that don't exist."""
    from services.cache_service import DiskCache

    dc = DiskCache(cache_dir)
    result = await dc.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_respects_ttl(cache_dir):
    """DiskCache returns None for expired entries."""
    from services.cache_service import DiskCache

    dc = DiskCache(cache_dir)
    await dc.set("expire_key", {"val": 1}, ttl=1)

    # Immediately readable
    result = await dc.get("expire_key")
    assert result == {"val": 1}

    # Wait for expiry
    await asyncio.sleep(1.1)
    result = await dc.get("expire_key")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_cleanup_removes_expired(cache_dir):
    """cleanup() removes expired files from disk."""
    from services.cache_service import DiskCache

    dc = DiskCache(cache_dir)
    await dc.set("old_key", {"val": 1}, ttl=1)
    await asyncio.sleep(1.1)

    removed = await dc.cleanup()
    assert removed >= 1

    # Directory should have no cache files left
    cache_path = Path(cache_dir)
    json_files = list(cache_path.glob("*.json"))
    assert len(json_files) == 0


@pytest.mark.asyncio
async def test_disk_cache_survives_corrupted_file(cache_dir):
    """DiskCache handles corrupted JSON files gracefully."""
    from services.cache_service import DiskCache

    dc = DiskCache(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)

    # Write a corrupted file
    import hashlib
    key_hash = hashlib.sha256("corrupt_key".encode()).hexdigest()[:32]
    corrupt_path = Path(cache_dir) / f"{key_hash}.json"
    corrupt_path.write_text("NOT VALID JSON{{{")

    result = await dc.get("corrupt_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_service_uses_disk_l2(cache_dir):
    """CacheService reads from disk L2 when L1 misses."""
    from services.cache_service import CacheService, DiskCache

    cache = CacheService(redis_url="")

    disk = DiskCache(cache_dir)
    await disk.set("my_key", {"cached": True}, ttl=300)

    cache._disk = disk

    # L1 miss, but disk L2 should hit
    result = await cache.get("my_key")
    assert result == {"cached": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_disk_cache.py -v`
Expected: FAIL — `DiskCache` not found

- [ ] **Step 3: Implement DiskCache class**

Add the following class to `services/cache_service.py`, after the imports and before the `CacheService` class:

```python
class DiskCache:
    """File-backed L2 cache that survives process restarts.

    Each entry is a JSON file named {sha256(key)[:32]}.json with structure:
    {"expires_at": <unix_ts>, "data": <value>}
    """

    def __init__(self, cache_dir: str) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self._dir / f"{key_hash}.json"

    async def get(self, key: str) -> Any:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
            envelope = json.loads(raw)
            if envelope.get("expires_at", 0) < time.time():
                await asyncio.to_thread(path.unlink, missing_ok=True)
                return None
            return envelope.get("data")
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        path = self._path(key)
        envelope = {"expires_at": time.time() + ttl, "data": value}
        try:
            raw = json.dumps(envelope, default=str)
            await asyncio.to_thread(path.write_text, raw, encoding="utf-8")
        except Exception as exc:
            logger.warning("Disk cache write failed for %s: %s", key, exc)

    async def cleanup(self) -> int:
        """Remove expired files. Returns count of files removed."""
        removed = 0
        try:
            for path in self._dir.glob("*.json"):
                try:
                    raw = await asyncio.to_thread(path.read_text, encoding="utf-8")
                    envelope = json.loads(raw)
                    if envelope.get("expires_at", 0) < time.time():
                        await asyncio.to_thread(path.unlink, missing_ok=True)
                        removed += 1
                except Exception:
                    await asyncio.to_thread(path.unlink, missing_ok=True)
                    removed += 1
        except Exception as exc:
            logger.warning("Disk cache cleanup error: %s", exc)
        return removed
```

Add these imports to the top of `services/cache_service.py` if not already present:

```python
import asyncio
from pathlib import Path
from typing import Any
```

- [ ] **Step 4: Integrate DiskCache into CacheService**

In `CacheService.__init__()`, add disk cache initialization:

```python
        self._disk: Optional[DiskCache] = None
        if settings.disk_cache_enabled:
            self._disk = DiskCache(settings.disk_cache_dir)
```

In `CacheService.get()`, after L1 check and before Redis check, add:

```python
        # L2 disk check
        if self._disk is not None:
            disk_val = await self._disk.get(key)
            if disk_val is not None:
                self._L1[key] = disk_val  # Promote to L1
                return disk_val
```

In `CacheService.set()`, after L1 write and alongside Redis write, add:

```python
        # Write to disk L2
        if self._disk is not None:
            await self._disk.set(key, value, ttl=ttl)
```

- [ ] **Step 5: Add cache cleanup to main.py lifespan**

In `main.py`, inside the `lifespan()` function, after the `yield` line (line 269) and before shutdown, add a background cache cleanup task at startup (before `yield`):

```python
    # Start background cache cleanup task
    async def _cache_cleanup_loop():
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            try:
                if hasattr(cache, '_disk') and cache._disk is not None:
                    removed = await cache._disk.cleanup()
                    if removed:
                        logger.debug("Cache cleanup: removed %d expired files", removed)
            except Exception as exc:
                logger.warning("Cache cleanup error: %s", exc)

    cleanup_task = asyncio.create_task(_cache_cleanup_loop())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_disk_cache.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add services/cache_service.py main.py tests/test_disk_cache.py
git commit -m "feat: disk-backed L2 cache with TTL and background cleanup"
```

---

## Task 5: Scope Gap Pipeline Parallelism

**Files:**
- Modify: `scope_pipeline/orchestrator.py` (lines 269-355)
- Modify: `scope_pipeline/config.py` (lines 72-73)
- Create: `tests/test_pipeline_parallel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_parallel.py`:

```python
"""Tests for scope gap pipeline parallelism optimizations."""
import pytest
from unittest.mock import AsyncMock, MagicMock


def test_pipeline_config_defaults():
    """Pipeline config uses optimized defaults."""
    import os
    # Clear any env overrides
    env_backup = {}
    for k in ["SCOPE_GAP_MAX_ATTEMPTS", "SCOPE_GAP_COMPLETENESS_THRESHOLD"]:
        if k in os.environ:
            env_backup[k] = os.environ.pop(k)

    try:
        from scope_pipeline.config import get_pipeline_config
        config = get_pipeline_config()
        assert config.max_attempts == 2, f"Expected 2, got {config.max_attempts}"
        assert config.completeness_threshold == 90.0, f"Expected 90.0, got {config.completeness_threshold}"
    finally:
        os.environ.update(env_backup)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_pipeline_parallel.py::test_pipeline_config_defaults -v`
Expected: FAIL — `max_attempts` is 5, not 2

- [ ] **Step 3: Update scope_pipeline/config.py defaults**

In `scope_pipeline/config.py`, line 72, change:

```python
        max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "5")),
```

to:

```python
        max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "2")),
```

In `scope_pipeline/config.py`, line 73, change:

```python
        completeness_threshold=float(os.getenv("SCOPE_GAP_COMPLETENESS_THRESHOLD", "95.0")),
```

to:

```python
        completeness_threshold=float(os.getenv("SCOPE_GAP_COMPLETENESS_THRESHOLD", "90.0")),
```

- [ ] **Step 4: Parallelize Quality + Document in orchestrator.py**

In `scope_pipeline/orchestrator.py`, replace the sequential quality + document block (lines 320-355) with parallel execution:

Replace:
```python
        # Step 5: Run quality agent
        final_merged = MergedResults(
            items=final_items,
            classified_items=final_classified,
            ambiguities=list(ambiguities),
            gotchas=list(gotchas),
        )
        quality_result = await self._quality.run(final_merged, emitter)
        quality_report: QualityReport = quality_result.data
        total_tokens += quality_result.tokens_used
        per_agent_timing["quality"] = quality_result.elapsed_ms

        # Step 6: Generate documents
        pipeline_stats = PipelineStats(
            total_ms=int((time.monotonic() - pipeline_start) * 1000),
            attempts=attempt_count,
            tokens_used=total_tokens,
            estimated_cost_usd=round(total_tokens * _COST_PER_TOKEN, 6),
            per_agent_timing=dict(per_agent_timing),
            records_processed=len(all_records),
            items_extracted=len(final_items),
        )

        documents: DocumentSet = await self._document.generate_all(
            items=final_classified,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness_report,
            quality=quality_report,
            project_id=request.project_id,
            project_name=project_display.get("name", project_name),
            project_location=project_display.get("city", ""),
            trade=request.trade,
            stats=pipeline_stats,
            drawing_s3_urls=drawing_s3_urls,
        )
```

With:
```python
        # Step 5 + 6: Run quality agent AND generate documents in PARALLEL
        final_merged = MergedResults(
            items=final_items,
            classified_items=final_classified,
            ambiguities=list(ambiguities),
            gotchas=list(gotchas),
        )

        # Pre-build pipeline stats (document agent needs it; quality tokens added after)
        pipeline_stats = PipelineStats(
            total_ms=int((time.monotonic() - pipeline_start) * 1000),
            attempts=attempt_count,
            tokens_used=total_tokens,
            estimated_cost_usd=round(total_tokens * _COST_PER_TOKEN, 6),
            per_agent_timing=dict(per_agent_timing),
            records_processed=len(all_records),
            items_extracted=len(final_items),
        )

        quality_task = self._quality.run(final_merged, emitter)
        document_task = self._document.generate_all(
            items=final_classified,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness_report,
            quality=None,  # Quality not yet available — document doesn't depend on it
            project_id=request.project_id,
            project_name=project_display.get("name", project_name),
            project_location=project_display.get("city", ""),
            trade=request.trade,
            stats=pipeline_stats,
            drawing_s3_urls=drawing_s3_urls,
        )

        quality_result, documents = await asyncio.gather(
            quality_task, document_task,
        )
        quality_report: QualityReport = quality_result.data
        total_tokens += quality_result.tokens_used
        per_agent_timing["quality"] = quality_result.elapsed_ms
```

- [ ] **Step 5: Parallelize force-extraction in orchestrator.py**

Replace the sequential force-extraction loop (lines 269-318). Replace:
```python
            for drawing_name in force_missing:
                drawing_records = [
                    r for r in all_records
                    if (r.get("drawingName") or r.get("drawing_name", "")) == drawing_name
                ]
                if not drawing_records:
                    continue

                force_input = {
                    "drawing_records": [
                        {
                            "drawing_name": r.get("drawingName") or r.get("drawing_name", ""),
                            "drawing_title": r.get("drawingTitle") or r.get("drawing_title", ""),
                            "text": r.get("text", ""),
                        }
                        for r in drawing_records
                    ],
                    "trade": request.trade,
                    "drawing_list": sorted(source_drawings),
                }

                try:
                    force_result = await self._extraction.run(
                        force_input, emitter, attempt=attempt_count + 1,
                    )
                    force_items = force_result.data
                    total_tokens += force_result.tokens_used

                    for item in force_items:
                        key = (item.drawing_name, item.text)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            final_items.append(item)

                    force_class = await self._classification.run(
                        force_items, emitter, trade=request.trade,
                    )
                    total_tokens += force_class.tokens_used
                    classified_keys = {
                        (c.drawing_name, c.text) for c in final_classified
                    }
                    for item in force_class.data:
                        key = (item.drawing_name, item.text)
                        if key not in classified_keys:
                            classified_keys.add(key)
                            final_classified.append(item)

                except Exception as exc:
                    logger.warning(
                        "Force-extract failed for drawing %s: %s", drawing_name, exc,
                    )
```

With:
```python
            async def _force_extract_one(drawing_name: str) -> None:
                """Force-extract a single missing drawing."""
                drawing_records = [
                    r for r in all_records
                    if (r.get("drawingName") or r.get("drawing_name", "")) == drawing_name
                ]
                if not drawing_records:
                    return

                force_input = {
                    "drawing_records": [
                        {
                            "drawing_name": r.get("drawingName") or r.get("drawing_name", ""),
                            "drawing_title": r.get("drawingTitle") or r.get("drawing_title", ""),
                            "text": r.get("text", ""),
                        }
                        for r in drawing_records
                    ],
                    "trade": request.trade,
                    "drawing_list": sorted(source_drawings),
                }

                try:
                    force_result = await self._extraction.run(
                        force_input, emitter, attempt=attempt_count + 1,
                    )
                    nonlocal total_tokens
                    total_tokens += force_result.tokens_used

                    for item in force_result.data:
                        key = (item.drawing_name, item.text)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            final_items.append(item)

                    force_class = await self._classification.run(
                        force_result.data, emitter, trade=request.trade,
                    )
                    total_tokens += force_class.tokens_used
                    classified_keys = {
                        (c.drawing_name, c.text) for c in final_classified
                    }
                    for item in force_class.data:
                        key = (item.drawing_name, item.text)
                        if key not in classified_keys:
                            classified_keys.add(key)
                            final_classified.append(item)

                except Exception as exc:
                    logger.warning(
                        "Force-extract failed for drawing %s: %s", drawing_name, exc,
                    )

            # Run force-extractions in parallel (batches of 5)
            batch_size = 5
            for i in range(0, len(force_missing), batch_size):
                batch = force_missing[i:i + batch_size]
                await asyncio.gather(*[_force_extract_one(d) for d in batch])
```

- [ ] **Step 6: Run all tests**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_pipeline_parallel.py tests/scope_pipeline/test_orchestrator.py -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add scope_pipeline/orchestrator.py scope_pipeline/config.py tests/test_pipeline_parallel.py
git commit -m "feat: scope gap pipeline parallelism — quality||document, batched force-extraction, optimized thresholds"
```

---

## Task 6: Update .env and Documentation

**Files:**
- Modify: `.env`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update .env with optimized values**

Add/update these settings in `.env`:

```env
# ── Latency Optimization v4 (2026-04-12) ────────────────────
# Layer 1: Smart Bulk Fetch
BULK_FETCH_ENABLED=true
BULK_FETCH_TIMEOUT=60

# Layer 2: Tiered LLM Routing
INTENT_MODEL=gpt-4.1-nano
FOLLOWUP_MODEL=gpt-4.1-nano

# Layer 3: Token Reduction (updated defaults)
MAX_OUTPUT_TOKENS=7000
NOTE_MAX_CHARS=200
API_TIMEOUT_SECONDS=60
CACHE_TTL_SUMMARY_DATA=900
PARALLEL_FETCH_CONCURRENCY=50

# Layer 4: Disk Cache
DISK_CACHE_ENABLED=true
DISK_CACHE_DIR=.cache
CACHE_WARMUP_ENABLED=true

# Layer 5: Pipeline Optimization (updated defaults)
SCOPE_GAP_COMPLETENESS_THRESHOLD=90.0
SCOPE_GAP_MAX_ATTEMPTS=2
```

- [ ] **Step 2: Add .cache to .gitignore**

Append to `.gitignore`:

```
# Disk cache (latency optimization)
.cache/
```

- [ ] **Step 3: Update CLAUDE.md with optimization v4 section**

Add the following section after the existing "OPTIMIZATION v2" section in `CLAUDE.md`:

```markdown
---

## OPTIMIZATION v4 — Applied 2026-04-12 (Latency Reduction)

### Problem
Both chat (~4-5 min) and scope gap (~6-10 min) endpoints too slow. Root cause: unnecessary pagination (228 calls when API returns all data in 1 call), unoptimized LLM routing, no persistent cache.

### 5-Layer Solution

| Layer | Change | Impact |
|-------|--------|--------|
| 1. Smart Bulk Fetch | Single API call replaces 228 paginated calls | 50s → 25s |
| 2. Tiered LLM | gpt-4.1-nano for intent + follow-up questions | 30s → 5s |
| 3. Token Reduction | max_output_tokens 10k→7k, note_max_chars 300→200 | 2.4min → 1.5min |
| 4. Disk Cache | File-backed L2 cache survives restarts | Repeat queries ~5ms |
| 5. Pipeline Parallel | Quality||Document parallel, force-extraction batched, threshold 90% | 60-120s saved |

### Performance After Fix

| Endpoint | Before | After |
|----------|--------|-------|
| Chat (uncached) | ~4-5 min | ~2 min |
| Chat (cached data) | ~4-5 min | ~1.5 min |
| Scope Gap (no backprop) | ~3 min | ~2.5 min |
| Scope Gap (worst case) | ~10 min | ~3.5 min |

### New .env Variables
```
BULK_FETCH_ENABLED=true
BULK_FETCH_TIMEOUT=60
INTENT_MODEL=gpt-4.1-nano
FOLLOWUP_MODEL=gpt-4.1-nano
DISK_CACHE_ENABLED=true
DISK_CACHE_DIR=.cache
CACHE_WARMUP_ENABLED=true
```

### Rollback
Each layer has independent .env toggle. See spec: `docs/superpowers/specs/2026-04-12-latency-optimization-design.md`
```

- [ ] **Step 4: Commit**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add .env .gitignore CLAUDE.md
git commit -m "docs: update env config and CLAUDE.md for latency optimization v4"
```

---

## Task 7: Full Regression Test Suite

**Files:**
- Run all existing tests + new tests

- [ ] **Step 1: Run complete test suite**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/ -v --timeout=120 2>&1 | tee test_results.txt`
Expected: All tests PASS

- [ ] **Step 2: Verify no import errors**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -c "from config import get_settings; s = get_settings(); print(f'bulk_fetch={s.bulk_fetch_enabled}, intent_model={s.intent_model}, disk_cache={s.disk_cache_enabled}')"` 
Expected: `bulk_fetch=True, intent_model=gpt-4.1-nano, disk_cache=True`

- [ ] **Step 3: Verify server starts without errors**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && timeout 10 python main.py 2>&1 || true`
Expected: Server starts, logs "All services initialised — API ready"

- [ ] **Step 4: Fix any failures and re-run**

If any tests fail, fix them and re-run until all pass. Common issues:
- Config import caching: use `Settings(openai_api_key="test")` directly in tests
- Mock patching: ensure `settings` module-level variable is patched correctly
- Async test issues: ensure `@pytest.mark.asyncio` on all async test functions

- [ ] **Step 5: Final commit if fixes were needed**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add -A
git commit -m "fix: resolve test regressions from latency optimization"
```

---

## Task 8: Deploy to Sandbox VM

**Files:**
- Deploy to 54.197.189.113

- [ ] **Step 1: Transfer code to sandbox**

```bash
scp -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" -r "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/" ubuntu@54.197.189.113:/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent/
```

- [ ] **Step 2: SSH into sandbox and verify**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113 "ls -la /home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent/"
```

- [ ] **Step 3: Install dependencies and run tests on sandbox**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113 "cd /home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent && pip install -r requirements.txt && python -m pytest tests/ -v --timeout=120"
```

- [ ] **Step 4: Start agent on sandbox**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113 "cd /home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent && nohup python main.py > agent.log 2>&1 &"
```

- [ ] **Step 5: Verify health endpoint**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113 "curl -s http://localhost:8003/health | python3 -m json.tool"
```
Expected: `{"status": "ok", ...}`

- [ ] **Step 6: Test latency with real request**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113 "time curl -s -X POST http://localhost:8003/api/chat -H 'Content-Type: application/json' -d '{\"project_id\": 7292, \"query\": \"generate electrical scope\"}' | python3 -m json.tool | grep pipeline_ms"
```
Expected: `pipeline_ms` < 120000 (2 minutes)

---

## Task 9: Deploy to Production VM

**Files:**
- Deploy to 13.217.22.125

- [ ] **Step 1: Transfer code to production**

```bash
scp -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" -r "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/" ubuntu@13.217.22.125:/home/ubuntu/vcsai/construction-intelligence-agent/
```

- [ ] **Step 2: SSH and verify**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" ubuntu@13.217.22.125 "ls -la /home/ubuntu/vcsai/construction-intelligence-agent/"
```

- [ ] **Step 3: Restart agent service**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" ubuntu@13.217.22.125 "sudo systemctl restart construction-agent && sleep 5 && sudo systemctl status construction-agent"
```

- [ ] **Step 4: Verify health**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" ubuntu@13.217.22.125 "curl -s http://localhost:8003/health | python3 -m json.tool"
```

- [ ] **Step 5: Test production latency**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" ubuntu@13.217.22.125 "time curl -s -X POST http://localhost:8003/api/chat -H 'Content-Type: application/json' -d '{\"project_id\": 7292, \"query\": \"generate electrical scope\"}' | python3 -m json.tool | grep pipeline_ms"
```

---

## Task 10: Push to GitHub

- [ ] **Step 1: Verify all changes committed locally**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git status
git log --oneline -10
```

- [ ] **Step 2: Push to remote**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git push origin main
```

- [ ] **Step 3: Verify push succeeded**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git log --oneline -5 origin/main
```
