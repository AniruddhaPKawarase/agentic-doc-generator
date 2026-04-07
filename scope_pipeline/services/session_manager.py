"""
scope_pipeline/services/session_manager.py — 3-layer session persistence.

L1: in-memory TTLCache (100 sessions, 1hr)
L2: Redis via CacheService (.get/.set/.delete)
L3: S3 (optional, for long-term persistence)

Sessions are keyed by {project_id}_{trade_lower} or
{project_id}_{trade_lower}_sets_{sorted_ids} when set_ids are provided.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, Union

from cachetools import TTLCache

from scope_pipeline.models import ScopeGapSession

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "sg_session:"
_REDIS_TTL = 604_800  # 7 days
_S3_PATH_PREFIX = "construction-intelligence-agent/scope_gap_sessions"


def _build_session_key(
    project_id: int,
    trade: str,
    set_ids: Optional[list[Union[int, str]]] = None,
) -> str:
    """Deterministic session key."""
    base = f"{project_id}_{trade.lower()}"
    if set_ids:
        sorted_ids = "_".join(str(sid) for sid in sorted(set_ids, key=str))
        return f"{base}_sets_{sorted_ids}"
    return base


class ScopeGapSessionManager:
    """3-layer session persistence: L1 memory -> L2 Redis -> L3 S3."""

    def __init__(self, cache_service: Any, s3_ops: Any = None) -> None:
        self._l1: TTLCache[str, ScopeGapSession] = TTLCache(maxsize=100, ttl=3600)
        self._cache = cache_service
        self._s3 = s3_ops

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        project_id: int,
        trade: str,
        set_ids: Optional[list[Union[int, str]]] = None,
        user_id: Optional[str] = None,
    ) -> ScopeGapSession:
        """Check L1 -> L2 -> L3 -> create new if not found."""
        key = _build_session_key(project_id, trade, set_ids)

        # L1 — in-memory
        session = self._l1.get(key)
        if session is not None:
            logger.debug("Session hit L1: %s", key)
            return session

        # L2 — Redis
        session = await self._get_from_l2(key)
        if session is not None:
            logger.debug("Session hit L2: %s", key)
            self._l1[key] = session
            return session

        # L3 — S3
        session = await self._get_from_l3(key, user_id)
        if session is not None:
            logger.debug("Session hit L3: %s", key)
            self._l1[key] = session
            return session

        # Create new
        logger.info("Creating new session: %s", key)
        session = ScopeGapSession(
            project_id=project_id,
            trade=trade,
            set_ids=set_ids,
            user_id=user_id,
        )
        self._l1[key] = session
        return session

    async def update(self, session: ScopeGapSession) -> None:
        """Persist session to all layers. L2+L3 run in parallel."""
        from datetime import datetime, timezone

        # Update timestamp (create new session with updated field via model_copy)
        updated = session.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        # Sync back to the original object's fields
        session.updated_at = updated.updated_at

        key = _build_session_key(session.project_id, session.trade, session.set_ids)
        serialised = session.model_dump_json()

        # L1
        self._l1[key] = session

        # L2 + L3 in parallel
        tasks = [self._persist_to_l2(key, serialised)]
        if self._s3 is not None:
            tasks.append(self._persist_to_l3(key, serialised, session.user_id))

        await asyncio.gather(*tasks, return_exceptions=True)

    def list_sessions(
        self,
        project_id: Optional[int] = None,
        trade: Optional[str] = None,
    ) -> list[ScopeGapSession]:
        """List sessions from L1 cache with optional filtering."""
        results: list[ScopeGapSession] = list(self._l1.values())
        if project_id is not None:
            results = [s for s in results if s.project_id == project_id]
        if trade is not None:
            trade_lower = trade.lower()
            results = [s for s in results if s.trade.lower() == trade_lower]
        return sorted(results, key=lambda s: s.updated_at, reverse=True)

    def get_session_by_id(self, session_id: str) -> Optional[ScopeGapSession]:
        """Find a session by its ID across L1 cache."""
        for session in self._l1.values():
            if session.id == session_id:
                return session
        return None

    async def delete(self, session: ScopeGapSession) -> None:
        """Remove session from all layers."""
        key = _build_session_key(session.project_id, session.trade, session.set_ids)

        # L1
        self._l1.pop(key, None)

        # L2
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            await self._cache.delete(redis_key)
        except Exception:
            logger.warning("Failed to delete session from L2: %s", key, exc_info=True)

        # L3
        if self._s3 is not None:
            try:
                s3_path = self._s3_path(key, session.user_id)
                await self._s3.delete(s3_path)
            except Exception:
                logger.warning("Failed to delete session from L3: %s", key, exc_info=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_from_l2(self, key: str) -> Optional[ScopeGapSession]:
        """Attempt to load session from Redis."""
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            raw = await self._cache.get(redis_key)
            if raw is not None:
                return ScopeGapSession.model_validate_json(raw)
        except Exception:
            logger.warning("L2 read failed for %s", key, exc_info=True)
        return None

    async def _get_from_l3(self, key: str, user_id: Optional[str]) -> Optional[ScopeGapSession]:
        """Attempt to load session from S3."""
        if self._s3 is None:
            return None
        try:
            s3_path = self._s3_path(key, user_id)
            raw = await self._s3.get(s3_path)
            if raw is not None:
                return ScopeGapSession.model_validate_json(raw)
        except Exception:
            logger.warning("L3 read failed for %s", key, exc_info=True)
        return None

    async def _persist_to_l2(self, key: str, serialised: str) -> None:
        """Write session JSON to Redis with TTL."""
        try:
            redis_key = f"{_REDIS_KEY_PREFIX}{key}"
            await self._cache.set(redis_key, serialised, ttl=_REDIS_TTL)
        except Exception:
            logger.warning("L2 write failed for %s", key, exc_info=True)

    async def _persist_to_l3(self, key: str, serialised: str, user_id: Optional[str]) -> None:
        """Write session JSON to S3."""
        try:
            s3_path = self._s3_path(key, user_id)
            await self._s3.put(s3_path, serialised)
        except Exception:
            logger.warning("L3 write failed for %s", key, exc_info=True)

    def backup_session_to_s3(self, session_id: str, session_data: dict) -> bool:
        """Persist session snapshot to S3 for disaster recovery."""
        try:
            import tempfile

            from s3_utils.operations import upload_file
            from config import get_settings

            settings = get_settings()
            if settings.storage_backend != "s3":
                return False

            s3_key = f"{settings.s3_agent_prefix}/sessions/{session_id}.json"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(session_data, f, default=str)
                tmp_path = f.name

            upload_file(tmp_path, s3_key)
            logger.info("Session %s backed up to S3: %s", session_id, s3_key)
            return True
        except Exception:
            logger.warning("Failed to backup session %s to S3", session_id, exc_info=True)
            return False

    @staticmethod
    def _s3_path(key: str, user_id: Optional[str]) -> str:
        uid = user_id or "anonymous"
        return f"{_S3_PATH_PREFIX}/{uid}/{key}.json"
