"""Tests for the smart bulk fetch optimization in APIClient.

Validates:
  - _fetch_bulk() returns all records on success (no pagination params)
  - _fetch_bulk() returns None on timeout
  - _fetch_bulk() returns None on HTTP error
  - _fetch_bulk() returns None on empty response
  - _fetch_bulk() includes setId param when set_id is provided
  - _fetch_all_pages() tries bulk first and returns if successful
  - _fetch_all_pages() falls back to pagination when bulk times out
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("S3_AGENT_PREFIX", "construction-intelligence-agent")


def _make_api_response(records: list) -> dict:
    """Build a standard API response payload with the given records."""
    return {"success": True, "data": {"list": records}}


def _make_record(n: int) -> dict:
    return {"_id": f"rec_{n}", "projectId": 7298, "trade": "Electrical", "text": f"note {n}"}


def _make_client():
    """Create an APIClient with a mocked HTTP client and cache."""
    from services.api_client import APIClient
    from services.cache_service import CacheService

    cache = MagicMock(spec=CacheService)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    client = APIClient(cache)
    client._http = AsyncMock()
    return client


# ── _fetch_bulk() unit tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_bulk_returns_all_records():
    """Bulk fetch returns all 500 records and makes no pagination params."""
    records = [_make_record(i) for i in range(500)]
    payload = _make_api_response(records)

    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    client = _make_client()
    client._http.get = AsyncMock(return_value=mock_resp)

    result = await client._fetch_bulk(project_id=7298, trade="Electrical")

    assert result is not None
    assert len(result) == 500

    # Verify the HTTP call was made exactly once
    assert client._http.get.call_count == 1

    # Verify NO pagination params (skip, limit, page) in the request
    call_kwargs = client._http.get.call_args
    params = call_kwargs.kwargs.get("params", call_kwargs.args[1] if len(call_kwargs.args) > 1 else {})
    assert "skip" not in params
    assert "limit" not in params
    assert "page" not in params
    assert "pageSize" not in params


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_bulk_returns_none_on_timeout():
    """Bulk fetch returns None when the HTTP call times out."""
    client = _make_client()
    client._http.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    result = await client._fetch_bulk(project_id=7298, trade="Electrical")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_bulk_returns_none_on_http_error():
    """Bulk fetch returns None when API returns HTTP 500."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )

    client = _make_client()
    client._http.get = AsyncMock(return_value=mock_resp)

    result = await client._fetch_bulk(project_id=7298, trade="Electrical")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_bulk_returns_none_on_empty_response():
    """Bulk fetch returns None when the API returns an empty list."""
    payload = _make_api_response([])

    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    client = _make_client()
    client._http.get = AsyncMock(return_value=mock_resp)

    result = await client._fetch_bulk(project_id=7298, trade="Electrical")

    assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_bulk_with_set_id():
    """Bulk fetch includes setId in params when set_id is provided."""
    records = [_make_record(i) for i in range(10)]
    payload = _make_api_response(records)

    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    client = _make_client()
    client._http.get = AsyncMock(return_value=mock_resp)

    result = await client._fetch_bulk(project_id=7298, trade="Electrical", set_id=4730)

    assert result is not None
    assert len(result) == 10

    call_kwargs = client._http.get.call_args
    params = call_kwargs.kwargs.get("params", {})
    assert params.get("setId") == 4730
    assert params.get("projectId") == 7298
    assert params.get("trade") == "Electrical"


# ── _fetch_all_pages() integration tests ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_all_pages_tries_bulk_first():
    """_fetch_all_pages calls _fetch_bulk first and returns its result directly (1 HTTP call)."""
    records = [_make_record(i) for i in range(500)]
    payload = _make_api_response(records)

    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()

    client = _make_client()
    client._http.get = AsyncMock(return_value=mock_resp)

    result = await client._fetch_all_pages(project_id=7298, trade="Electrical")

    assert result is not None
    assert len(result) == 500

    # Bulk fetch is ONE call — no pagination calls should follow
    assert client._http.get.call_count == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetch_all_pages_falls_back_on_bulk_failure():
    """_fetch_all_pages falls back to paginated fetch when bulk times out."""
    # Bulk call times out; pagination page 1 returns a full page (50 records),
    # then all subsequent pages return empty — pagination terminates cleanly.
    full_page_records = [_make_record(i) for i in range(50)]
    full_page_payload = _make_api_response(full_page_records)
    empty_payload = _make_api_response([])

    call_count = {"n": 0}

    async def mock_get(path, **kwargs):
        call_count["n"] += 1
        # First call (bulk) times out
        if call_count["n"] == 1:
            raise httpx.TimeoutException("bulk timed out")
        # Second call (paginated page 1) returns a full page
        if call_count["n"] == 2:
            mock_resp = MagicMock()
            mock_resp.json.return_value = full_page_payload
            mock_resp.raise_for_status = MagicMock()
            return mock_resp
        # All subsequent calls (parallel batch pages) return empty → terminates
        mock_resp = MagicMock()
        mock_resp.json.return_value = empty_payload
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    client = _make_client()
    client._http.get = mock_get

    result = await client._fetch_all_pages(project_id=7298, trade="Electrical")

    # Should fall back to pagination and return at least the first page records
    assert result is not None
    assert len(result) == 50
    # At minimum: 1 bulk call + 1 page-1 call + batch calls
    assert call_count["n"] >= 2
    # The bulk call was the first (and only timed-out) call
    assert call_count["n"] > 1
