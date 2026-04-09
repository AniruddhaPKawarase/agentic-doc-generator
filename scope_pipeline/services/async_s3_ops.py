"""
scope_pipeline/services/async_s3_ops.py — Async wrapper for synchronous S3 operations.

Provides an async interface (put/get) on top of the sync s3_utils functions,
used by HighlightService which expects an async s3_ops object.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AsyncS3Ops:
    """Async adapter for synchronous s3_utils.operations functions."""

    def __init__(self, bucket_name: str, prefix: str = "") -> None:
        self._bucket = bucket_name
        self._prefix = prefix
        self._s3_available = False

        try:
            from s3_utils.client import get_s3_client
            self._client = get_s3_client()
            self._s3_available = self._client is not None
        except Exception as exc:
            logger.warning("AsyncS3Ops: S3 client init failed: %s", exc)
            self._client = None

    async def put(self, path: str, data: str) -> bool:
        """Upload a JSON string to S3."""
        if not self._s3_available:
            logger.warning("AsyncS3Ops.put: S3 not available, skipping write to %s", path)
            return False

        s3_key = self._resolve_key(path)
        loop = asyncio.get_running_loop()
        try:
            from s3_utils.operations import upload_bytes
            result = await loop.run_in_executor(
                None,
                lambda: upload_bytes(data.encode("utf-8"), s3_key, "application/json"),
            )
            return result
        except Exception as exc:
            logger.error("AsyncS3Ops.put failed for %s: %s", s3_key, exc)
            return False

    async def get(self, path: str) -> Optional[str]:
        """Download a JSON string from S3. Returns None if not found."""
        if not self._s3_available:
            return None

        s3_key = self._resolve_key(path)
        loop = asyncio.get_running_loop()
        try:
            from s3_utils.operations import download_bytes
            raw = await loop.run_in_executor(
                None,
                lambda: download_bytes(s3_key),
            )
            return raw.decode("utf-8") if raw else None
        except Exception as exc:
            logger.debug("AsyncS3Ops.get: no data at %s: %s", s3_key, exc)
            return None

    def _resolve_key(self, path: str) -> str:
        """Build the full S3 key from prefix + path."""
        if self._prefix:
            return f"{self._prefix}/{path}"
        return path
