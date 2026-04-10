"""
services/source_index.py -- Builds source reference index from API records.

Extracts drawingId, s3BucketPath, pdfName, coordinates from raw API records.
Used by document generators for hyperlinks and traceability tables.
"""

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_ALLOWED_S3_PREFIXES = ("ifieldsmart/", "agentic-ai-production/")


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Immutable source reference for a single drawing."""
    drawing_id: int
    drawing_name: str
    drawing_title: str
    s3_url: str
    pdf_name: str
    x: int | None
    y: int | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceIndexBuilder:
    """Builds a source index from deduplicated API records."""

    def build(self, records: list[dict]) -> tuple[dict[str, SourceReference], dict[str, Any]]:
        start = time.perf_counter()
        index: dict[str, SourceReference] = {}
        warnings: list[str] = []
        seen: set[str] = set()

        for rec in records:
            dn = (rec.get("drawingName") or "").strip()
            if not dn or dn in seen:
                continue
            seen.add(dn)

            s3_path_raw = rec.get("s3BucketPath", "")
            pdf_name = rec.get("pdfName", "")

            if not s3_path_raw or not pdf_name:
                warnings.append(dn)
                continue

            s3_path = self._sanitize_s3_path(s3_path_raw)
            if not s3_path:
                logger.warning("Invalid S3 path for drawing %s: %s", dn, s3_path_raw)
                warnings.append(dn)
                continue

            x, y, w, h = self._validate_coordinates(rec)
            index[dn] = SourceReference(
                drawing_id=int(rec.get("drawingId", 0) or 0),
                drawing_name=dn,
                drawing_title=rec.get("drawingTitle", ""),
                s3_url=self._build_s3_url(s3_path, pdf_name),
                pdf_name=pdf_name,
                x=x, y=y, width=w, height=h,
            )

        pre_recovery = len(index)
        index = self._recover_missing_sources(records, index)
        recovered = len(index) - pre_recovery

        build_ms = int((time.perf_counter() - start) * 1000)
        if warnings:
            logger.warning("Missing source fields for %d drawings: %s", len(warnings), warnings[:10])

        metadata = {
            "drawings_total": len(index),
            "drawings_missing": max(0, len(warnings) - recovered),
            "recovery_count": recovered,
            "build_ms": build_ms,
        }
        return index, metadata

    def _sanitize_s3_path(self, raw_path: str) -> str | None:
        if not raw_path or ".." in raw_path:
            return None
        if not any(raw_path.startswith(p) for p in _ALLOWED_S3_PREFIXES):
            return None
        return quote(raw_path, safe="/")

    def _build_s3_url(self, s3_path: str, pdf_name: str) -> str:
        pattern = settings.s3_pdf_url_pattern
        return pattern.format(bucket=settings.s3_bucket_name, path=s3_path, name=pdf_name)

    def _validate_coordinates(self, record: dict) -> tuple[int | None, int | None, int | None, int | None]:
        def _safe_int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                v = int(val)
                return v if v >= 0 else None
            except (ValueError, TypeError):
                return None
        return (
            _safe_int(record.get("x")),
            _safe_int(record.get("y")),
            _safe_int(record.get("width")),
            _safe_int(record.get("height")),
        )

    def _recover_missing_sources(self, records: list[dict], index: dict[str, SourceReference]) -> dict[str, SourceReference]:
        by_drawing: dict[str, list[dict]] = {}
        for rec in records:
            dn = (rec.get("drawingName") or "").strip()
            if dn:
                by_drawing.setdefault(dn, []).append(rec)

        recovered: dict[str, SourceReference] = {}
        for dn, group in by_drawing.items():
            if dn in index:
                continue
            for rec in group:
                s3_path = rec.get("s3BucketPath", "")
                pdf_name = rec.get("pdfName", "")
                if s3_path and pdf_name:
                    sanitized = self._sanitize_s3_path(s3_path)
                    if sanitized:
                        x, y, w, h = self._validate_coordinates(rec)
                        recovered[dn] = SourceReference(
                            drawing_id=int(rec.get("drawingId", 0) or 0),
                            drawing_name=dn,
                            drawing_title=rec.get("drawingTitle", ""),
                            s3_url=self._build_s3_url(sanitized, pdf_name),
                            pdf_name=pdf_name,
                            x=x, y=y, width=w, height=h,
                        )
                        break
        return {**index, **recovered}
