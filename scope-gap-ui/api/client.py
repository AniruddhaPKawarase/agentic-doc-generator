"""
Low-level HTTP helpers — _get(), _post(), health(), fetch_document_bytes().
"""
import re
from typing import Optional

import requests

from config import API_BASE, REQUEST_TIMEOUT


def _get(path: str, params: dict = None) -> Optional[dict]:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {REQUEST_TIMEOUT}s"}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def _post(path: str, payload: dict, timeout: int = 0) -> Optional[dict]:
    effective_timeout = timeout or REQUEST_TIMEOUT
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload,
                          timeout=effective_timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return {"error": f"Request timed out after {effective_timeout}s. The pipeline may still be running — check status before retrying."}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        body = exc.response.text[:200] if exc.response else ""
        return {"error": f"API error {status}: {body}"}
    except Exception as exc:
        return {"error": f"Unexpected error: {str(exc)[:200]}"}


def health() -> Optional[dict]:
    """Check API health."""
    return _get("/health")


def get_raw_data(
    project_id: int, trade: str, set_id: int = None, skip: int = 0, limit: int = 500
) -> Optional[dict]:
    """Fetch raw API records for the data expander."""
    params = {"trade": trade, "skip": skip, "limit": limit}
    if set_id:
        params["set_id"] = set_id
    return _get(f"/api/projects/{project_id}/raw-data", params=params)


def fetch_document_bytes(doc_path: str) -> tuple[bytes | None, str]:
    """Download document bytes from backend. Returns (bytes, filename) or (None, "")."""
    if not doc_path:
        return None, ""
    # Extract basename and filename stem (without extension) as file_id
    basename = doc_path.rsplit("/", 1)[-1] if "/" in doc_path else doc_path
    # Remove extension to get file_id (e.g., "7298_Doors_20260407_114028")
    file_id = basename.rsplit(".", 1)[0] if "." in basename else basename
    if not file_id:
        return None, ""
    try:
        r = requests.get(
            f"{API_BASE}/api/documents/{file_id}/download",
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        r.raise_for_status()
        cd = r.headers.get("content-disposition", "")
        fname = cd.split("filename=")[-1].strip('"') if "filename=" in cd else basename
        return r.content, fname
    except Exception:
        return None, ""
