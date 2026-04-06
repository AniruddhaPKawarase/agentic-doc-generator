"""scope_pipeline/routers/webhook_endpoints.py — Webhook receiver endpoint.

Handles incoming iFieldSmart platform webhooks with HMAC-SHA256 signature
verification, idempotency enforcement via Redis, and event parsing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap/webhooks", tags=["scope-gap-webhooks"])


@router.post("/project-event", status_code=202)
async def receive_project_event(
    request: Request,
    x_webhook_signature: str | None = Header(default=None),
    x_webhook_event_id: str | None = Header(default=None),
) -> Response:
    """Receive and process a project event webhook from iFieldSmart.

    Processing steps:
    1. Read raw body and verify HMAC-SHA256 signature.
    2. Check idempotency — return 200 if event already processed.
    3. Parse the JSON payload into a WebhookEvent.
    4. Mark event as processed and return 202 Accepted.

    Args:
        request: Incoming FastAPI request with ``app.state.webhook_handler`` set.
        x_webhook_signature: HMAC signature header (``sha256=<hex>``).
        x_webhook_event_id: Unique event identifier for idempotency.

    Returns:
        202 Accepted on success, 401 on invalid signature, 200 on duplicate,
        422 on parse failure.
    """
    webhook_handler = request.app.state.webhook_handler

    # Step 1: Read raw body and verify signature
    raw_body: bytes = await request.body()
    payload: str = raw_body.decode("utf-8")

    if not webhook_handler.verify_signature(payload, x_webhook_signature):
        logger.warning("Webhook signature verification failed for event_id=%s", x_webhook_event_id)
        return JSONResponse(status_code=401, content={"detail": "Invalid signature"})

    # Step 2: Idempotency check
    if x_webhook_event_id:
        already_processed = await webhook_handler.check_idempotency(x_webhook_event_id)
        if already_processed:
            logger.info("Duplicate webhook event_id=%s — skipping", x_webhook_event_id)
            return JSONResponse(status_code=200, content={"message": "Duplicate"})

    # Step 3: Parse event payload
    try:
        event = webhook_handler.parse_event(payload)
    except (ValueError, Exception) as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
        return JSONResponse(status_code=422, content={"detail": f"Invalid payload: {exc}"})

    # Step 4: Mark event as processed
    if x_webhook_event_id:
        await webhook_handler.mark_processed(x_webhook_event_id)

    logger.info(
        "Webhook received: event=%s project_id=%s event_id=%s",
        event.event,
        event.project_id,
        x_webhook_event_id,
    )

    return JSONResponse(
        status_code=202,
        content={
            "message": "Pre-computation queued",
            "event": event.event,
            "project_id": event.project_id,
        },
    )
