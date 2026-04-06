"""tests/scope_pipeline/test_webhook_endpoints.py — Webhook receiver endpoint tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from scope_pipeline.routers.webhook_endpoints import router
from scope_pipeline.models_v2 import WebhookEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-webhook-secret"
_EVENT_ID = "evt-test-001"
_ENDPOINT = "/api/scope-gap/webhooks/project-event"

_VALID_PAYLOAD = json.dumps({
    "event": "drawings.updated",
    "project_id": 7166,
    "project_name": "Granville",
    "changed_trades": ["Electrical"],
    "drawing_count": 3,
})


def _sign(payload: str, secret: str = _SECRET) -> str:
    """Produce a valid sha256= HMAC signature for the given payload."""
    mac = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def _make_webhook_handler(
    *,
    signature_valid: bool = True,
    already_processed: bool = False,
) -> MagicMock:
    """Build a mock WebhookHandler with configurable behaviour."""
    handler = MagicMock()
    handler.verify_signature = MagicMock(return_value=signature_valid)
    handler.check_idempotency = AsyncMock(return_value=already_processed)
    handler.mark_processed = AsyncMock()
    handler.parse_event = MagicMock(
        return_value=WebhookEvent(
            event="drawings.updated",
            project_id=7166,
            project_name="Granville",
            changed_trades=["Electrical"],
            drawing_count=3,
        )
    )
    return handler


def _make_app(webhook_handler: MagicMock) -> FastAPI:
    """Create a minimal FastAPI app with the webhook router and mock handler."""
    app = FastAPI()
    app.include_router(router)
    app.state.webhook_handler = webhook_handler
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWebhookEndpoints:
    @pytest.mark.asyncio
    async def test_webhook_valid(self):
        """A valid, signed, non-duplicate webhook returns 202 Accepted."""
        handler = _make_webhook_handler(signature_valid=True, already_processed=False)
        app = _make_app(handler)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            signature = _sign(_VALID_PAYLOAD)
            response = await client.post(
                _ENDPOINT,
                content=_VALID_PAYLOAD.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Event-Id": _EVENT_ID,
                },
            )

        assert response.status_code == 202
        body = response.json()
        assert body["message"] == "Pre-computation queued"
        assert body["event"] == "drawings.updated"
        assert body["project_id"] == 7166

        handler.verify_signature.assert_called_once()
        handler.check_idempotency.assert_awaited_once_with(_EVENT_ID)
        handler.mark_processed.assert_awaited_once_with(_EVENT_ID)

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self):
        """A request with an invalid HMAC signature returns 401 Unauthorized."""
        handler = _make_webhook_handler(signature_valid=False)
        app = _make_app(handler)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                _ENDPOINT,
                content=_VALID_PAYLOAD.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": "sha256=badhexvalue",
                    "X-Webhook-Event-Id": _EVENT_ID,
                },
            )

        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

        # Idempotency check must NOT be reached after auth failure
        handler.check_idempotency.assert_not_awaited()
        handler.mark_processed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_webhook_duplicate(self):
        """A duplicate event (idempotency key already set) returns 200 with 'Duplicate'."""
        handler = _make_webhook_handler(signature_valid=True, already_processed=True)
        app = _make_app(handler)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            signature = _sign(_VALID_PAYLOAD)
            response = await client.post(
                _ENDPOINT,
                content=_VALID_PAYLOAD.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Event-Id": _EVENT_ID,
                },
            )

        assert response.status_code == 200
        assert response.json()["message"] == "Duplicate"

        # Event must not be re-processed
        handler.parse_event.assert_not_called()
        handler.mark_processed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_webhook_invalid_payload_returns_422(self):
        """A payload that fails parsing returns 422 Unprocessable Entity."""
        handler = _make_webhook_handler(signature_valid=True, already_processed=False)
        handler.parse_event = MagicMock(side_effect=ValueError("not valid JSON"))
        app = _make_app(handler)
        transport = httpx.ASGITransport(app=app)

        bad_payload = "{not: valid json}"
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            signature = _sign(bad_payload)
            response = await client.post(
                _ENDPOINT,
                content=bad_payload.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Event-Id": _EVENT_ID,
                },
            )

        assert response.status_code == 422
        handler.mark_processed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_webhook_missing_event_id_still_processes(self):
        """A valid signed request without an event-id header is accepted (no idempotency check)."""
        handler = _make_webhook_handler(signature_valid=True, already_processed=False)
        app = _make_app(handler)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            signature = _sign(_VALID_PAYLOAD)
            response = await client.post(
                _ENDPOINT,
                content=_VALID_PAYLOAD.encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": signature,
                    # No X-Webhook-Event-Id header
                },
            )

        assert response.status_code == 202
        # Idempotency check skipped when no event_id
        handler.check_idempotency.assert_not_awaited()
        handler.mark_processed.assert_not_awaited()
