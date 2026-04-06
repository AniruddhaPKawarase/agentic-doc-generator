"""tests/scope_pipeline/test_trade_discovery_service.py"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scope_pipeline.services.trade_discovery_service import TradeDiscoveryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_api_client(records: list[dict]) -> MagicMock:
    """Build a mock api_client whose get_summary_by_trade returns `records`."""
    client = MagicMock()
    client.get_summary_by_trade = AsyncMock(return_value=records)
    client.get_summary_by_trade_and_set = AsyncMock(return_value=(records, []))
    return client


def _make_cache(initial: dict | None = None) -> MagicMock:
    """Build a mock cache_service backed by a plain dict."""
    store: dict = initial or {}

    async def _get(key: str):
        return store.get(key)

    async def _set(key: str, value, ttl: int = 3600):
        store[key] = value

    cache = MagicMock()
    cache.get = AsyncMock(side_effect=_get)
    cache.set = AsyncMock(side_effect=_set)
    cache._store = store  # expose for assertions
    return cache


# ---------------------------------------------------------------------------
# test_discover_trades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_trades():
    """Basic path: api returns records with setTrade, service counts per trade."""
    records = [
        {"_id": "1", "setTrade": "Electrical", "drawingName": "E-101"},
        {"_id": "2", "setTrade": "Electrical", "drawingName": "E-102"},
        {"_id": "3", "setTrade": "Electrical", "drawingName": "E-103"},
        {"_id": "4", "setTrade": "Plumbing",   "drawingName": "P-101"},
        {"_id": "5", "setTrade": "Mechanical", "drawingName": "M-101"},
        {"_id": "6", "setTrade": "Mechanical", "drawingName": "M-102"},
    ]

    api = _make_api_client(records)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=7166)

    # Correct trades present
    trade_names = [r["trade"] for r in result]
    assert "Electrical" in trade_names
    assert "Plumbing" in trade_names
    assert "Mechanical" in trade_names

    # Correct counts
    by_trade = {r["trade"]: r["record_count"] for r in result}
    assert by_trade["Electrical"] == 3
    assert by_trade["Plumbing"] == 1
    assert by_trade["Mechanical"] == 2

    # Sorted alphabetically
    assert result == sorted(result, key=lambda x: x["trade"])

    # API was called once
    api.get_summary_by_trade.assert_called_once_with(7166, "")

    # Result was cached
    cache_key = "sg_trades:7166"
    assert cache_key in cache._store


@pytest.mark.asyncio
async def test_discover_trades_with_trades_list_field():
    """Records may carry a `trades` list instead of (or in addition to) setTrade."""
    records = [
        {"_id": "1", "setTrade": "",      "trades": ["Electrical", "Fire Protection"]},
        {"_id": "2", "setTrade": "Electrical", "trades": []},
        {"_id": "3", "setTrade": "Plumbing",   "trades": None},
    ]

    api = _make_api_client(records)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=9999)

    trade_names = {r["trade"] for r in result}
    assert "Electrical" in trade_names
    assert "Fire Protection" in trade_names
    assert "Plumbing" in trade_names


@pytest.mark.asyncio
async def test_discover_trades_with_set_id():
    """When set_id is provided, uses get_summary_by_trade_and_set."""
    records = [
        {"_id": "1", "setTrade": "Electrical", "drawingName": "E-101"},
        {"_id": "2", "setTrade": "Electrical", "drawingName": "E-102"},
    ]

    api = _make_api_client(records)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=7166, set_id=42)

    assert len(result) == 1
    assert result[0]["trade"] == "Electrical"
    assert result[0]["record_count"] == 2

    # Correct endpoint called
    api.get_summary_by_trade_and_set.assert_called_once_with(7166, "", [42])

    # Cache key includes set_id
    assert "sg_trades:7166_42" in cache._store


# ---------------------------------------------------------------------------
# test_discover_trades_cached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_trades_cached():
    """Second call with same project_id must return cached result, no API call."""
    records = [
        {"_id": "1", "setTrade": "Electrical", "drawingName": "E-101"},
    ]

    api = _make_api_client(records)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    # First call — populates cache
    first = await svc.discover_trades(project_id=7201)
    assert api.get_summary_by_trade.call_count == 1

    # Second call — must hit cache
    second = await svc.discover_trades(project_id=7201)
    assert api.get_summary_by_trade.call_count == 1  # still 1, not 2

    assert first == second


@pytest.mark.asyncio
async def test_discover_trades_cached_pre_populated():
    """If cache already holds data, API is never called."""
    pre_cached = json.dumps([{"trade": "Structural", "record_count": 5}])
    initial_store = {"sg_trades:8000": pre_cached}

    api = _make_api_client([])
    cache = _make_cache(initial=initial_store)
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=8000)

    api.get_summary_by_trade.assert_not_called()
    assert result == [{"trade": "Structural", "record_count": 5}]


# ---------------------------------------------------------------------------
# test_discover_trades_empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_trades_empty():
    """API returns empty list and probe returns nothing → service returns [] without error."""
    api = _make_api_client([])
    # Add probe_trade_exists mock that returns 0 for all trades
    api.probe_trade_exists = AsyncMock(return_value=0)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=5555)

    assert result == []
    # Empty result is NOT cached (allows re-probe on next call)
    assert "sg_trades:5555" not in cache._store


@pytest.mark.asyncio
async def test_discover_trades_api_failure_returns_empty():
    """If the API raises an exception, service returns [] gracefully."""
    api = MagicMock()
    api.get_summary_by_trade = AsyncMock(side_effect=Exception("connection refused"))
    api.probe_trade_exists = AsyncMock(return_value=0)

    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=1234)

    assert result == []


@pytest.mark.asyncio
async def test_discover_trades_records_without_trade_fields():
    """Records missing both setTrade and trades produce no trade entries."""
    records = [
        {"_id": "1", "drawingName": "E-101"},          # no trade fields
        {"_id": "2", "setTrade": None, "trades": []},  # null/empty trade fields
        {"_id": "3", "setTrade": "Electrical"},         # one valid record
    ]

    api = _make_api_client(records)
    cache = _make_cache()
    svc = TradeDiscoveryService(api, cache)

    result = await svc.discover_trades(project_id=2222)

    # Only "Electrical" counted (1 record)
    assert len(result) == 1
    assert result[0]["trade"] == "Electrical"
    assert result[0]["record_count"] == 1
