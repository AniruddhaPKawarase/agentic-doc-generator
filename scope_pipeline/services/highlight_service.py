"""scope_pipeline/services/highlight_service.py — User highlight persistence.

Highlights are stored per-drawing in S3 as a JSON array. Redis provides a
short-lived cache to avoid repeated S3 reads.

S3 path:  {prefix}/{project_id}/{user_id}/{drawing_name}.json
Cache key: hl:{project_id}:{user_id}:{drawing_name}
Cache TTL: 300 s
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from scope_pipeline.models_v2 import Highlight

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds


class HighlightService:
    """Persist and retrieve user-drawn highlights via S3 + Redis cache."""

    def __init__(self, s3_ops: Any, cache_service: Any, s3_prefix: str = "highlights") -> None:
        self._s3 = s3_ops
        self._cache = cache_service
        self._prefix = s3_prefix

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(self, project_id: Any, user_id: str, highlight: Highlight) -> Highlight:
        """Append a new highlight to the drawing's JSON array in S3.

        Reads the existing array, appends the new highlight, writes back,
        then invalidates the Redis cache key.

        Returns:
            The highlight that was stored (unchanged from input).
        """
        path = self._s3_path(project_id, user_id, highlight.drawing_name)
        existing = await self._read_array(path)
        updated = existing + [highlight.model_dump(mode="json")]
        await self._s3.put(path, json.dumps(updated))
        await self._invalidate_cache(project_id, user_id, highlight.drawing_name)
        logger.debug(
            "HighlightService.create: stored %s for project=%s user=%s drawing=%s",
            highlight.id,
            project_id,
            user_id,
            highlight.drawing_name,
        )
        return highlight

    async def list_for_drawing(
        self, project_id: Any, user_id: str, drawing_name: str
    ) -> list[dict]:
        """Return all highlights for a drawing, using Redis cache when possible.

        Cache miss order: Redis → S3 → [].
        Populates the cache on an S3 hit.

        Returns:
            List of highlight dicts (may be empty).
        """
        cache_key = self._cache_key(project_id, user_id, drawing_name)
        cached = await self._safe_cache_get(cache_key)
        if cached is not None:
            logger.debug(
                "HighlightService.list_for_drawing: cache hit for %s", cache_key
            )
            return json.loads(cached)

        path = self._s3_path(project_id, user_id, drawing_name)
        items = await self._read_array(path)
        await self._safe_cache_set(cache_key, json.dumps(items))
        return items

    async def delete_one(
        self, project_id: Any, user_id: str, drawing_name: str, highlight_id: str
    ) -> bool:
        """Remove a single highlight by id from the drawing's S3 array.

        Returns:
            True if an item was removed, False if no item with that id existed.
        """
        path = self._s3_path(project_id, user_id, drawing_name)
        existing = await self._read_array(path)
        filtered = [item for item in existing if item.get("id") != highlight_id]
        if len(filtered) == len(existing):
            return False
        await self._s3.put(path, json.dumps(filtered))
        await self._invalidate_cache(project_id, user_id, drawing_name)
        logger.debug(
            "HighlightService.delete_one: removed %s from drawing=%s", highlight_id, drawing_name
        )
        return True

    async def update_one(
        self,
        project_id: Any,
        user_id: str,
        drawing_name: str,
        highlight_id: str,
        updates: dict,
    ) -> Optional[dict]:
        """Apply field-level updates to a single highlight in the S3 array.

        Returns:
            The updated highlight dict, or None if no highlight with that id found.
        """
        path = self._s3_path(project_id, user_id, drawing_name)
        existing = await self._read_array(path)

        updated_item: Optional[dict] = None
        new_array: list[dict] = []
        for item in existing:
            if item.get("id") == highlight_id:
                merged = {**item, **updates}
                updated_item = merged
                new_array.append(merged)
            else:
                new_array.append(item)

        if updated_item is None:
            return None

        await self._s3.put(path, json.dumps(new_array))
        await self._invalidate_cache(project_id, user_id, drawing_name)
        logger.debug(
            "HighlightService.update_one: updated %s in drawing=%s", highlight_id, drawing_name
        )
        return updated_item

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _s3_path(self, project_id: Any, user_id: str, drawing_name: str) -> str:
        return f"{self._prefix}/{project_id}/{user_id}/{drawing_name}.json"

    def _cache_key(self, project_id: Any, user_id: str, drawing_name: str) -> str:
        return f"hl:{project_id}:{user_id}:{drawing_name}"

    async def _read_array(self, path: str) -> list[dict]:
        """Read and parse a JSON array from S3; return [] on miss or parse error."""
        try:
            raw = await self._s3.get(path)
            if raw is None:
                return []
            return json.loads(raw)
        except Exception:
            logger.warning("HighlightService._read_array: failed to read %s", path, exc_info=True)
            return []

    async def _invalidate_cache(
        self, project_id: Any, user_id: str, drawing_name: str
    ) -> None:
        cache_key = self._cache_key(project_id, user_id, drawing_name)
        try:
            await self._cache.delete(cache_key)
        except Exception:
            logger.warning(
                "HighlightService._invalidate_cache: failed to delete key %s",
                cache_key,
                exc_info=True,
            )

    async def _safe_cache_get(self, key: str) -> Optional[str]:
        try:
            return await self._cache.get(key)
        except Exception:
            logger.warning("HighlightService._safe_cache_get: failed for key %s", key, exc_info=True)
            return None

    async def _safe_cache_set(self, key: str, value: str) -> None:
        try:
            await self._cache.set(key, value, ttl=_CACHE_TTL)
        except Exception:
            logger.warning("HighlightService._safe_cache_set: failed for key %s", key, exc_info=True)
