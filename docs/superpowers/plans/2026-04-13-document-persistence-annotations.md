# Document Persistence, Annotations & Document Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SetName level to S3 folder hierarchy, add `text`+`annotations` array to source references, enhance document listing with set filters, and enforce `set_ids` for document generation.

**Architecture:** Four surgical changes to the existing FastAPI pipeline. Source index builder collects all records per drawing into an annotations array. S3 key builder adds a set folder. Document listing parser handles both legacy (3-level) and new (4-level) paths. All changes are additive and backward-compatible.

**Tech Stack:** Python 3.12, FastAPI, python-docx, boto3 (S3), pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-document-persistence-annotations-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `s3_utils/helpers.py` | Modify | Add `set_name`/`set_id` to `generated_document_key()`, new project folder format |
| `services/source_index.py` | Modify | Add `Annotation` dataclass, update `SourceReference` with `text`+`annotations`, rewrite `build()` to group records |
| `services/document_generator.py` | Modify | Pass set params to S3 key builder, add overwrite-before-upload logic, update traceability table |
| `services/exhibit_document_generator.py` | Modify | Same set params + overwrite logic as document_generator |
| `agents/generation_agent.py` | Modify | Validate `set_ids` required when `generate_document=True`, per-set doc generation loop |
| `routers/documents.py` | Modify | `project_id` required, add `set_name` filter, parse 4-level S3 keys, add set metadata to response |
| `models/schemas.py` | Modify | Add `documents` list field to `ChatResponse`, update `source_references` description, add `set_ids` validation |
| `tests/test_document_persistence.py` | Create | All unit tests for new features |

---

## Task 1: Update S3 Key Builder (`s3_utils/helpers.py`)

**Files:**
- Modify: `s3_utils/helpers.py:32-52`
- Test: `tests/test_document_persistence.py` (create)

- [ ] **Step 1: Write failing tests for new key builder**

Create `tests/test_document_persistence.py`:

```python
"""Tests for document persistence features: S3 keys, annotations, listing."""
import pytest


# ── S3 Key Builder Tests ─────────────────────────────────────────────────────

class TestGeneratedDocumentKeyWithSet:
    """Test the updated generated_document_key with set_name/set_id."""

    def test_key_with_set_name_and_id(self):
        from s3_utils.helpers import generated_document_key

        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Granville Hotel",
            project_id=7298,
            set_name="Foundation Plans",
            set_id=4730,
            trade="Electrical",
            filename="scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx",
        )
        assert key == (
            "construction-intelligence-agent/generated_documents/"
            "Granville_Hotel(7298)/Foundation_Plans(4730)/Electrical/"
            "scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx"
        )

    def test_key_without_project_name(self):
        from s3_utils.helpers import generated_document_key

        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name=None,
            project_id=7298,
            set_name="Sheet Set A",
            set_id=100,
            trade="Plumbing",
            filename="scope_plumbing_7298_abcd1234.docx",
        )
        assert key == (
            "construction-intelligence-agent/generated_documents/"
            "Project(7298)/Sheet_Set_A(100)/Plumbing/"
            "scope_plumbing_7298_abcd1234.docx"
        )

    def test_key_sanitizes_special_chars_in_set_name(self):
        from s3_utils.helpers import generated_document_key

        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Test Project",
            project_id=1,
            set_name="HVAC / Mechanical (Phase 2)",
            set_id=99,
            trade="HVAC",
            filename="doc.docx",
        )
        # sanitize_name removes special chars, replaces spaces/slashes with _
        assert "HVAC_Mechanical_Phase_2(99)" in key
        assert "//" not in key

    def test_key_empty_set_name_fallback(self):
        from s3_utils.helpers import generated_document_key

        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Hotel",
            project_id=1,
            set_name="",
            set_id=50,
            trade="Concrete",
            filename="doc.docx",
        )
        # Empty set_name after sanitize -> fallback
        assert "Set(50)" in key or "(50)" in key
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py::TestGeneratedDocumentKeyWithSet -v`

Expected: FAIL — `generated_document_key()` does not accept `set_name`/`set_id` parameters.

- [ ] **Step 3: Update `generated_document_key()` in `s3_utils/helpers.py`**

Replace the existing function at lines 32-52:

```python
def generated_document_key(
    agent_prefix: str,
    project_name: Optional[str],
    project_id: int,
    set_name: str,
    set_id: int,
    trade: str,
    filename: str,
) -> str:
    """
    Build S3 key for a generated document.

    Returns:
        e.g. "construction-intelligence-agent/generated_documents/
              GranvilleHotel(7298)/Foundation_Plans(4730)/Electrical/
              scope_electrical_7298_a1b2c3d4.docx"
    """
    if project_name:
        project_folder = f"{sanitize_name(project_name)}({project_id})"
    else:
        project_folder = f"Project({project_id})"

    sanitized_set = sanitize_name(set_name) if set_name else ""
    set_folder = f"{sanitized_set}({set_id})" if sanitized_set else f"Set({set_id})"

    trade_folder = sanitize_name(trade) if trade else "General"

    return f"{agent_prefix}/generated_documents/{project_folder}/{set_folder}/{trade_folder}/{filename}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py::TestGeneratedDocumentKeyWithSet -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add s3_utils/helpers.py tests/test_document_persistence.py
git commit -m "feat: add set_name/set_id to S3 document key builder"
```

---

## Task 2: Add `Annotation` and Update `SourceReference` (`services/source_index.py`)

**Files:**
- Modify: `services/source_index.py`
- Test: `tests/test_document_persistence.py` (append)

- [ ] **Step 1: Write failing tests for annotations**

Append to `tests/test_document_persistence.py`:

```python
# ── Source Index / Annotations Tests ─────────────────────────────────────────

class TestAnnotationDataclass:
    """Test the Annotation dataclass."""

    def test_annotation_to_dict(self):
        from services.source_index import Annotation

        ann = Annotation(text="Panel EP-1", x=100, y=200, width=50, height=30)
        d = ann.to_dict()
        assert d == {"text": "Panel EP-1", "x": 100, "y": 200, "width": 50, "height": 30}

    def test_annotation_with_null_coords(self):
        from services.source_index import Annotation

        ann = Annotation(text="Some note", x=None, y=None, width=None, height=None)
        d = ann.to_dict()
        assert d["text"] == "Some note"
        assert d["x"] is None


class TestSourceReferenceWithAnnotations:
    """Test SourceReference with text and annotations fields."""

    def test_to_dict_includes_text_and_annotations(self):
        from services.source_index import SourceReference, Annotation

        ref = SourceReference(
            drawing_id=123,
            drawing_name="A-12",
            drawing_title="FLOOR PLAN",
            s3_url="https://example.com/A12.pdf",
            pdf_name="pdfA12",
            x=100, y=200, width=50, height=30,
            text="Panel EP-1",
            annotations=(
                Annotation(text="Panel EP-1", x=100, y=200, width=50, height=30),
                Annotation(text="Conduit run", x=300, y=150, width=40, height=20),
            ),
        )
        d = ref.to_dict()
        assert d["text"] == "Panel EP-1"
        assert len(d["annotations"]) == 2
        assert d["annotations"][0]["text"] == "Panel EP-1"
        assert d["annotations"][1]["text"] == "Conduit run"
        # Backward compat: root-level coords from first annotation
        assert d["x"] == 100
        assert d["y"] == 200

    def test_backward_compat_root_level_fields(self):
        from services.source_index import SourceReference, Annotation

        ref = SourceReference(
            drawing_id=1, drawing_name="B-1", drawing_title="T",
            s3_url="https://x.com/b1.pdf", pdf_name="pdfB1",
            x=10, y=20, width=5, height=3,
            text="First note",
            annotations=(Annotation(text="First note", x=10, y=20, width=5, height=3),),
        )
        d = ref.to_dict()
        # Old consumers read these root-level fields — must still work
        assert "drawing_id" in d
        assert "s3_url" in d
        assert "x" in d
        assert "y" in d
        assert "width" in d
        assert "height" in d


class TestSourceIndexBuilderAnnotations:
    """Test SourceIndexBuilder.build() groups records into annotations."""

    def _make_record(self, drawing_name, text, x=None, y=None, w=None, h=None,
                     s3_path="ifieldsmart/proj/Drawings/pdf", pdf_name="pdfA12",
                     drawing_id=123, drawing_title="FLOOR PLAN"):
        return {
            "drawingName": drawing_name,
            "text": text,
            "x": x, "y": y, "width": w, "height": h,
            "s3BucketPath": s3_path,
            "pdfName": pdf_name,
            "drawingId": drawing_id,
            "drawingTitle": drawing_title,
        }

    def test_single_record_per_drawing(self):
        from services.source_index import SourceIndexBuilder

        builder = SourceIndexBuilder()
        records = [self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30)]
        index, meta = builder.build(records)

        assert "A-12" in index
        ref = index["A-12"]
        assert ref.text == "Panel EP-1"
        assert len(ref.annotations) == 1
        assert ref.annotations[0].text == "Panel EP-1"
        assert ref.x == 100  # backward compat

    def test_multiple_records_same_drawing(self):
        from services.source_index import SourceIndexBuilder

        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30),
            self._make_record("A-12", "Conduit run to MDP", 300, 150, 40, 20),
            self._make_record("A-12", "Junction box JB-3", 500, 100, 25, 15),
        ]
        index, meta = builder.build(records)

        assert "A-12" in index
        ref = index["A-12"]
        assert len(ref.annotations) == 3
        assert ref.annotations[0].text == "Panel EP-1"
        assert ref.annotations[1].text == "Conduit run to MDP"
        assert ref.annotations[2].text == "Junction box JB-3"
        # Root-level = first annotation
        assert ref.text == "Panel EP-1"
        assert ref.x == 100

    def test_records_with_empty_text_excluded_from_annotations(self):
        from services.source_index import SourceIndexBuilder

        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30),
            self._make_record("A-12", "", 300, 150, 40, 20),  # empty text
            self._make_record("A-12", "   ", 400, 100, 25, 15),  # whitespace only
        ]
        index, meta = builder.build(records)

        ref = index["A-12"]
        assert len(ref.annotations) == 1  # only the one with real text

    def test_multiple_drawings(self):
        from services.source_index import SourceIndexBuilder

        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Note 1", 100, 200, 50, 30),
            self._make_record("A-13", "Note 2", 200, 300, 60, 40,
                              pdf_name="pdfA13", drawing_id=456, drawing_title="PANEL SCHEDULE"),
        ]
        index, meta = builder.build(records)

        assert len(index) == 2
        assert index["A-12"].text == "Note 1"
        assert index["A-13"].text == "Note 2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py -k "Annotation or SourceReference or SourceIndexBuilder" -v`

Expected: FAIL — `Annotation` class does not exist, `SourceReference` has no `text`/`annotations`.

- [ ] **Step 3: Rewrite `services/source_index.py`**

Replace the entire file content:

```python
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
    x: int | None              # First annotation's x (backward compat)
    y: int | None              # First annotation's y (backward compat)
    width: int | None          # First annotation's width (backward compat)
    height: int | None         # First annotation's height (backward compat)
    text: str                  # First annotation's text (backward compat)
    annotations: tuple[Annotation, ...]  # All text+coordinate annotations

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

        # Group all records by drawingName
        by_drawing: dict[str, list[dict]] = {}
        for rec in records:
            dn = (rec.get("drawingName") or "").strip()
            if dn:
                by_drawing.setdefault(dn, []).append(rec)

        index: dict[str, SourceReference] = {}
        warnings: list[str] = []

        for dn, group in by_drawing.items():
            # Find first record with valid S3 info
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

            # Build annotations from ALL records in this drawing group
            annotations: list[Annotation] = []
            for rec in group:
                text = (rec.get("text") or "").strip()
                x, y, w, h = self._validate_coordinates(rec)
                if text:
                    annotations.append(Annotation(text=text, x=x, y=y, width=w, height=h))

            # Root-level values from first annotation (backward compat)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py -k "Annotation or SourceReference or SourceIndexBuilder" -v`

Expected: All 9 tests PASS.

- [ ] **Step 5: Run existing source_index tests to verify no regression**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_source_index.py -v`

Expected: Existing tests may need minor updates since `SourceReference` now requires `text` and `annotations` params. Fix any failures by adding those fields to existing test fixtures.

- [ ] **Step 6: Commit**

```bash
git add services/source_index.py tests/test_document_persistence.py
git commit -m "feat: add text and annotations array to SourceReference"
```

---

## Task 3: Update Document Generator — Set Folder + Overwrite (`services/document_generator.py`)

**Files:**
- Modify: `services/document_generator.py:118-156` (S3 upload section)
- Modify: `services/document_generator.py:229-265` (traceability table)

- [ ] **Step 1: Update `generate_sync()` signature — add `set_name` and `set_id`**

In `services/document_generator.py`, update the `generate()` and `generate_sync()` signatures:

```python
    async def generate(
        self,
        content: str,
        project_id: int,
        trade: str,
        document_type: str,
        project_name: str = "",
        title: str = None,
        set_ids: list = None,
        set_names: list = None,
        set_name: str = "",          # NEW
        set_id: int = 0,             # NEW
        source_index: dict = None,
    ) -> GeneratedDocument:
        return await asyncio.to_thread(
            self.generate_sync,
            content=content,
            project_id=project_id,
            trade=trade,
            document_type=document_type,
            project_name=project_name,
            title=title,
            set_ids=set_ids,
            set_names=set_names,
            set_name=set_name,
            set_id=set_id,
            source_index=source_index,
        )

    def generate_sync(
        self,
        content: str,
        project_id: int,
        trade: str,
        document_type: str,
        project_name: str = "",
        title: str = None,
        set_ids: list = None,
        set_names: list = None,
        set_name: str = "",          # NEW
        set_id: int = 0,             # NEW
        source_index: dict = None,
    ) -> GeneratedDocument:
```

- [ ] **Step 2: Update S3 upload section to use new key builder + overwrite**

Replace the S3 MODE block (lines ~118-156) inside `generate_sync()`:

```python
        # --- S3 MODE: save to temp, upload to S3, delete local ---
        if settings.storage_backend == "s3":
            import tempfile
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
            from s3_utils.operations import upload_file, delete_prefix
            from s3_utils.helpers import generated_document_key

            # Save to temp file (python-docx needs a file path)
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            doc.save(str(tmp_path))
            size_bytes = tmp_path.stat().st_size

            s3_key = generated_document_key(
                settings.s3_agent_prefix,
                project_name,
                project_id,
                set_name,
                set_id,
                trade,
                filename,
            )

            # Overwrite: delete existing docs in this Project/Set/Trade folder
            folder_prefix = "/".join(s3_key.split("/")[:-1]) + "/"
            try:
                deleted = delete_prefix(folder_prefix)
                if deleted > 0:
                    logger.info("Overwrite: deleted %d old docs from %s", deleted, folder_prefix)
            except Exception as e:
                logger.warning("Failed to delete old docs at %s: %s", folder_prefix, e)

            upload_ok = upload_file(str(tmp_path), s3_key)
            if upload_ok:
                logger.info(
                    "S3 upload OK: s3://%s/%s (%d bytes) | file_id=%s",
                    settings.s3_bucket_name, s3_key, size_bytes, file_id,
                )
            else:
                logger.error(
                    "S3 upload FAILED: s3://%s/%s | file_id=%s | "
                    "Check AWS credentials, bucket permissions, and network connectivity. "
                    "Verify STORAGE_BACKEND, S3_BUCKET_NAME, AWS_ACCESS_KEY_ID are in os.environ.",
                    settings.s3_bucket_name, s3_key, file_id,
                )

            # Clean up temp file — S3 is the only copy now
            tmp_path.unlink(missing_ok=True)
            download_url = f"{settings.docs_base_url}/{file_id}/download"
            file_path_str = f"s3://{settings.s3_bucket_name}/{s3_key}"
```

- [ ] **Step 3: Update traceability table to show text column**

Replace `_add_traceability_table()`:

```python
    def _add_traceability_table(self, doc, source_index):
        """Append a source reference traceability table to the document."""
        if not source_index:
            return
        doc.add_page_break()
        doc.add_heading("Source Reference Table", level=2)
        table = doc.add_table(rows=1, cols=5)
        try:
            table.style = "Light Grid Accent 1"
        except KeyError:
            table.style = "Table Grid"
        headers = ["Drawing Name", "Drawing Title", "Text", "PDF Link", "Coordinates"]
        for i, h in enumerate(headers):
            table.rows[0].cells[i].text = h
        for ref in sorted(source_index.values(), key=lambda r: r.drawing_name):
            row = table.add_row().cells
            p = row[0].paragraphs[0]
            if ref.s3_url:
                self._add_hyperlink(p, ref.s3_url, ref.drawing_name)
            else:
                p.text = ref.drawing_name
            row[1].text = ref.drawing_title
            # Text column: first annotation text, truncated
            row[2].text = (ref.text[:100] + "...") if len(ref.text) > 100 else ref.text
            p2 = row[3].paragraphs[0]
            if ref.s3_url:
                self._add_hyperlink(p2, ref.s3_url, "View PDF")
            else:
                p2.text = "N/A"
            if ref.x is not None and ref.y is not None:
                size = f" {ref.width}x{ref.height}" if ref.width is not None and ref.height is not None else ""
                row[4].text = f"({ref.x}, {ref.y}){size}"
            else:
                row[4].text = "\u2014"
        hyperlink_count = sum(1 for ref in source_index.values() if ref.s3_url)
        logger.info(
            "Traceability table: %d drawings, %d hyperlinks",
            len(source_index), hyperlink_count,
        )
```

- [ ] **Step 4: Run existing document tests**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_hyperlinks.py -v`

Expected: PASS (or fix any failures due to new params).

- [ ] **Step 5: Commit**

```bash
git add services/document_generator.py
git commit -m "feat: add set folder to S3 path, overwrite on regeneration, text column in traceability"
```

---

## Task 4: Update Exhibit Document Generator (`services/exhibit_document_generator.py`)

**Files:**
- Modify: `services/exhibit_document_generator.py:94-210`

- [ ] **Step 1: Update `generate()` and `generate_sync()` signatures to accept `set_name`/`set_id`**

Add `set_name: str = ""` and `set_id: int = 0` parameters to both methods (same pattern as Task 3 Step 1).

- [ ] **Step 2: Update S3 key builder call**

In the S3 MODE block (lines ~155-189), change:

```python
            s3_key = generated_document_key(
                settings.s3_agent_prefix,
                project_name,
                project_id,
                set_name,      # NEW
                set_id,        # NEW
                trade,
                filename,
            )

            # Overwrite: delete existing docs in this Project/Set/Trade folder
            folder_prefix = "/".join(s3_key.split("/")[:-1]) + "/"
            try:
                from s3_utils.operations import delete_prefix
                deleted = delete_prefix(folder_prefix)
                if deleted > 0:
                    logger.info("Overwrite: deleted %d old exhibit docs from %s", deleted, folder_prefix)
            except Exception as e:
                logger.warning("Failed to delete old exhibit docs at %s: %s", folder_prefix, e)
```

- [ ] **Step 3: Commit**

```bash
git add services/exhibit_document_generator.py
git commit -m "feat: add set folder to exhibit document S3 path"
```

---

## Task 5: Update `ChatResponse` Schema (`models/schemas.py`)

**Files:**
- Modify: `models/schemas.py:157-210`

- [ ] **Step 1: Add `documents` field and update `source_references` description**

In `ChatResponse` class, add a `documents` list field and update the description:

```python
class ChatResponse(BaseModel):
    """Response from POST /api/chat."""
    session_id: str
    project_name: str = ""
    answer: str
    set_ids: Optional[list[Union[int, str]]] = Field(None, description="Set IDs used for filtering (echo of request)")
    set_names: list[str] = Field(default_factory=list, description="Set names extracted from API response")
    document: Optional[GeneratedDocument] = None
    documents: list[GeneratedDocument] = Field(
        default_factory=list,
        description="All generated documents (one per set_id when multiple sets requested)",
    )
    intent: Optional[IntentResult] = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    groundedness_score: float = 0.0
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="3-5 suggested follow-up questions based on the generated scope",
    )
    pipeline_ms: int = 0
    cached: bool = False
    token_log: Optional[dict[str, Any]] = Field(None)
    source_references: dict[str, dict] = Field(
        default_factory=dict,
        description="Map of drawingName -> {drawing_id, s3_url, pdf_name, x, y, width, height, text, annotations[]}",
    )
    api_version: str = Field("", description="API endpoint used")
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Add `set_ids` validation on `ChatRequest`**

Add a model validator to `ChatRequest`:

```python
from pydantic import model_validator

class ChatRequest(BaseModel):
    """Incoming request to POST /api/chat."""
    project_id: int = Field(..., description="MongoDB project ID, e.g. 7276")
    query: str = Field(..., min_length=3, description="User's natural-language question")
    session_id: Optional[str] = Field(None, description="Pass existing session ID to continue conversation")
    user_id: Optional[str] = Field(None, description="Optional user identifier")
    generate_document: bool = Field(True, description="Whether to generate a .docx file")
    set_ids: Optional[list[Union[int, str]]] = Field(
        None,
        description="List of set IDs to filter drawings. Required when generate_document is true.",
    )

    @model_validator(mode="after")
    def validate_set_ids_for_document(self):
        if self.generate_document and not self.set_ids:
            raise ValueError("set_ids is required when generate_document is true")
        return self
```

- [ ] **Step 3: Commit**

```bash
git add models/schemas.py
git commit -m "feat: add documents list, set_ids validation, update source_references description"
```

---

## Task 6: Update Generation Agent — Per-Set Document Generation (`agents/generation_agent.py`)

**Files:**
- Modify: `agents/generation_agent.py` (lines ~329-403)

- [ ] **Step 1: Replace single doc generation with per-set loop**

Find the document generation section (around lines 329-355) and replace:

```python
        # -- Document generation + follow-up questions -- parallel ----------
        # Per-set document generation: one .docx per set_id
        generated_docs: list[GeneratedDocument] = []
        if request.generate_document and set_ids:
            # Map set_id -> set_name from context stats
            set_name_map: dict[str, str] = {}
            for sn in set_names:
                # set_names are like "Foundation Plans" — map via data
                # We need set_id -> set_name mapping from raw records
                pass
            # Build set_id -> set_name from raw records
            for rec in raw_records:
                sid = rec.get("setId") or rec.get("set_id")
                sname = (rec.get("setName") or rec.get("set_name") or "").strip()
                if sid is not None and sname:
                    set_name_map[str(sid)] = sname

            async def _gen_doc_for_set(sid):
                sname = set_name_map.get(str(sid), f"Set_{sid}")
                return await asyncio.to_thread(
                    self._docgen.generate_sync,
                    content=answer,
                    project_id=request.project_id,
                    project_name=project_display_name,
                    trade=intent.trade or "General",
                    document_type=intent.document_type,
                    set_ids=[sid],
                    set_names=[sname],
                    set_name=sname,
                    set_id=int(sid),
                    source_index=source_index if source_index else None,
                )

            doc_coros = [_gen_doc_for_set(sid) for sid in set_ids]
            followup_coro = self._generate_follow_up_questions(
                answer=answer,
                query=request.query,
                trade=intent.trade or "General",
                document_type=intent.document_type,
            )

            results = await asyncio.gather(*doc_coros, followup_coro, return_exceptions=True)
            follow_up_questions = results[-1] if not isinstance(results[-1], BaseException) else []
            if isinstance(follow_up_questions, BaseException):
                logger.warning("Follow-up question generation failed: %s", follow_up_questions)
                follow_up_questions = []

            for r in results[:-1]:
                if isinstance(r, BaseException):
                    logger.error("Document generation failed for a set: %s", r)
                else:
                    generated_docs.append(r)
        else:
            # No document generation — just follow-up questions
            followup_coro = self._generate_follow_up_questions(
                answer=answer,
                query=request.query,
                trade=intent.trade or "General",
                document_type=intent.document_type,
            )
            follow_up_questions = await followup_coro
            if isinstance(follow_up_questions, BaseException):
                logger.warning("Follow-up question generation failed: %s", follow_up_questions)
                follow_up_questions = []

        # Backward compat: first doc as singular `document`
        generated_doc = generated_docs[0] if generated_docs else None
```

- [ ] **Step 2: Update `ChatResponse` construction to include `documents` list**

In the response construction (around line 382), add the `documents` field:

```python
        response = ChatResponse(
            session_id=session.session_id,
            project_name=project_display_name,
            answer=answer,
            set_ids=set_ids,
            set_names=set_names,
            document=generated_doc,
            documents=generated_docs,        # NEW
            intent=intent,
            token_usage=usage,
            groundedness_score=guard_result.confidence_score,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions,
            follow_up_questions=follow_up_questions,
            pipeline_ms=pipeline_ms,
            cached=False,
            token_log=token_log_summary,
            source_references={
                name: ref.to_dict() for name, ref in source_index.items()
            } if source_index else {},
            api_version=api_metadata.get("endpoint_used", ""),
            warnings=warnings,
        )
```

- [ ] **Step 3: Apply same pattern to `process_stream()` method**

Find the streaming doc generation section and apply the same per-set loop pattern.

- [ ] **Step 4: Commit**

```bash
git add agents/generation_agent.py
git commit -m "feat: per-set document generation, set_ids validation, documents list in response"
```

---

## Task 7: Update Document Listing Router (`routers/documents.py`)

**Files:**
- Modify: `routers/documents.py:108-204`

- [ ] **Step 1: Write failing tests for document listing**

Append to `tests/test_document_persistence.py`:

```python
# ── Document Listing Tests ───────────────────────────────────────────────────

class TestDocumentListParsing:
    """Test S3 key parsing for new 4-level folder structure."""

    def test_parse_new_4_level_key(self):
        """Verify extraction of project_id, set_name, set_id, trade from new key format."""
        import re
        key_suffix = "GranvilleHotel(7298)/Foundation_Plans(4730)/Electrical/scope.docx"
        parts = key_suffix.split("/")
        assert len(parts) == 4

        project_folder = parts[0]
        set_folder = parts[1]
        trade_folder = parts[2]
        filename = parts[3]

        pid_match = re.search(r'\((\d+)\)$', project_folder)
        assert pid_match and int(pid_match.group(1)) == 7298

        sid_match = re.search(r'\((\d+)\)$', set_folder)
        assert sid_match and int(sid_match.group(1)) == 4730

        set_name = re.sub(r'\(\d+\)$', '', set_folder).replace('_', ' ').strip()
        assert set_name == "Foundation Plans"
        assert trade_folder == "Electrical"

    def test_parse_legacy_3_level_key(self):
        """Legacy docs with 3 parts should get set_name='Unknown', set_id=0."""
        key_suffix = "GranvilleHotel_7298/Electrical/scope.docx"
        parts = key_suffix.split("/")
        assert len(parts) == 3
        # Legacy path: no set info available
```

- [ ] **Step 2: Run tests to verify they pass (these are parsing logic tests, not endpoint tests)**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py::TestDocumentListParsing -v`

Expected: PASS (pure parsing logic, no imports needed).

- [ ] **Step 3: Update `list_documents()` in `routers/documents.py`**

Replace the endpoint (lines 108-204):

```python
@router.get("/list")
async def list_documents(
    project_id: int = ...,    # NOW REQUIRED
    set_name: str = None,     # NEW FILTER
    trade: str = None,
):
    """
    List generated documents for a project. Optionally filter by set_name and/or trade.
    Supports both new 4-level (Project/Set/Trade/file) and legacy 3-level (Project/Trade/file) S3 paths.
    """
    if settings.storage_backend != "s3":
        # Local mode: scan docs_dir (unchanged)
        docs_dir = Path(settings.docs_dir)
        if not docs_dir.exists():
            return {"success": True, "data": {"documents": [], "total": 0}}

        documents = []
        for f in sorted(docs_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = f.stat()
            file_id = f.stem.rsplit("_", 1)[-1] if "_" in f.stem else f.stem
            documents.append({
                "file_id": file_id,
                "filename": f.name,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 1),
                "download_url": f"{settings.docs_base_url}/{file_id}/download",
                "created_at": stat.st_mtime,
                "storage": "local",
                "set_name": "Unknown",
                "set_id": 0,
            })
        return {"success": True, "data": {"documents": documents, "total": len(documents)}}

    # S3 mode: scan generated_documents/ prefix
    _init_s3()
    try:
        from s3_utils.operations import list_objects

        prefix = f"{settings.s3_agent_prefix}/generated_documents/"
        objects = await asyncio.to_thread(list_objects, prefix, 5000)

        documents = []
        for obj in objects:
            key = obj["Key"]
            if not key.endswith((".docx", ".pdf", ".csv", ".json")):
                continue

            parts = key.replace(prefix, "").split("/")

            # --- New 4-level structure: Project(ID)/Set(ID)/Trade/filename ---
            if len(parts) >= 4:
                project_folder = parts[0]
                set_folder = parts[1]
                trade_folder = parts[2]
                filename = parts[3]

                pid_match = re.search(r'\((\d+)\)$', project_folder)
                doc_project_id = int(pid_match.group(1)) if pid_match else 0

                sid_match = re.search(r'\((\d+)\)$', set_folder)
                doc_set_id = int(sid_match.group(1)) if sid_match else 0
                doc_set_name = re.sub(r'\(\d+\)$', '', set_folder).replace('_', ' ').strip()

            # --- Legacy 3-level structure: Project_ID/Trade/filename ---
            elif len(parts) == 3:
                project_folder = parts[0]
                set_folder = ""
                trade_folder = parts[1]
                filename = parts[2]

                folder_parts = project_folder.rsplit("_", 1)
                try:
                    doc_project_id = int(folder_parts[-1])
                except (ValueError, IndexError):
                    doc_project_id = 0
                doc_set_id = 0
                doc_set_name = "Unknown"
            else:
                continue

            # Apply filters
            if doc_project_id != project_id:
                continue
            if trade and trade.lower() != trade_folder.lower():
                continue
            if set_name and set_name.lower() not in doc_set_name.lower():
                continue

            stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            file_id_part = stem.rsplit("_", 1)[-1] if "_" in stem else stem

            documents.append({
                "file_id": file_id_part,
                "filename": filename,
                "s3_key": key,
                "project_folder": project_folder,
                "project_id": doc_project_id,
                "set_name": doc_set_name,
                "set_id": doc_set_id,
                "trade": trade_folder,
                "size_bytes": obj.get("Size", 0),
                "size_kb": round(obj.get("Size", 0) / 1024, 1),
                "download_url": f"{settings.docs_base_url}/{file_id_part}/download",
                "created_at": obj.get("LastModified", ""),
                "storage": "s3",
            })

        documents.sort(key=lambda d: str(d.get("created_at", "")), reverse=True)
        return {"success": True, "data": {"documents": documents, "total": len(documents)}}

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to list S3 documents: %s", e)
        return {"success": False, "error": str(e), "data": {"documents": [], "total": 0}}
```

- [ ] **Step 4: Commit**

```bash
git add routers/documents.py tests/test_document_persistence.py
git commit -m "feat: add set_name filter, 4-level S3 parsing, project_id required in document listing"
```

---

## Task 8: Run Full Test Suite and Fix Regressions

**Files:**
- All modified files
- All existing test files

- [ ] **Step 1: Run all new tests**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/test_document_persistence.py -v`

Expected: All tests PASS.

- [ ] **Step 2: Run existing test suite to catch regressions**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -m pytest tests/ -v --tb=short 2>&1 | head -100`

Expected: Fix any failures caused by:
- `SourceReference` constructor now requires `text` and `annotations` params
- `generated_document_key()` now requires `set_name` and `set_id` params
- `ChatRequest` now rejects `generate_document=True` without `set_ids`

For each failure: update the test fixture to include the new required fields.

- [ ] **Step 3: Commit all regression fixes**

```bash
git add -A
git commit -m "fix: update existing tests for new SourceReference and S3 key signatures"
```

---

## Task 9: Integration Test — Live API Verification

**Files:**
- Test: manual curl commands against running server

- [ ] **Step 1: Start the server locally**

Run: `cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python main.py`

- [ ] **Step 2: Test health endpoint**

Run: `curl -s http://localhost:8003/health | python -m json.tool`

Expected: `{"status": "ok", ...}`

- [ ] **Step 3: Test document generation with set_ids**

Run:
```bash
curl -s -X POST http://localhost:8003/api/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "query": "generate concrete scope", "set_ids": [4730], "generate_document": true}' \
  | python -m json.tool > test_output.json
```

Verify in `test_output.json`:
- `source_references` contains `text` and `annotations` fields
- `document` has valid `download_url`
- `documents` array has one entry

- [ ] **Step 4: Test document listing**

Run: `curl -s "http://localhost:8003/api/documents/list?project_id=7276" | python -m json.tool`

Verify: Response includes `set_name` and `set_id` in each document.

- [ ] **Step 5: Test set_ids validation (should fail without set_ids)**

Run:
```bash
curl -s -X POST http://localhost:8003/api/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "query": "generate concrete scope", "generate_document": true}' \
  | python -m json.tool
```

Expected: HTTP 422 — `"set_ids is required when generate_document is true"`

- [ ] **Step 6: Save test results**

Save the generated `.docx` locally and save the JSON response with timing:

```bash
# Save JSON response with metadata
python -c "
import json, time
with open('test_output.json') as f:
    data = json.load(f)
result = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
    'response_time_ms': data.get('pipeline_ms', 0),
    'total_tokens': data.get('token_usage', {}).get('total_tokens', 0),
    'token_log': data.get('token_log', {}),
    'document': data.get('document'),
    'documents': data.get('documents', []),
    'source_references_count': len(data.get('source_references', {})),
}
with open('test_results.json', 'w') as f:
    json.dump(result, f, indent=2)
print('Saved test_results.json')
"
```

- [ ] **Step 7: Commit test results**

```bash
git add test_output.json test_results.json
git commit -m "test: save integration test results with response times and tokens"
```

---

## Task 10: Deploy to Sandbox VM (54.197.189.113)

**Files:**
- All modified files synced to sandbox

- [ ] **Step 1: Sync code to sandbox**

```bash
scp -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" \
  -r "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/" \
  ubuntu@54.197.189.113:/home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent/
```

- [ ] **Step 2: SSH and restart service**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant_sandbox.pem" ubuntu@54.197.189.113
cd /home/ubuntu/chatbot/aniruddha/vcsai/construction-intelligence-agent
pip install -r requirements.txt
# Restart the agent (check if systemd or screen/tmux)
sudo systemctl restart construction-agent || python main.py &
```

- [ ] **Step 3: Verify sandbox health**

```bash
curl -s http://54.197.189.113:8003/health | python -m json.tool
```

- [ ] **Step 4: Run integration test against sandbox**

```bash
curl -s -X POST http://54.197.189.113:8003/api/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "query": "generate concrete scope", "set_ids": [4730], "generate_document": true}' \
  | python -m json.tool
```

- [ ] **Step 5: Verify document listing on sandbox**

```bash
curl -s "http://54.197.189.113:8003/api/documents/list?project_id=7276" | python -m json.tool
```

---

## Task 11: Deploy to Production VM (13.217.22.125)

- [ ] **Step 1: Sync code to production**

```bash
scp -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" \
  -r "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent/" \
  ubuntu@13.217.22.125:/home/ubuntu/vcsai/construction-intelligence-agent/
```

- [ ] **Step 2: SSH and restart service**

```bash
ssh -i "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/ai_assistant.pem" ubuntu@13.217.22.125
cd /home/ubuntu/vcsai/construction-intelligence-agent
pip install -r requirements.txt
sudo systemctl restart construction-agent
```

- [ ] **Step 3: Verify production health**

```bash
curl -s https://ai5.ifieldsmart.com/construction/health | python -m json.tool
```

- [ ] **Step 4: Run smoke test**

```bash
curl -s -X POST https://ai5.ifieldsmart.com/construction/api/chat \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "query": "generate concrete scope", "set_ids": [4730], "generate_document": true}' \
  | python -m json.tool
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `docs/PRODUCTION_API_REFERENCE.md`
- Create: `docs/SANDBOX_API_REFERENCE.md`

- [ ] **Step 1: Update PRODUCTION_API_REFERENCE.md**

Add/update these sections:
- `source_references` schema now includes `text` and `annotations[]`
- `ChatRequest.set_ids` is required when `generate_document=true`
- `ChatResponse.documents` list field
- `GET /api/documents/list` now requires `project_id`, accepts `set_name` filter
- Document response includes `set_name` and `set_id`
- New S3 folder structure: `Project(ID)/Set(ID)/Trade/filename`

- [ ] **Step 2: Create SANDBOX_API_REFERENCE.md**

Copy production reference with sandbox-specific details:
- Base URL: `http://54.197.189.113:8003`
- Same endpoints, same schema
- Same S3 bucket (`agentic-ai-production`)

- [ ] **Step 3: Commit docs**

```bash
git add docs/PRODUCTION_API_REFERENCE.md docs/SANDBOX_API_REFERENCE.md
git commit -m "docs: update API reference with new source_references schema and document listing"
```

---

## Task 13: Update Excel Attendance Sheet

**Files:**
- Modify: `C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/Attendance_sheets/Attendance_Aniruddha.xlsx`

- [ ] **Step 1: Read existing sheet format**

Read the `Xtra-work-april` sheet to understand column structure.

- [ ] **Step 2: Append rows for new work**

Using openpyxl, append rows matching the existing format with:
- Date: 2026-04-13
- Tasks: S3 folder restructuring with SetName, source reference annotations with text, document listing enhancement with set filter
- Status: Completed

- [ ] **Step 3: Save and verify**

Open the file and verify the new rows appear correctly.

---

## Task 14: Push to GitHub

- [ ] **Step 1: Stage all changes**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
git add -A
git status
```

- [ ] **Step 2: Create final commit if needed**

```bash
git commit -m "feat: document persistence, annotations, set-based folder structure

- S3 path: Project(ID)/Set(ID)/Trade/filename
- source_references: text + annotations[] array (backward-compatible)
- set_ids required for document generation
- Document listing: project_id required, set_name filter
- Overwrite on regeneration (same Project/Set/Trade)
- Per-set document generation for multiple set_ids
- 10+ unit tests, integration tests with saved results"
```

- [ ] **Step 3: Push to remote**

```bash
git push origin main
```
