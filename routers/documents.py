"""
routers/documents.py  —  Document download endpoints.

When STORAGE_BACKEND=s3: serves documents via S3 presigned URLs (no local files).
When STORAGE_BACKEND=local: serves from local docs_dir (original behavior).
"""
import asyncio
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from config import get_settings

_FILE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

def _validate_file_id(file_id: str) -> str:
    """Validate file_id — accepts UUIDs, filenames (alphanumeric + underscore + dash)."""
    if not _FILE_ID_PATTERN.match(file_id) or len(file_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid file_id format")
    return file_id

router = APIRouter(prefix="/api/documents", tags=["documents"])
settings = get_settings()

# Lazy S3 imports (only when needed)
_s3_ready = False
def _init_s3():
    global _s3_ready
    if not _s3_ready:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        _s3_ready = True


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _find_s3_key(file_id: str) -> str | None:
    """Search S3 for a document matching the file_id prefix."""
    _init_s3()
    try:
        from s3_utils.operations import list_objects
        prefix = f"{settings.s3_agent_prefix}/generated_documents/"
        objects = list_objects(prefix, max_keys=5000)
        for obj in objects:
            if file_id[:8] in obj["Key"]:
                return obj["Key"]
    except Exception:
        pass
    return None


def _s3_presigned_url(s3_key: str, expiration: int = 3600) -> str | None:
    """Generate a presigned download URL for an S3 object."""
    _init_s3()
    try:
        from s3_utils.operations import generate_presigned_url
        return generate_presigned_url(s3_key, expiration=expiration)
    except Exception:
        return None


def _s3_object_size(s3_key: str) -> int | None:
    """Get the size of an S3 object in bytes."""
    _init_s3()
    try:
        from s3_utils.client import get_s3_client
        from s3_utils.config import get_s3_config
        client = get_s3_client()
        config = get_s3_config()
        resp = client.head_object(Bucket=config.bucket_name, Key=s3_key)
        return resp["ContentLength"]
    except Exception:
        return None


# ── Local helpers ─────────────────────────────────────────────────────────────

def _find_local(file_id: str) -> Path | None:
    """Find a local file matching the file_id.

    Supports both UUID-based names (old chat pipeline) and
    timestamp-based names (scope gap pipeline: 7298_Doors_20260407_114028).
    Searches all supported extensions: .docx, .pdf, .csv, .json
    """
    docs_dir = Path(settings.docs_dir)
    if not docs_dir.exists():
        return None

    # Strategy 1: exact filename match (with any extension)
    for ext in (".docx", ".pdf", ".csv", ".json"):
        exact = docs_dir / f"{file_id}{ext}"
        if exact.exists():
            return exact

    # Strategy 2: UUID prefix match (legacy chat pipeline docs)
    for ext in (".docx", ".pdf", ".csv", ".json"):
        matches = [f for f in docs_dir.glob(f"*{ext}") if file_id[:8] in f.stem]
        if matches:
            return matches[0]

    return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{file_id}/download")
async def download_document(file_id: str):
    """Download a generated Word document."""
    _validate_file_id(file_id)

    # --- S3 MODE: try S3 first, fall through to local ---
    if settings.storage_backend == "s3":
        s3_key = await asyncio.to_thread(_find_s3_key, file_id)
        if s3_key:
            url = await asyncio.to_thread(_s3_presigned_url, s3_key)
            if url:
                from services.audit_logger import log_audit_event
                log_audit_event("document_download", file_id=file_id)
                return RedirectResponse(url=url)
        # S3 lookup failed — fall through to local (scope gap docs saved locally)

    # --- LOCAL FALLBACK ---
    local = _find_local(file_id)
    if local and local.exists():
        from services.audit_logger import log_audit_event
        log_audit_event("document_download", file_id=file_id)
        mime_map = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pdf": "application/pdf",
            ".csv": "text/csv",
            ".json": "application/json",
        }
        mime = mime_map.get(local.suffix.lower(), "application/octet-stream")
        return FileResponse(
            path=str(local),
            media_type=mime,
            filename=local.name,
            headers={"Content-Disposition": f'attachment; filename="{local.name}"'},
        )

    raise HTTPException(status_code=404, detail="Document not found or expired")


@router.get("/{file_id}/info")
async def document_info(file_id: str):
    """Return metadata for a generated document."""
    _validate_file_id(file_id)

    # --- S3 MODE ---
    if settings.storage_backend == "s3":
        s3_key = await asyncio.to_thread(_find_s3_key, file_id)
        if s3_key:
            size = await asyncio.to_thread(_s3_object_size, s3_key)
            return {
                "file_id": file_id,
                "filename": s3_key.split("/")[-1],
                "size_bytes": size,
                "size_kb": round(size / 1024, 1) if size else None,
                "download_url": f"{settings.docs_base_url}/{file_id}/download",
                "storage": "s3",
                "s3_key": s3_key,
            }
        raise HTTPException(status_code=404, detail="Document not found in S3")

    # --- LOCAL MODE ---
    local = _find_local(file_id)
    if local:
        stat = local.stat()
        return {
            "file_id": file_id,
            "filename": local.name,
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 1),
            "download_url": f"{settings.docs_base_url}/{file_id}/download",
            "storage": "local",
        }

    raise HTTPException(status_code=404, detail="Document not found")
