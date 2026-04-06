"""tests/scope_pipeline/test_webhook_handler.py — WebhookHandler unit tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from scope_pipeline.services.webhook_handler import WebhookHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-webhook-secret"


def _make_cache(get_return=None):
    """Return a mock cache service with async get/set."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=get_return)
    cache.set = AsyncMock()
    return cache


def _sign(payload: str, secret: str = _SECRET) -> str:
    """Produce a valid sha256= signature for the given payload."""
    mac = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _make_handler(secret: str = _SECRET, cache=None) -> WebhookHandler:
    return WebhookHandler(secret=secret, cache_service=cache or _make_cache())


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

class TestVerifySignature:
    def test_valid_signature(self):
        """A correctly signed payload must verify as True."""
        handler = _make_handler()
        payload = '{"event":"drawings.updated","project_id":7166}'
        sig = _sign(payload)

        assert handler.verify_signature(payload, sig) is True

    def test_invalid_signature(self):
        """A signature produced with a different secret must be rejected."""
        handler = _make_handler()
        payload = '{"event":"drawings.updated","project_id":7166}'
        bad_sig = _sign(payload, secret="wrong-secret")

        assert handler.verify_signature(payload, bad_sig) is False

    def test_missing_signature(self):
        """None signature must return False without raising."""
        handler = _make_handler()
        payload = '{"event":"drawings.updated","project_id":7166}'

        # Passing None (simulates missing header)
        assert handler.verify_signature(payload, None) is False  # type: ignore[arg-type]

    def test_empty_signature(self):
        """Empty-string signature must return False."""
        handler = _make_handler()
        payload = '{"event":"drawings.updated","project_id":7166}'

        assert handler.verify_signature(payload, "") is False

    def test_signature_without_prefix(self):
        """Signature lacking 'sha256=' prefix must return False."""
        handler = _make_handler()
        payload = '{"event":"drawings.updated","project_id":7166}'
        mac = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256)
        bare_hex = mac.hexdigest()  # no prefix

        assert handler.verify_signature(payload, bare_hex) is False


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------

class TestParseEvent:
    def test_parse_event_project_created(self):
        """Parses a project.created payload into a WebhookEvent."""
        from scope_pipeline.models_v2 import WebhookEvent

        payload = json.dumps({
            "event": "project.created",
            "project_id": 9999,
            "project_name": "New Tower",
        })
        handler = _make_handler()
        event = handler.parse_event(payload)

        assert isinstance(event, WebhookEvent)
        assert event.event == "project.created"
        assert event.project_id == 9999
        assert event.project_name == "New Tower"

    def test_parse_event_drawings_uploaded(self):
        """Parses a drawings.uploaded payload including changed_trades and drawing_count."""
        from scope_pipeline.models_v2 import WebhookEvent

        payload = json.dumps({
            "event": "drawings.uploaded",
            "project_id": 7166,
            "project_name": "Granville",
            "changed_trades": ["Electrical", "Plumbing"],
            "drawing_count": 5,
        })
        handler = _make_handler()
        event = handler.parse_event(payload)

        assert isinstance(event, WebhookEvent)
        assert event.event == "drawings.uploaded"
        assert event.project_id == 7166
        assert event.changed_trades == ["Electrical", "Plumbing"]
        assert event.drawing_count == 5

    def test_parse_event_invalid_json_raises(self):
        """Malformed JSON must raise ValueError."""
        handler = _make_handler()
        with pytest.raises(ValueError, match="not valid JSON"):
            handler.parse_event("{not: valid json}")

    def test_parse_event_missing_required_fields_raises(self):
        """Payload missing required fields must raise (Pydantic ValidationError)."""
        handler = _make_handler()
        with pytest.raises(Exception):  # pydantic.ValidationError
            handler.parse_event(json.dumps({"project_id": 123}))  # no 'event'


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_idempotency_check_exists(self):
        """Returns True when cache reports the event key already exists."""
        cache = _make_cache(get_return="1")
        handler = _make_handler(cache=cache)

        result = await handler.check_idempotency("evt-abc-123")

        assert result is True
        cache.get.assert_awaited_once_with("sg_webhook_idem:evt-abc-123")

    @pytest.mark.asyncio
    async def test_idempotency_check_not_exists(self):
        """Returns False when cache returns None (key absent)."""
        cache = _make_cache(get_return=None)
        handler = _make_handler(cache=cache)

        result = await handler.check_idempotency("evt-new-999")

        assert result is False
        cache.get.assert_awaited_once_with("sg_webhook_idem:evt-new-999")

    @pytest.mark.asyncio
    async def test_mark_processed_sets_key_with_ttl(self):
        """mark_processed sets the correct Redis key with the configured TTL."""
        cache = _make_cache()
        handler = WebhookHandler(secret=_SECRET, cache_service=cache, idempotency_ttl=7200)

        await handler.mark_processed("evt-xyz-456")

        cache.set.assert_awaited_once_with("sg_webhook_idem:evt-xyz-456", "1", 7200)

    @pytest.mark.asyncio
    async def test_idempotency_check_uses_prefix(self):
        """Idempotency keys must be namespaced with 'sg_webhook_idem:' prefix."""
        cache = _make_cache(get_return=None)
        handler = _make_handler(cache=cache)

        await handler.check_idempotency("evt-prefix-check")

        call_args = cache.get.call_args[0][0]
        assert call_args.startswith("sg_webhook_idem:")
