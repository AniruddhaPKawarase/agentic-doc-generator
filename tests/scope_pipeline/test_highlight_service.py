"""tests/scope_pipeline/test_highlight_service.py — HighlightService unit tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scope_pipeline.models_v2 import Highlight
from scope_pipeline.services.highlight_service import HighlightService, _CACHE_TTL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_s3(get_return=None):
    """Return a mock s3_ops with async get/put."""
    s3 = MagicMock()
    s3.get = AsyncMock(return_value=get_return)
    s3.put = AsyncMock()
    return s3


def _make_cache(get_return=None):
    """Return a mock cache_service with async get/set/delete."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=get_return)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


def _make_highlight(drawing_name: str = "E-101") -> Highlight:
    return Highlight(
        drawing_name=drawing_name,
        page=1,
        x=0.1,
        y=0.2,
        width=0.3,
        height=0.1,
        color="#FF0000",
        label="Test highlight",
    )


# ---------------------------------------------------------------------------
# test_create_highlight
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_highlight():
    """create() appends to an empty S3 array and writes back; cache is invalidated."""
    s3 = _make_s3(get_return=None)   # S3 has no existing data
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    hl = _make_highlight("E-101")

    result = await svc.create(project_id=7166, user_id="user_abc", highlight=hl)

    # Returns the same highlight
    assert result is hl

    # S3.put must have been called once
    s3.put.assert_awaited_once()
    call_args = s3.put.call_args
    path, data = call_args[0]

    # Path follows the expected pattern
    assert path == "highlights/7166/user_abc/E-101.json"

    # Written data is a JSON array containing the new highlight
    written = json.loads(data)
    assert isinstance(written, list)
    assert len(written) == 1
    assert written[0]["id"] == hl.id

    # Redis cache invalidated
    cache.delete.assert_awaited_once_with("hl:7166:user_abc:E-101")


@pytest.mark.asyncio
async def test_create_highlight_appends_to_existing():
    """create() appends to a non-empty existing S3 array."""
    existing_hl = _make_highlight("E-101")
    existing_data = json.dumps([existing_hl.model_dump(mode="json")])
    s3 = _make_s3(get_return=existing_data)
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    new_hl = _make_highlight("E-101")

    await svc.create(project_id=7166, user_id="user_abc", highlight=new_hl)

    call_args = s3.put.call_args
    _, data = call_args[0]
    written = json.loads(data)
    assert len(written) == 2
    ids = {item["id"] for item in written}
    assert existing_hl.id in ids
    assert new_hl.id in ids


# ---------------------------------------------------------------------------
# test_list_highlights_empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_highlights_empty():
    """list_for_drawing() returns [] when S3 returns None (no data yet)."""
    s3 = _make_s3(get_return=None)
    cache = _make_cache(get_return=None)

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    result = await svc.list_for_drawing(
        project_id=7166, user_id="user_abc", drawing_name="E-101"
    )

    assert result == []
    # S3 was consulted (cache miss)
    s3.get.assert_awaited_once_with("highlights/7166/user_abc/E-101.json")
    # Empty result cached
    cache.set.assert_awaited_once()
    set_call = cache.set.call_args
    key, value = set_call[0][0], set_call[0][1]
    assert key == "hl:7166:user_abc:E-101"
    assert json.loads(value) == []


# ---------------------------------------------------------------------------
# test_list_highlights_from_s3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_highlights_from_s3():
    """list_for_drawing() returns items from S3 on cache miss and caches them."""
    hl = _make_highlight("E-101")
    s3_data = json.dumps([hl.model_dump(mode="json")])
    s3 = _make_s3(get_return=s3_data)
    cache = _make_cache(get_return=None)  # cache miss

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    result = await svc.list_for_drawing(
        project_id=7166, user_id="user_abc", drawing_name="E-101"
    )

    assert len(result) == 1
    assert result[0]["id"] == hl.id

    # Cache was populated with TTL=300
    cache.set.assert_awaited_once()
    set_call = cache.set.call_args
    assert set_call[0][0] == "hl:7166:user_abc:E-101"
    assert set_call[1].get("ttl") == _CACHE_TTL or set_call[0][2] == _CACHE_TTL


@pytest.mark.asyncio
async def test_list_highlights_from_cache():
    """list_for_drawing() returns cached data without hitting S3."""
    hl = _make_highlight("E-101")
    cached_data = json.dumps([hl.model_dump(mode="json")])
    s3 = _make_s3()
    cache = _make_cache(get_return=cached_data)

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    result = await svc.list_for_drawing(
        project_id=7166, user_id="user_abc", drawing_name="E-101"
    )

    assert len(result) == 1
    assert result[0]["id"] == hl.id
    # S3 must NOT have been consulted
    s3.get.assert_not_awaited()


# ---------------------------------------------------------------------------
# test_delete_one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_one():
    """delete_one() removes the matching highlight and returns True."""
    hl1 = _make_highlight("E-101")
    hl2 = _make_highlight("E-101")
    s3_data = json.dumps([hl1.model_dump(mode="json"), hl2.model_dump(mode="json")])
    s3 = _make_s3(get_return=s3_data)
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    removed = await svc.delete_one(
        project_id=7166, user_id="user_abc", drawing_name="E-101", highlight_id=hl1.id
    )

    assert removed is True

    # S3 put called with array minus hl1
    s3.put.assert_awaited_once()
    _, data = s3.put.call_args[0]
    remaining = json.loads(data)
    assert len(remaining) == 1
    assert remaining[0]["id"] == hl2.id

    # Cache invalidated
    cache.delete.assert_awaited_once_with("hl:7166:user_abc:E-101")


@pytest.mark.asyncio
async def test_delete_one_not_found():
    """delete_one() returns False when the highlight_id does not exist."""
    hl = _make_highlight("E-101")
    s3_data = json.dumps([hl.model_dump(mode="json")])
    s3 = _make_s3(get_return=s3_data)
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    removed = await svc.delete_one(
        project_id=7166,
        user_id="user_abc",
        drawing_name="E-101",
        highlight_id="hl_nonexistent",
    )

    assert removed is False
    # S3 put must NOT be called (no change)
    s3.put.assert_not_awaited()


# ---------------------------------------------------------------------------
# test_update_one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_one():
    """update_one() merges updates into the matching highlight and writes back."""
    hl = _make_highlight("E-101")
    s3_data = json.dumps([hl.model_dump(mode="json")])
    s3 = _make_s3(get_return=s3_data)
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    updated = await svc.update_one(
        project_id=7166,
        user_id="user_abc",
        drawing_name="E-101",
        highlight_id=hl.id,
        updates={"label": "Updated label", "color": "#00FF00"},
    )

    assert updated is not None
    assert updated["id"] == hl.id
    assert updated["label"] == "Updated label"
    assert updated["color"] == "#00FF00"
    # Unchanged field is preserved
    assert updated["page"] == hl.page

    # S3 put called with updated array
    s3.put.assert_awaited_once()
    _, data = s3.put.call_args[0]
    stored = json.loads(data)
    assert len(stored) == 1
    assert stored[0]["label"] == "Updated label"

    # Cache invalidated
    cache.delete.assert_awaited_once_with("hl:7166:user_abc:E-101")


@pytest.mark.asyncio
async def test_update_one_not_found():
    """update_one() returns None when the highlight_id does not exist."""
    hl = _make_highlight("E-101")
    s3_data = json.dumps([hl.model_dump(mode="json")])
    s3 = _make_s3(get_return=s3_data)
    cache = _make_cache()

    svc = HighlightService(s3_ops=s3, cache_service=cache)
    result = await svc.update_one(
        project_id=7166,
        user_id="user_abc",
        drawing_name="E-101",
        highlight_id="hl_nonexistent",
        updates={"label": "Should not apply"},
    )

    assert result is None
    # S3 put must NOT be called (no change)
    s3.put.assert_not_awaited()
