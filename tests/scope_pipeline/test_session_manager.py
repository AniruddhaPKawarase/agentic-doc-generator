"""tests/scope_pipeline/test_session_manager.py — Session Manager tests."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import ScopeGapSession


def _make_cache_service(get_return=None):
    """Create a mock CacheService with async get/set/delete."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=get_return)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    return cache


@pytest.mark.asyncio
async def test_create_new_session():
    """When cache returns None, a brand-new session is created."""
    from scope_pipeline.services.session_manager import ScopeGapSessionManager

    cache = _make_cache_service(get_return=None)
    mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166, trade="Electrical")

    assert isinstance(session, ScopeGapSession)
    assert session.project_id == 7166
    assert session.trade == "Electrical"
    # Should have attempted L2 lookup
    cache.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_reuse_existing_session_from_cache():
    """When L2 cache returns a serialised session, it is reused (not created fresh)."""
    from scope_pipeline.services.session_manager import ScopeGapSessionManager

    existing = ScopeGapSession(
        project_id=7166,
        trade="Electrical",
        user_id="u1",
    )
    serialised = existing.model_dump_json()

    cache = _make_cache_service(get_return=serialised)
    mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166, trade="Electrical", user_id="u1")

    assert session.id == existing.id
    assert session.project_id == 7166
    assert session.trade == "Electrical"


@pytest.mark.asyncio
async def test_resolve_ambiguity_persists():
    """Adding an ambiguity resolution and calling update persists to L2."""
    from scope_pipeline.services.session_manager import ScopeGapSessionManager

    cache = _make_cache_service(get_return=None)
    mgr = ScopeGapSessionManager(cache_service=cache, s3_ops=None)

    session = await mgr.get_or_create(project_id=7166, trade="Plumbing")
    session.ambiguity_resolutions["amb_abc12345"] = "Plumbing"

    await mgr.update(session)

    # L2 cache.set should have been called with the session data
    cache.set.assert_awaited_once()
    call_args = cache.set.call_args
    stored_json = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("value", call_args[0][1])
    stored = json.loads(stored_json)
    assert stored["ambiguity_resolutions"]["amb_abc12345"] == "Plumbing"
