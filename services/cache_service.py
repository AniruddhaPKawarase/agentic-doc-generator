"""
services/cache_service.py  —  Two-level cache (L1 in-memory + L2 Redis).

L1: cachetools.TTLCache (process-local, zero latency)
L2: Redis (cross-process, cross-restart persistence)

If Redis is unavailable the service silently falls back to L1-only mode.
Cache keys are deterministic hashes of (projectId, trade, query_intent).

Semantic caching: for repetitive similar queries, a normalized query key
strips whitespace/punctuation variations so "create scope for plumbing"
and "Create  Scope  for  Plumbing!" hit the same cache entry.
"""

import json
import hashlib
import logging
import re
import time
from typing import Any, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# -- L1 in-memory cache ------------------------------------------------
# maxsize=500 entries, TTL=1 hour
_L1: TTLCache = TTLCache(maxsize=500, ttl=3600)


class CacheService:
    """
    Unified cache interface with semantic query normalization.

    Usage:
        cache = CacheService(redis_url="redis://localhost:6379/0")
        await cache.connect()
        await cache.set("key", data, ttl=300)
        data = await cache.get("key")
    """

    def __init__(self, redis_url: str = ""):
        self._redis_url = redis_url
        self._redis: Any = None
        self._redis_ok = False

    async def connect(self) -> None:
        """Try to establish Redis connection; silently degrade if it fails."""
        if not self._redis_url:
            logger.info("No REDIS_URL configured -- running L1-only cache mode")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
            )
            await self._redis.ping()
            self._redis_ok = True
            logger.info("Redis connected: %s", self._redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s) -- L1-only mode", exc)
            self._redis_ok = False

    async def disconnect(self) -> None:
        if self._redis and self._redis_ok:
            await self._redis.aclose()

    # -- Core API --------------------------------------------------------

    async def get(self, key: str) -> Optional[Any]:
        """Return cached value or None."""
        if key in _L1:
            return _L1[key]
        if self._redis_ok:
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    value = json.loads(raw)
                    _L1[key] = value
                    return value
            except Exception as exc:
                logger.debug("Redis get error: %s", exc)
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Store value in both L1 and L2 caches."""
        _L1[key] = value
        if self._redis_ok:
            try:
                await self._redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception as exc:
                logger.debug("Redis set error: %s", exc)

    async def delete(self, key: str) -> None:
        _L1.pop(key, None)
        if self._redis_ok:
            try:
                await self._redis.delete(key)
            except Exception as exc:
                logger.debug("Redis delete error: %s", exc)

    async def exists(self, key: str) -> bool:
        if key in _L1:
            return True
        if self._redis_ok:
            try:
                return bool(await self._redis.exists(key))
            except Exception:
                pass
        return False

    async def status(self) -> str:
        if self._redis_ok:
            try:
                await self._redis.ping()
                return "connected"
            except Exception:
                return "error"
        return "in-memory-only"

    # -- Key builders (with semantic normalization) ----------------------

    @staticmethod
    def _normalize_query(query: str) -> str:
        """
        Normalize a query string for semantic cache matching.

        Strips extra whitespace, lowercases, removes punctuation, and
        sorts words so that "Create scope for Plumbing" and
        "plumbing scope create" hit the same cache key.
        """
        q = query.lower().strip()
        q = re.sub(r'[^\w\s]', '', q)      # remove punctuation
        q = re.sub(r'\s+', ' ', q).strip()  # collapse whitespace
        words = sorted(q.split())            # sort words for order-independence
        return " ".join(words)

    @staticmethod
    def query_key(project_id: int, trade: str, query: str) -> str:
        """Deterministic cache key for a full query response (semantic)."""
        normalized = CacheService._normalize_query(query)
        raw = f"query:{project_id}:{trade.lower()}:{normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    def api_key(endpoint: str, project_id: int, trade: str = "") -> str:
        """Cache key for a MongoDB API response."""
        raw = f"api:{endpoint}:{project_id}:{trade.lower()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def session_key(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def token_key(session_id: str) -> str:
        return f"tokens:{session_id}"