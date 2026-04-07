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

_FILE_ID_PATTERN = re.compile(r'^[a-f0-9-]+$')

def _validate_file_id(file_id: str) -> str:
    if not _FILE_ID_PATTERN.match(file_id):
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
    """Find a local file matching the UUID prefix."""
    docs_dir = Path(settings.docs_dir)
    if not docs_dir.exists():
        return None
    matches = list(docs_dir.glob(f"*_{file_id[:8]}.docx"))
    if not matches:
        matches = [f for f in docs_dir.glob("*.docx") if file_id[:8] in f.name]
    return matches[0] if matches else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{file_id}/download")
async def download_document(file_id: str):
    """Download a generated Word document."""
    _validate_file_id(file_id)

    # --- S3 MODE: presigned URL redirect ---
    if settings.storage_backend == "s3":
        s3_key = await asyncio.to_thread(_find_s3_key, file_id)
        if s3_key:
            url = await asyncio.to_thread(_s3_presigned_url, s3_key)
            if url:
                from services.audit_logger import log_audit_event
                log_audit_event("document_download", file_id=file_id)
                return RedirectResponse(url=url)
        raise HTTPException(status_code=404, detail="Document not found in S3")

    # --- LOCAL MODE ---
    local = _find_local(file_id)
    if local and local.exists():
        from services.audit_logger import log_audit_event
        log_audit_event("document_download", file_id=file_id)
        return FileResponse(
            path=str(local),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
