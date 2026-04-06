"""scope_pipeline/services/webhook_handler.py — Webhook signature validation and idempotency.

Verifies HMAC-SHA256 signatures from the iFieldSmart platform, parses
incoming WebhookEvent payloads, and enforces idempotency via Redis.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from scope_pipeline.models_v2 import WebhookEvent

logger = logging.getLogger(__name__)

_IDEM_KEY_PREFIX = "sg_webhook_idem:"


class WebhookHandler:
    """Handles incoming iFieldSmart webhooks: signature verification, parsing,
    and idempotency enforcement.

    Args:
        secret: Shared HMAC secret (raw string; encoded to UTF-8 internally).
        cache_service: Cache backend with async .get(key) and .set(key, value, ttl) methods.
        timestamp_tolerance: Unused tolerance seconds (reserved for future replay protection).
        idempotency_ttl: TTL in seconds for idempotency Redis keys (default 3600 = 1 hour).
    """

    def __init__(
        self,
        secret: str,
        cache_service: Any,
        timestamp_tolerance: int = 300,
        idempotency_ttl: int = 3600,
    ) -> None:
        self._secret: bytes = secret.encode("utf-8")
        self._cache = cache_service
        self._timestamp_tolerance = timestamp_tolerance
        self._idempotency_ttl = idempotency_ttl

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def verify_signature(self, payload: str, signature: str) -> bool:
        """Verify an HMAC-SHA256 signature from the iFieldSmart platform.

        Expected signature format: ``sha256=<hex_digest>``

        Uses :func:`hmac.compare_digest` for timing-safe comparison to
        prevent timing-based attacks.

        Args:
            payload: Raw request body string.
            signature: Value of the ``X-Signature`` (or equivalent) header.

        Returns:
            True if the signature is valid, False otherwise.
        """
        if not signature or not signature.startswith("sha256="):
            return False

        mac = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256)
        expected = "sha256=" + mac.hexdigest()

        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Payload parsing
    # ------------------------------------------------------------------

    def parse_event(self, payload: str) -> WebhookEvent:
        """Parse a raw JSON payload string into a :class:`WebhookEvent`.

        Args:
            payload: Raw JSON string from the webhook request body.

        Returns:
            Validated :class:`WebhookEvent` instance.

        Raises:
            ValueError: If the JSON is malformed or fails model validation.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Webhook payload is not valid JSON: {exc}") from exc

        return WebhookEvent(**data)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    async def check_idempotency(self, event_id: str) -> bool:
        """Check whether a webhook event has already been processed.

        Looks up the Redis key ``sg_webhook_idem:{event_id}``.

        Args:
            event_id: Unique identifier for the incoming webhook event.

        Returns:
            True if the event was already processed (key exists), False otherwise.
        """
        key = f"{_IDEM_KEY_PREFIX}{event_id}"
        value = await self._cache.get(key)
        return value is not None

    async def mark_processed(self, event_id: str) -> None:
        """Mark a webhook event as processed in Redis with a TTL.

        Sets the key ``sg_webhook_idem:{event_id}`` with the configured
        idempotency TTL so the entry expires automatically.

        Args:
            event_id: Unique identifier for the webhook event.
        """
        key = f"{_IDEM_KEY_PREFIX}{event_id}"
        await self._cache.set(key, "1", self._idempotency_ttl)
        logger.debug("Marked webhook event %s as processed (ttl=%ds)", event_id, self._idempotency_ttl)
