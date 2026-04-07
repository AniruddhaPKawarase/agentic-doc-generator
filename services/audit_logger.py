"""
services/audit_logger.py — Write audit events to S3.
"""
import json
import tempfile
import logging
from datetime import datetime, timezone
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


def log_audit_event(
    event_type: str,
    project_id: int = 0,
    trade: str = "",
    file_id: str = "",
    request_ip: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Write an audit event to S3 audit_logs/ prefix. Never raises."""
    settings = get_settings()
    if settings.storage_backend != "s3":
        return False
    try:
        from s3_utils.operations import upload_file

        now = datetime.now(timezone.utc)
        event = {
            "timestamp": now.isoformat(),
            "event_type": event_type,
            "project_id": project_id,
            "trade": trade,
            "file_id": file_id,
            "request_ip": request_ip,
            **(metadata or {}),
        }

        date_prefix = now.strftime("%Y-%m-%d")
        s3_key = (
            f"{settings.s3_agent_prefix}/audit_logs/{date_prefix}/"
            f"{event_type}_{now.strftime('%H%M%S')}_{file_id[:8] if file_id else 'na'}.json"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(event, f, default=str)
            tmp_path = f.name

        upload_file(tmp_path, s3_key)
        return True
    except Exception as exc:
        logger.warning("Audit log failed: %s", exc)
        return False
