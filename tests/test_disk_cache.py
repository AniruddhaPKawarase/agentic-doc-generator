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
    return str(tmp_path / "disk_cache")


@pytest.mark.asyncio
async def test_disk_cache_write_and_read(cache_dir):
    from services.cache_service import DiskCache
    dc = DiskCache(cache_dir)
    await dc.set("test_key", {"data": [1, 2, 3]}, ttl=300)
    result = await dc.get("test_key")
    assert result == {"data": [1, 2, 3]}


@pytest.mark.asyncio
async def test_disk_cache_returns_none_for_missing_key(cache_dir):
    from services.cache_service import DiskCache
    dc = DiskCache(cache_dir)
    result = await dc.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_respects_ttl(cache_dir):
    from services.cache_service import DiskCache
    dc = DiskCache(cache_dir)
    await dc.set("expire_key", {"val": 1}, ttl=1)
    result = await dc.get("expire_key")
    assert result == {"val": 1}
    await asyncio.sleep(1.1)
    result = await dc.get("expire_key")
    assert result is None


@pytest.mark.asyncio
async def test_disk_cache_cleanup_removes_expired(cache_dir):
    from services.cache_service import DiskCache
    dc = DiskCache(cache_dir)
    await dc.set("old_key", {"val": 1}, ttl=1)
    await asyncio.sleep(1.1)
    removed = await dc.cleanup()
    assert removed >= 1
    cache_path = Path(cache_dir)
    json_files = list(cache_path.glob("*.json"))
    assert len(json_files) == 0


@pytest.mark.asyncio
async def test_disk_cache_survives_corrupted_file(cache_dir):
    from services.cache_service import DiskCache
    dc = DiskCache(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)
    import hashlib
    key_hash = hashlib.sha256("corrupt_key".encode()).hexdigest()[:32]
    corrupt_path = Path(cache_dir) / f"{key_hash}.json"
    corrupt_path.write_text("NOT VALID JSON{{{")
    result = await dc.get("corrupt_key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_service_uses_disk_l2(cache_dir):
    from services.cache_service import CacheService, DiskCache
    cache = CacheService(redis_url="")
    disk = DiskCache(cache_dir)
    await disk.set("my_key", {"cached": True}, ttl=300)
    cache._disk = disk
    result = await cache.get("my_key")
    assert result == {"cached": True}
