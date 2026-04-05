"""tests/scope_pipeline/test_session_manager_integration.py — Session manager L1/L2/L3 integration tests.

Tests exercise cache hit/miss paths, list/filter, delete, and S3 layer
interactions with mocked cache and S3 services.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import ScopeGapSession
from scope_pipeline.services.session_manager import (
    ScopeGapSessionManager,
    _build_session_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(get_return=None):
    """Mock CacheService with async get/set/delete."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=get_return)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


def _make_s3(get_return=None):
    """Mock S3 ops with async get/put/delete."""
    s3 = MagicMock()
    s3.get = AsyncMock(return_value=get_return)
    s3.put = AsyncMock()
    s3.delete = AsyncMock()
    return s3


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------


class TestBuildSessionKey:
    """Verify deterministic session key generation."""

    def test_basic_key(self):
        key = _build_session_key(7166, "Electrical")
        assert key == "7166_electrical"

    def test_key_with_set_ids(self):
        key = _build_session_key(7166, "Electrical", set_ids=[4731, 4730])
        # set_ids should be sorted
        assert key == "7166_electrical_sets_4730_4731"

    def test_key_case_insensitive(self):
        assert _build_session_key(7166, "PLUMBING") == _build_session_key(7166, "plumbing")


# ---------------------------------------------------------------------------
# L1 cache hit/miss
# ---------------------------------------------------------------------------


class TestL1Cache:
    """Test in-memory L1 cache behavior."""

    @pytest.mark.asyncio
    async def test_l1_stores_session_after_creation(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert session.project_id == 7166

        # Second call should hit L1 (no additional L2 lookup)
        cache.get.reset_mock()
        session2 = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert session2.id == session.id
        cache.get.assert_not_awaited()  # L1 hit, no L2 call

    @pytest.mark.asyncio
    async def test_l1_returns_different_sessions_for_different_trades(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        s1 = await mgr.get_or_create(project_id=7166, trade="Electrical")
        s2 = await mgr.get_or_create(project_id=7166, trade="Plumbing")
        assert s1.id != s2.id


# ---------------------------------------------------------------------------
# L2 cache restore
# ---------------------------------------------------------------------------


class TestL2Restore:
    """Test L2 Redis restore + L1 promotion."""

    @pytest.mark.asyncio
    async def test_l2_hit_promotes_to_l1(self):
        existing = ScopeGapSession(project_id=7166, trade="Electrical", user_id="u1")
        serialised = existing.model_dump_json()

        cache = _make_cache(get_return=serialised)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        assert session.id == existing.id

        # Second call should hit L1
        cache.get.reset_mock()
        session2 = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        assert session2.id == existing.id
        cache.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_l2_read_failure_creates_new_session(self):
        cache = _make_cache()
        cache.get = AsyncMock(side_effect=Exception("Redis connection lost"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert session.project_id == 7166
        assert isinstance(session, ScopeGapSession)


# ---------------------------------------------------------------------------
# L3 S3 restore
# ---------------------------------------------------------------------------


class TestL3Restore:
    """Test S3 layer restore and promotion to L1."""

    @pytest.mark.asyncio
    async def test_l3_hit_promotes_to_l1(self):
        existing = ScopeGapSession(project_id=7201, trade="Plumbing", user_id="u2")
        serialised = existing.model_dump_json()

        cache = _make_cache(get_return=None)  # L2 miss
        s3 = _make_s3(get_return=serialised)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7201, trade="Plumbing", user_id="u2")
        assert session.id == existing.id
        s3.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_l3_miss_creates_new(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7201, trade="Plumbing")
        assert session.project_id == 7201
        assert isinstance(session, ScopeGapSession)

    @pytest.mark.asyncio
    async def test_l3_read_failure_creates_new_session(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3()
        s3.get = AsyncMock(side_effect=Exception("S3 timeout"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert isinstance(session, ScopeGapSession)

    @pytest.mark.asyncio
    async def test_no_s3_skips_l3(self):
        """When s3_ops is None, L3 is skipped entirely."""
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert isinstance(session, ScopeGapSession)


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdate:
    """Test session update persistence to all layers."""

    @pytest.mark.asyncio
    async def test_update_refreshes_updated_at(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        original_ts = session.updated_at

        import asyncio
        await asyncio.sleep(0.01)

        await mgr.update(session)
        assert session.updated_at > original_ts

    @pytest.mark.asyncio
    async def test_update_persists_to_l2(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        session.ambiguity_resolutions["amb_1"] = "Plumbing"
        await mgr.update(session)

        cache.set.assert_awaited_once()
        call_args = cache.set.call_args
        stored_json = call_args[0][1]
        stored = json.loads(stored_json)
        assert stored["ambiguity_resolutions"]["amb_1"] == "Plumbing"

    @pytest.mark.asyncio
    async def test_update_persists_to_l3_when_s3_available(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3()
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        await mgr.update(session)

        cache.set.assert_awaited_once()
        s3.put.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_l2_failure_does_not_raise(self):
        cache = _make_cache(get_return=None)
        cache.set = AsyncMock(side_effect=Exception("Redis write failed"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        # Should not raise
        await mgr.update(session)

    @pytest.mark.asyncio
    async def test_update_l3_failure_does_not_raise(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3()
        s3.put = AsyncMock(side_effect=Exception("S3 write failed"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        # Should not raise
        await mgr.update(session)


# ---------------------------------------------------------------------------
# List sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    """Test list_sessions with filtering."""

    @pytest.mark.asyncio
    async def test_list_returns_all_l1_sessions(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        await mgr.get_or_create(project_id=7166, trade="Electrical")
        await mgr.get_or_create(project_id=7201, trade="Plumbing")

        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_project_id(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        await mgr.get_or_create(project_id=7166, trade="Electrical")
        await mgr.get_or_create(project_id=7201, trade="Plumbing")

        sessions = mgr.list_sessions(project_id=7166)
        assert len(sessions) == 1
        assert sessions[0].project_id == 7166

    @pytest.mark.asyncio
    async def test_list_filter_by_trade(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        await mgr.get_or_create(project_id=7166, trade="Electrical")
        await mgr.get_or_create(project_id=7166, trade="Plumbing")

        sessions = mgr.list_sessions(trade="plumbing")  # case-insensitive
        assert len(sessions) == 1
        assert sessions[0].trade == "Plumbing"

    @pytest.mark.asyncio
    async def test_list_sorted_by_updated_at_descending(self):
        import asyncio
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        s1 = await mgr.get_or_create(project_id=7166, trade="Electrical")
        await asyncio.sleep(0.01)
        s2 = await mgr.get_or_create(project_id=7201, trade="Plumbing")

        sessions = mgr.list_sessions()
        # s2 was created later, should be first
        assert sessions[0].id == s2.id


# ---------------------------------------------------------------------------
# Get session by ID
# ---------------------------------------------------------------------------


class TestGetSessionById:
    """Test get_session_by_id lookup."""

    @pytest.mark.asyncio
    async def test_get_existing_session(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        found = mgr.get_session_by_id(session.id)
        assert found is not None
        assert found.id == session.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_none(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        found = mgr.get_session_by_id("nonexistent_id")
        assert found is None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    """Test session deletion from all layers."""

    @pytest.mark.asyncio
    async def test_delete_removes_from_l1(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        assert mgr.get_session_by_id(session.id) is not None

        await mgr.delete(session)
        assert mgr.get_session_by_id(session.id) is None

    @pytest.mark.asyncio
    async def test_delete_removes_from_l2(self):
        cache = _make_cache(get_return=None)
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        await mgr.delete(session)
        cache.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_removes_from_l3_when_s3_available(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3()
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        await mgr.delete(session)
        s3.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_l2_failure_does_not_raise(self):
        cache = _make_cache(get_return=None)
        cache.delete = AsyncMock(side_effect=Exception("Redis error"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical")
        # Should not raise
        await mgr.delete(session)

    @pytest.mark.asyncio
    async def test_delete_l3_failure_does_not_raise(self):
        cache = _make_cache(get_return=None)
        s3 = _make_s3()
        s3.delete = AsyncMock(side_effect=Exception("S3 error"))
        mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=s3)

        session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")
        # Should not raise
        await mgr.delete(session)


# ---------------------------------------------------------------------------
# S3 path helper
# ---------------------------------------------------------------------------


class TestS3Path:
    """Test static _s3_path helper."""

    def test_s3_path_with_user_id(self):
        path = ScopeGapSessionManager._s3_path("7166_electrical", "user123")
        assert "user123" in path
        assert "7166_electrical.json" in path

    def test_s3_path_anonymous(self):
        path = ScopeGapSessionManager._s3_path("7166_electrical", None)
        assert "anonymous" in path
