"""scope_pipeline/services/project_session_manager.py — 3-layer project session persistence.

L1: in-memory TTLCache (100 sessions, 1hr)
L2: Redis via CacheService (.get/.set/.delete)
L3: S3 (optional, via s3_ops parameter — reserved for future use)

Sessions are keyed by ProjectSession.session_key which encodes project_id and
sorted set_ids (if provided).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from cachetools import TTLCache

from scope_pipeline.models_v2 import ProjectSession

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "sg_proj_session:"
_REDIS_TTL = 604_800  # 7 days


class ProjectSessionManager:
    """3-layer project session persistence: L1 memory -> L2 Redis -> (L3 S3 optional)."""

    def __init__(self, cache_service: Any, s3_ops: Any = None) -> None:
        self._l1: TTLCache[str, ProjectSession] = TTLCache(maxsize=100, ttl=3600)
        self._cache = cache_service
        self._s3 = s3_ops

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        project_id: int,
        set_ids: Optional[list[Union[int, str]]] = None,
        project_name: str = "",
    ) -> ProjectSession:
        """Check L1 -> L2 -> create new if not found.

        Returns an existing ProjectSession from cache or a freshly created one.
        """
        # Build a temporary session to derive the stable session_key
        _probe = ProjectSession(project_id=project_id, set_ids=set_ids, project_name=project_name)
        key = _probe.session_key

        # L1 — in-memory
        session = self._l1.get(key)
        if session is not None:
            logger.debug("ProjectSession hit L1: %s", key)
            return session

        # L2 — Redis
        session = await self._get_from_l2(key)
        if session is not None:
            logger.debug("ProjectSession hit L2: %s", key)
            self._l1[key] = session
            return session

        # Create new
        logger.info("Creating new ProjectSession: %s", key)
        session = ProjectSession(
            project_id=project_id,
            set_ids=set_ids,
            project_name=project_name,
        )
        self._l1[key] = session
        return session

    async def update(self, session: ProjectSession) -> None:
        """Update updated_at timestamp, then persist session to L1 and L2."""
        updated = session.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        # Mutate the caller's object to keep the reference consistent
        session.updated_at = updated.updated_at

        key = session.session_key
        serialised = session.model_dump_json()

        # L1
        self._l1[key] = session

        # L2 (and L3 if available) in parallel
        tasks = [self._persist_to_l2(key, serialised)]
        if self._s3 is not None:
            tasks.append(self._persist_to_l3(key, serialised))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def delete(self, session: ProjectSession) -> None:
        """Remove session from L1 and L2."""
        key = session.session_key

        # L1
        self._l1.pop(key, None)

        # L2
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            await self._cache.delete(redis_key)
        except Exception:
            logger.warning("Failed to delete ProjectSession from L2: %s", key, exc_info=True)

        # L3
        if self._s3 is not None:
            try:
                s3_path = f"construction-intelligence-agent/project_sessions/{key}.json"
                await self._s3.delete(s3_path)
            except Exception:
                logger.warning("Failed to delete ProjectSession from L3: %s", key, exc_info=True)

    def get_by_project_id(self, project_id: int) -> Optional[ProjectSession]:
        """Scan L1 cache and return the first session matching project_id."""
        for session in self._l1.values():
            if session.project_id == project_id:
                return session
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_from_l2(self, key: str) -> Optional[ProjectSession]:
        """Attempt to load a ProjectSession from Redis."""
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            raw = await self._cache.get(redis_key)
            if raw is not None:
                return ProjectSession.model_validate_json(raw)
        except Exception:
            logger.warning("L2 read failed for ProjectSession %s", key, exc_info=True)
        return None

    async def _persist_to_l2(self, key: str, serialised: str) -> None:
        """Write session JSON to Redis with TTL."""
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            await self._cache.set(redis_key, serialised, ttl=_REDIS_TTL)
        except Exception:
            logger.warning("L2 write failed for ProjectSession %s", key, exc_info=True)

    async def _persist_to_l3(self, key: str, serialised: str) -> None:
        """Write session JSON to S3 (optional layer)."""
        try:
            s3_path = f"construction-intelligence-agent/project_sessions/{key}.json"
            await self._s3.put(s3_path, serialised)
        except Exception:
            logger.warning("L3 write failed for ProjectSession %s", key, exc_info=True)
