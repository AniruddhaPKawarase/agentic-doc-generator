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

@router.get("/list")
async def list_documents(
    project_id: int = None,
    trade: str = None,
):
    """
    List all generated documents. Optionally filter by project_id and/or trade.
    Scans S3 generated_documents/ prefix.
    Returns list of documents with metadata.
    """
    if settings.storage_backend != "s3":
        # Local mode: scan docs_dir
        docs_dir = Path(settings.docs_dir)
        if not docs_dir.exists():
            return {"success": True, "data": {"documents": [], "total": 0}}

        documents = []
        for f in sorted(docs_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = f.stat()
            # Extract file_id from filename (last 8 chars before .docx)
            file_id = f.stem.rsplit("_", 1)[-1] if "_" in f.stem else f.stem
            documents.append({
                "file_id": file_id,
                "filename": f.name,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "download_url": f"{settings.docs_base_url}/{file_id}/download",
                "created_at": stat.st_mtime,
                "storage": "local",
            })
        return {"success": True, "data": {"documents": documents, "total": len(documents)}}

    # S3 mode: scan generated_documents/ prefix
    _init_s3()
    try:
        from s3_utils.operations import list_objects

        # Build prefix based on filters
        prefix = f"{settings.s3_agent_prefix}/generated_documents/"
        objects = await asyncio.to_thread(list_objects, prefix, 5000)

        documents = []
        for obj in objects:
            key = obj["Key"]
            # Skip non-document files
            if not key.endswith((".docx", ".pdf", ".csv", ".json")):
                continue

            # Parse S3 key: {prefix}/generated_documents/{ProjectName}_{ProjectID}/{Trade}/{filename}
            parts = key.replace(prefix, "").split("/")
            if len(parts) < 3:
                continue

            project_folder = parts[0]  # e.g. "SINGH_RESIDENCE_ID_7276_7276"
            trade_folder = parts[1]     # e.g. "Concrete"
            filename = parts[2]

            # Extract project_id from folder name (last numeric segment)
            folder_parts = project_folder.rsplit("_", 1)
            try:
                doc_project_id = int(folder_parts[-1])
            except (ValueError, IndexError):
                doc_project_id = 0

            # Apply filters
            if project_id and doc_project_id != project_id:
                continue
            if trade and trade.lower() != trade_folder.lower():
                continue

            # Extract file_id from filename
            stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            file_id_part = stem.rsplit("_", 1)[-1] if "_" in stem else stem

            documents.append({
                "file_id": file_id_part,
                "filename": filename,
                "s3_key": key,
                "project_folder": project_folder,
                "project_id": doc_project_id,
                "trade": trade_folder,
                "size_bytes": obj.get("Size", 0),
                "size_kb": round(obj.get("Size", 0) / 1024, 1),
                "download_url": f"{settings.docs_base_url}/{file_id_part}/download",
                "created_at": obj.get("LastModified", ""),
                "storage": "s3",
            })

        # Sort by created_at descending (newest first)
        documents.sort(key=lambda d: str(d.get("created_at", "")), reverse=True)

        return {"success": True, "data": {"documents": documents, "total": len(documents)}}

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to list S3 documents: %s", e)
        return {"success": False, "error": str(e), "data": {"documents": [], "total": 0}}


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
