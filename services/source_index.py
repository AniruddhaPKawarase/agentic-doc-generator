"""
services/source_index.py -- Builds source reference index from API records.

Extracts drawingId, s3BucketPath, pdfName, coordinates, and text from raw API records.
Groups multiple records per drawing into an annotations array.
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
class Annotation:
    """Single text annotation with coordinates on a drawing."""
    text: str
    x: int | None
    y: int | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Immutable source reference for a single drawing with all annotations."""
    drawing_id: int
    drawing_name: str
    drawing_title: str
    s3_url: str
    pdf_name: str
    x: int | None
    y: int | None
    width: int | None
    height: int | None
    text: str
    annotations: tuple[Annotation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "drawing_id": self.drawing_id,
            "drawing_name": self.drawing_name,
            "drawing_title": self.drawing_title,
            "s3_url": self.s3_url,
            "pdf_name": self.pdf_name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "annotations": [a.to_dict() for a in self.annotations],
        }


class SourceIndexBuilder:
    """Builds a source index from API records, grouping by drawing."""

    def build(self, records: list[dict]) -> tuple[dict[str, SourceReference], dict[str, Any]]:
        start = time.perf_counter()

        by_drawing: dict[str, list[dict]] = {}
        for rec in records:
            dn = (rec.get("drawingName") or "").strip()
            if dn:
                by_drawing.setdefault(dn, []).append(rec)

        index: dict[str, SourceReference] = {}
        warnings: list[str] = []

        for dn, group in by_drawing.items():
            s3_url = ""
            pdf_name = ""
            drawing_id = 0
            drawing_title = ""

            for rec in group:
                s3_path_raw = rec.get("s3BucketPath", "")
                pn = rec.get("pdfName", "")
                if s3_path_raw and pn:
                    s3_path = self._sanitize_s3_path(s3_path_raw)
                    safe_pdf = self._sanitize_pdf_name(pn)
                    if s3_path and safe_pdf:
                        s3_url = self._build_s3_url(s3_path, safe_pdf)
                        pdf_name = pn
                        drawing_id = self._safe_drawing_id(rec.get("drawingId"))
                        drawing_title = rec.get("drawingTitle", "")
                        break

            if not s3_url:
                warnings.append(dn)
                continue

            annotations: list[Annotation] = []
            for rec in group:
                text = (rec.get("text") or "").strip()
                x, y, w, h = self._validate_coordinates(rec)
                if text:
                    annotations.append(Annotation(text=text, x=x, y=y, width=w, height=h))

            if annotations:
                first = annotations[0]
            else:
                first = Annotation(text="", x=None, y=None, width=None, height=None)

            index[dn] = SourceReference(
                drawing_id=drawing_id,
                drawing_name=dn,
                drawing_title=drawing_title,
                s3_url=s3_url,
                pdf_name=pdf_name,
                x=first.x,
                y=first.y,
                width=first.width,
                height=first.height,
                text=first.text,
                annotations=tuple(annotations),
            )

        build_ms = int((time.perf_counter() - start) * 1000)
        if warnings:
            logger.warning("Missing source fields for %d drawings: %s", len(warnings), warnings[:10])

        metadata = {
            "drawings_total": len(index),
            "drawings_missing": len(warnings),
            "build_ms": build_ms,
        }
        return index, metadata

    @staticmethod
    def _safe_drawing_id(val: Any) -> int:
        if val is None:
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def _sanitize_s3_path(self, raw_path: str) -> str | None:
        if not raw_path or ".." in raw_path or "\x00" in raw_path:
            return None
        if not any(raw_path.startswith(p) for p in _ALLOWED_S3_PREFIXES):
            return None
        return quote(raw_path, safe="/")

    @staticmethod
    def _sanitize_pdf_name(name: str) -> str | None:
        if not name or ".." in name or "\x00" in name or "/" in name or "\\" in name:
            return None
        return quote(name, safe="")

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
