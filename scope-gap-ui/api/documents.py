"""
Document info helpers.
"""
from typing import Optional

from api.client import _get


def api_get_document_info(file_id: str) -> Optional[dict]:
    """Retrieve metadata about a generated document."""
    return _get(f"/api/documents/{file_id}/info")
