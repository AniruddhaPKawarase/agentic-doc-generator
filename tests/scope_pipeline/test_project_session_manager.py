"""tests/scope_pipeline/test_project_session_manager.py — ProjectSessionManager tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scope_pipeline.models_v2 import ProjectSession
from scope_pipeline.services.project_session_manager import (
    ProjectSessionManager,
    _REDIS_KEY_PREFIX,
    _REDIS_TTL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache_service(get_return=None):
    """Return a mock CacheService with async get/set/delete."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=get_return)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_or_create_new_session():
    """When L1 and L2 both miss, a brand-new ProjectSession is created."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166)

    assert isinstance(session, ProjectSession)
    assert session.project_id == 7166
    # L2 lookup must have been attempted
    cache.get.assert_awaited_once()
    # Session should be in L1 now
    assert mgr.get_by_project_id(7166) is session


@pytest.mark.asyncio
async def test_get_or_create_with_project_name_and_set_ids():
    """Session is created with the correct project_name and set_ids."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(
        project_id=7201,
        set_ids=[10, 20],
        project_name="Granville",
    )

    assert session.project_id == 7201
    assert session.project_name == "Granville"
    assert session.set_ids == [10, 20]
    # session_key encodes sorted set_ids
    assert session.session_key == "proj_7201_sets_10_20"


@pytest.mark.asyncio
async def test_get_or_create_cached_session_l1_hit():
    """Second call with same project_id returns the cached L1 session (no extra L2 call)."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session_first = await mgr.get_or_create(project_id=7166, project_name="Hotel")
    session_second = await mgr.get_or_create(project_id=7166, project_name="Hotel")

    # Same object from L1
    assert session_first is session_second
    # L2 get called only once (on first miss)
    assert cache.get.await_count == 1


@pytest.mark.asyncio
async def test_get_or_create_cached_session_l2_hit():
    """When L1 is cold but L2 returns a serialised session, that session is returned."""
    existing = ProjectSession(project_id=7212, project_name="Office")
    serialised = existing.model_dump_json()

    cache = _make_cache_service(get_return=serialised)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7212, project_name="Office")

    assert session.project_id == 7212
    assert session.project_name == "Office"
    # Restored session has the same session_key as the original
    assert session.session_key == existing.session_key
    # Should now be in L1
    assert mgr.get_by_project_id(7212) is session


@pytest.mark.asyncio
async def test_update_persists_to_l2():
    """update() writes the serialised session to Redis with the correct key and TTL."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7222, project_name="Plaza")
    # Simulate a change
    session.ambiguity_resolutions["amb_001"] = "Electrical"

    await mgr.update(session)

    cache.set.assert_awaited_once()
    call_args = cache.set.call_args
    positional = call_args[0]
    kwargs = call_args[1] if call_args[1] else {}

    redis_key_used = positional[0]
    stored_json = positional[1]
    ttl_used = kwargs.get("ttl", positional[2] if len(positional) > 2 else None)

    assert redis_key_used == f"{_REDIS_KEY_PREFIX}{session.session_key}"
    assert ttl_used == _REDIS_TTL

    stored = json.loads(stored_json)
    assert stored["ambiguity_resolutions"]["amb_001"] == "Electrical"
    assert stored["project_id"] == 7222


@pytest.mark.asyncio
async def test_update_refreshes_updated_at():
    """update() mutates session.updated_at to the current time."""
    from datetime import timezone

    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7223)
    original_ts = session.updated_at

    await mgr.update(session)

    # updated_at must be at-or-after the original value
    assert session.updated_at.tzinfo is not None
    assert session.updated_at >= original_ts


@pytest.mark.asyncio
async def test_delete_removes_from_all_layers():
    """delete() removes from L1 and calls cache.delete for L2."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166)

    # Confirm L1 presence before delete
    assert mgr.get_by_project_id(7166) is session

    await mgr.delete(session)

    # L1 should be empty for this project
    assert mgr.get_by_project_id(7166) is None

    # L2 delete should have been called with correct key
    cache.delete.assert_awaited_once()
    redis_key_used = cache.delete.call_args[0][0]
    assert redis_key_used == f"{_REDIS_KEY_PREFIX}{session.session_key}"


@pytest.mark.asyncio
async def test_delete_with_s3_ops():
    """delete() also calls s3_ops.delete when s3_ops is provided."""
    cache = _make_cache_service(get_return=None)
    s3_ops = MagicMock()
    s3_ops.delete = AsyncMock()
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=s3_ops)

    session = await mgr.get_or_create(project_id=7166)
    await mgr.delete(session)

    s3_ops.delete.assert_awaited_once()
    s3_path_used = s3_ops.delete.call_args[0][0]
    assert session.session_key in s3_path_used


@pytest.mark.asyncio
async def test_get_by_project_id_returns_none_when_not_cached():
    """get_by_project_id returns None when nothing is in L1 for that project."""
    cache = _make_cache_service(get_return=None)
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    result = mgr.get_by_project_id(9999)
    assert result is None


@pytest.mark.asyncio
async def test_l2_failure_does_not_raise():
    """If Redis raises during get_or_create, a new session is still returned."""
    cache = MagicMock()
    cache.get = AsyncMock(side_effect=ConnectionError("redis down"))
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166)
    assert isinstance(session, ProjectSession)
    assert session.project_id == 7166


@pytest.mark.asyncio
async def test_l2_write_failure_does_not_raise():
    """If Redis raises during update, the call completes without propagating the error."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(side_effect=ConnectionError("redis down"))
    cache.delete = AsyncMock()
    mgr = ProjectSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166)
    # Should not raise even though L2 write fails
    await mgr.update(session)
