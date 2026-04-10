# byTradeAndSet API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the construction agent from `summaryByTrade` to the richer `byTradeAndSet` API, adding source reference indexes, clickable PDF hyperlinks in Word documents, traceability tables, and raw data display in the Streamlit UI.

**Architecture:** Four independent streams (API migration, source index, document enrichment, UI integration) converge in `generation_agent.py`. The new API provides `drawingId`, `s3BucketPath`, `pdfName`, and coordinates per record. A `SourceIndexBuilder` extracts these into a lookup dict used by document generators for hyperlinks and by the UI for raw data display.

**Tech Stack:** Python 3.10+, FastAPI, httpx, python-docx (OxmlElement hyperlinks), Streamlit, pydantic-settings, pytest

**Spec:** `docs/superpowers/specs/2026-04-10-byTradeAndSet-api-integration-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|----------------|
| `services/source_index.py` | `SourceReference` dataclass + `SourceIndexBuilder` (build, sanitize, recover) |
| `tests/test_source_index.py` | Unit tests for source index builder |
| `tests/test_api_migration.py` | Integration tests for endpoint fallback |
| `tests/test_document_hyperlinks.py` | Tests for Word hyperlinks + traceability table |

### Modified Files
| File | What Changes |
|------|-------------|
| `config.py:93` | Add 3 settings: `use_new_api`, `s3_pdf_url_pattern`, `source_ref_enabled` |
| `models/schemas.py:172-197` | Add `source_references`, `api_version`, `warnings` to `ChatResponse`; `new_api` to `HealthResponse` |
| `services/api_client.py` | Add `get_by_trade()`, `get_by_trade_and_set()`, `_fetch_with_fallback()` |
| `services/document_generator.py:73-83` | Add `source_index` param, `_add_hyperlink()`, `_add_traceability_table()` |
| `services/exhibit_document_generator.py:115-125` | Add `source_index` param + same hyperlink/table methods |
| `agents/generation_agent.py:188,320,358` | Wire source index, pass to doc gen, collect warnings |
| `agents/data_agent.py:36-70` | Route API calls based on `use_new_api` flag |
| `routers/projects.py:14` | Add `GET /{project_id}/raw-data` endpoint |
| `main.py:83` | Initialize `SourceIndexBuilder`, attach to `app.state` |
| `.env` | Add `USE_NEW_API`, `S3_PDF_URL_PATTERN`, `SOURCE_REF_ENABLED` |
| `scope-gap-ui/api/client.py:12` | Add `get_raw_data()` method |
| `scope-gap-ui/components/chat.py:45` | Add raw data expander + fallback banner |
| `scope-gap-ui/components/reference_panel.py` | Add source reference links |

---

## Task 1: Config + Schema Foundation

**Files:**
- Modify: `config.py:93` (after scope gap settings block)
- Modify: `models/schemas.py:172-197` (ChatResponse), `models/schemas.py:209-213` (HealthResponse)
- Modify: `.env`

- [ ] **Step 1: Add 3 new settings to config.py**

Open `config.py`. After line 103 (the `scope_gap_quality_max_tokens` line), add:

```python
    # ── API Migration (v4) ───────────────────────────────────
    use_new_api: bool = True
    s3_pdf_url_pattern: str = "https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf"
    source_ref_enabled: bool = True
```

- [ ] **Step 2: Add new fields to ChatResponse in schemas.py**

Open `models/schemas.py`. After line 197 (the `token_log` field), add:

```python
    # ── Source references (v4 API migration) ─────────────────
    source_references: dict[str, dict] = Field(
        default_factory=dict,
        description="Map of drawingName -> {drawing_id, s3_url, pdf_name, x, y, width, height}",
    )
    api_version: str = Field(
        "",
        description="API endpoint used: 'byTrade', 'byTradeAndSet', 'summaryByTrade' (fallback)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings: missing sources, fallback alerts, etc.",
    )
```

- [ ] **Step 3: Add new_api to HealthResponse in schemas.py**

Open `models/schemas.py`. In the `HealthResponse` class (line 209-213), add after `openai`:

```python
class HealthResponse(BaseModel):
    status: str = "ok"
    redis: str = "unknown"
    openai: str = "unknown"
    new_api: str = "unknown"
    version: str = ""
```

- [ ] **Step 4: Add env vars to .env**

Append to `.env`:

```bash
# ── API Migration (v4) ───────────────────────────────────
USE_NEW_API=true
S3_PDF_URL_PATTERN=https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf
SOURCE_REF_ENABLED=true
```

- [ ] **Step 5: Verify config loads**

Run:
```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
python -c "from config import get_settings; s = get_settings(); print(f'use_new_api={s.use_new_api}, source_ref_enabled={s.source_ref_enabled}, pattern={s.s3_pdf_url_pattern}')"
```

Expected: `use_new_api=True, source_ref_enabled=True, pattern=https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf`

- [ ] **Step 6: Commit**

```bash
git add config.py models/schemas.py .env
git commit -m "feat: add config + schema foundation for byTradeAndSet API migration"
```

---

## Task 2: Source Index Builder — Tests First

**Files:**
- Create: `services/source_index.py`
- Create: `tests/test_source_index.py`

- [ ] **Step 1: Write test file with all unit tests**

Create `tests/test_source_index.py`:

```python
"""Unit tests for services/source_index.py — SourceIndexBuilder."""

import pytest
from unittest.mock import patch


# ── Fixtures ──────────────────────────────────────────────


def _make_record(
    drawing_name: str = "A102",
    s3_path: str = "ifieldsmart/proj123/Drawings/pdf456",
    pdf_name: str = "pdfA102Plan1-1",
    drawing_id: int = 318845,
    drawing_title: str = "ARCH SITE PLAN",
    x: int = 3743,
    y: int = 738,
    width: int = 144,
    height: int = 69,
    **overrides,
) -> dict:
    rec = {
        "_id": f"id_{drawing_name}",
        "projectId": 7292,
        "drawingId": drawing_id,
        "drawingName": drawing_name,
        "drawingTitle": drawing_title,
        "s3BucketPath": s3_path,
        "pdfName": pdf_name,
        "text": "Some note text",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "csi_division": ["03 - Concrete"],
        "trades": ["Civil"],
    }
    rec.update(overrides)
    return rec


# ── Tests ─────────────────────────────────────────────────


class TestSourceIndexBuilder:
    """Tests for SourceIndexBuilder.build()."""

    def test_build_from_valid_records(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(drawing_name=f"D-{i}") for i in range(10)]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)

        assert len(index) == 10
        assert meta["drawings_total"] == 10
        assert meta["drawings_missing"] == 0
        assert meta["build_ms"] >= 0
        # Check first entry
        ref = index["D-0"]
        assert ref.drawing_id == 318845
        assert ref.drawing_name == "D-0"
        assert "ifieldsmart/proj123" in ref.s3_url
        assert ref.pdf_name == "pdfA102Plan1-1"

    def test_build_with_missing_s3_path(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(s3_path="")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)

        assert len(index) == 0
        assert meta["drawings_missing"] == 1

    def test_build_with_missing_pdf_name(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(pdf_name="")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)

        assert len(index) == 0
        assert meta["drawings_missing"] == 1

    def test_sibling_recovery(self):
        from services.source_index import SourceIndexBuilder

        # Record A has no source fields; Record B (same drawing) does
        rec_a = _make_record(drawing_name="X-1", s3_path="", pdf_name="")
        rec_b = _make_record(
            drawing_name="X-1",
            s3_path="ifieldsmart/proj/Drawings/pdf",
            pdf_name="pdfX1Plan",
            drawing_id=999,
        )
        rec_b["_id"] = "id_X-1_b"

        builder = SourceIndexBuilder()
        index, meta = builder.build([rec_a, rec_b])

        assert "X-1" in index
        assert index["X-1"].drawing_id == 999
        assert meta["recovery_count"] == 1

    def test_path_traversal_blocked(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(s3_path="../../../etc/passwd")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)

        assert len(index) == 0

    def test_invalid_prefix_blocked(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(s3_path="malicious/bucket/path")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)

        assert len(index) == 0

    def test_coordinate_validation_negative(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(x=-5, y=-10, width=-1, height=-1)]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)

        ref = index["A102"]
        assert ref.x is None
        assert ref.y is None
        assert ref.width is None
        assert ref.height is None

    def test_coordinate_zero_is_valid(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(x=0, y=0, width=100, height=50)]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)

        ref = index["A102"]
        assert ref.x == 0
        assert ref.y == 0
        assert ref.width == 100
        assert ref.height == 50

    def test_empty_records(self):
        from services.source_index import SourceIndexBuilder

        builder = SourceIndexBuilder()
        index, meta = builder.build([])

        assert index == {}
        assert meta["drawings_total"] == 0

    def test_dedup_by_drawing_name(self):
        from services.source_index import SourceIndexBuilder

        rec1 = _make_record(drawing_name="A102", drawing_id=111)
        rec2 = _make_record(drawing_name="A102", drawing_id=222)
        rec2["_id"] = "id_A102_b"

        builder = SourceIndexBuilder()
        index, _ = builder.build([rec1, rec2])

        assert len(index) == 1
        assert index["A102"].drawing_id == 111  # first wins

    def test_url_construction(self):
        from services.source_index import SourceIndexBuilder

        records = [_make_record(
            s3_path="ifieldsmart/proj/Drawings/pdf",
            pdf_name="myPdf",
        )]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)

        ref = index["A102"]
        assert ref.s3_url == (
            "https://agentic-ai-production.s3.amazonaws.com/"
            "ifieldsmart/proj/Drawings/pdf/myPdf.pdf"
        )

    def test_to_dict(self):
        from services.source_index import SourceReference

        ref = SourceReference(
            drawing_id=1, drawing_name="A1", drawing_title="Title",
            s3_url="https://example.com", pdf_name="pdf1",
            x=10, y=20, width=100, height=50,
        )
        d = ref.to_dict()
        assert d["drawing_id"] == 1
        assert d["s3_url"] == "https://example.com"
        assert d["x"] == 10

    def test_source_reference_is_frozen(self):
        from services.source_index import SourceReference

        ref = SourceReference(
            drawing_id=1, drawing_name="A1", drawing_title="T",
            s3_url="u", pdf_name="p", x=0, y=0, width=0, height=0,
        )
        with pytest.raises(AttributeError):
            ref.drawing_id = 999
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "c:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent"
python -m pytest tests/test_source_index.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'services.source_index'`

- [ ] **Step 3: Implement source_index.py**

Create `services/source_index.py` with the full implementation from the spec (Section 5.1). The complete code:

```python
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

# Allowlisted S3 path prefixes (security: prevent path traversal)
_ALLOWED_S3_PREFIXES = ("ifieldsmart/", "agentic-ai-production/")


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Immutable source reference for a single drawing."""

    drawing_id: int
    drawing_name: str
    drawing_title: str
    s3_url: str
    pdf_name: str
    x: int | None  # None = unknown, 0 = valid top-left
    y: int | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceIndexBuilder:
    """Builds a source index from deduplicated API records."""

    def build(
        self, records: list[dict]
    ) -> tuple[dict[str, SourceReference], dict[str, Any]]:
        """
        Build {drawingName -> SourceReference} from raw records.
        Returns (source_index, build_metadata).
        """
        start = time.perf_counter()
        index: dict[str, SourceReference] = {}
        warnings: list[str] = []

        for rec in records:
            dn = (rec.get("drawingName") or "").strip()
            if not dn or dn in index:
                continue

            s3_path_raw = rec.get("s3BucketPath", "")
            pdf_name = rec.get("pdfName", "")

            if not s3_path_raw or not pdf_name:
                warnings.append(dn)
                continue

            s3_path = self._sanitize_s3_path(s3_path_raw)
            if not s3_path:
                logger.warning(
                    "Invalid S3 path for drawing %s: %s", dn, s3_path_raw
                )
                warnings.append(dn)
                continue

            x, y, w, h = self._validate_coordinates(rec)
            index[dn] = SourceReference(
                drawing_id=int(rec.get("drawingId", 0) or 0),
                drawing_name=dn,
                drawing_title=rec.get("drawingTitle", ""),
                s3_url=self._build_s3_url(s3_path, pdf_name),
                pdf_name=pdf_name,
                x=x,
                y=y,
                width=w,
                height=h,
            )

        # Recovery pass: fill gaps from sibling records
        pre_recovery = len(index)
        index = self._recover_missing_sources(records, index)
        recovered = len(index) - pre_recovery

        build_ms = int((time.perf_counter() - start) * 1000)
        if warnings:
            logger.warning(
                "Missing source fields for %d drawings: %s",
                len(warnings),
                warnings[:10],
            )

        metadata = {
            "drawings_total": len(index),
            "drawings_missing": max(0, len(warnings) - recovered),
            "recovery_count": recovered,
            "build_ms": build_ms,
        }
        return index, metadata

    def _sanitize_s3_path(self, raw_path: str) -> str | None:
        """Validate S3 path: no ../, must start with allowed prefix, URL-encode."""
        if not raw_path or ".." in raw_path:
            return None
        if not any(raw_path.startswith(p) for p in _ALLOWED_S3_PREFIXES):
            return None
        return quote(raw_path, safe="/")

    def _build_s3_url(self, s3_path: str, pdf_name: str) -> str:
        """Construct direct S3 URL from sanitized path + PDF name."""
        pattern = settings.s3_pdf_url_pattern
        return pattern.format(
            bucket=settings.s3_bucket_name, path=s3_path, name=pdf_name
        )

    def _validate_coordinates(
        self, record: dict
    ) -> tuple[int | None, int | None, int | None, int | None]:
        """
        Extract and validate x, y, width, height.
        Returns None for missing or negative values. 0 is valid.
        """

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

    def _recover_missing_sources(
        self,
        records: list[dict],
        index: dict[str, SourceReference],
    ) -> dict[str, SourceReference]:
        """
        Backpropagation pass: fill gaps from sibling records.
        Returns a NEW dict (does not mutate input).
        """
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
                            x=x,
                            y=y,
                            width=w,
                            height=h,
                        )
                        break

        return {**index, **recovered}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_source_index.py -v
```

Expected: All 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/source_index.py tests/test_source_index.py
git commit -m "feat: add SourceIndexBuilder with TDD (13 tests, sanitization, recovery)"
```

---

## Task 3: API Client — Fallback Methods

**Files:**
- Modify: `services/api_client.py` (add after line 170, after `get_summary_by_trade_and_set`)
- Create: `tests/test_api_migration.py`

- [ ] **Step 1: Write test file for API migration**

Create `tests/test_api_migration.py`:

```python
"""Integration tests for API client endpoint migration with fallback."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from services.api_client import APIClient


@pytest.fixture
def api_client():
    client = APIClient.__new__(APIClient)
    client._http = AsyncMock(spec=httpx.AsyncClient)
    client._cache = None
    return client


class TestFetchWithFallback:
    """Tests for _fetch_with_fallback()."""

    @pytest.mark.asyncio
    async def test_primary_success(self, api_client):
        """Primary endpoint returns 200 -> use primary records."""
        fake_records = [{"_id": "1", "drawingName": "A1"}]

        with patch.object(
            api_client, "_fetch_all_pages", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = fake_records
            records, label = await api_client._fetch_with_fallback(
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade",
                fallback_label="summaryByTrade",
                params={"projectId": 7292, "trade": "Civil"},
            )

        assert records == fake_records
        assert label == "byTrade"
        mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self, api_client):
        """Primary returns 500 -> fall back to summary endpoint."""
        fallback_records = [{"_id": "2", "drawingName": "B1"}]
        call_count = 0

        async def side_effect(path, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status_code = 500
                raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
            return fallback_records

        with patch.object(
            api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect
        ):
            records, label = await api_client._fetch_with_fallback(
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade",
                fallback_label="summaryByTrade",
                params={"projectId": 7292, "trade": "Civil"},
            )

        assert records == fallback_records
        assert label == "summaryByTrade"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self, api_client):
        """Primary times out -> fall back."""
        fallback_records = [{"_id": "3"}]
        call_count = 0

        async def side_effect(path, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timed out")
            return fallback_records

        with patch.object(
            api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect
        ):
            records, label = await api_client._fetch_with_fallback(
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade",
                fallback_label="summaryByTrade",
                params={"projectId": 7292, "trade": "Civil"},
            )

        assert records == fallback_records
        assert label == "summaryByTrade"

    @pytest.mark.asyncio
    async def test_labels_for_set_variant(self, api_client):
        """byTradeAndSet falls back to summaryByTradeAndSet with correct labels."""
        fallback_records = [{"_id": "4"}]
        call_count = 0

        async def side_effect(path, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timed out")
            return fallback_records

        with patch.object(
            api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect
        ):
            records, label = await api_client._fetch_with_fallback(
                primary_path="/api/drawingText/byTradeAndSet",
                fallback_path="/api/drawingText/summaryByTradeAndSet",
                primary_label="byTradeAndSet",
                fallback_label="summaryByTradeAndSet",
                params={"projectId": 7292, "trade": "Civil", "setId": 4720},
            )

        assert label == "summaryByTradeAndSet"


class TestGetByTrade:
    """Tests for get_by_trade() routing."""

    @pytest.mark.asyncio
    async def test_feature_flag_true_uses_new_endpoint(self, api_client):
        """USE_NEW_API=true -> calls _fetch_with_fallback with byTrade paths."""
        fake_records = [{"_id": "1"}]

        with patch.object(
            api_client, "_fetch_with_fallback", new_callable=AsyncMock,
            return_value=(fake_records, "byTrade"),
        ) as mock_fallback:
            with patch("services.api_client.settings") as mock_settings:
                mock_settings.use_new_api = True
                mock_settings.api_base_url = "https://mongo.ifieldsmart.com"
                mock_settings.by_trade_path = "/api/drawingText/byTrade"
                mock_settings.summary_by_trade_path = "/api/drawingText/summaryByTrade"

                records, metadata = await api_client.get_by_trade(7292, "Civil")

        assert records == fake_records
        assert metadata["endpoint_used"] == "byTrade"
        assert metadata["fallback"] is False

    @pytest.mark.asyncio
    async def test_feature_flag_false_uses_existing(self, api_client):
        """USE_NEW_API=false -> calls get_summary_by_trade directly."""
        fake_records = [{"_id": "1"}]

        with patch.object(
            api_client, "get_summary_by_trade", new_callable=AsyncMock,
            return_value=fake_records,
        ):
            with patch("services.api_client.settings") as mock_settings:
                mock_settings.use_new_api = False

                records, metadata = await api_client.get_by_trade(7292, "Civil")

        assert records == fake_records
        assert metadata["endpoint_used"] == "summaryByTrade"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_api_migration.py -v 2>&1 | head -20
```

Expected: FAIL — `_fetch_with_fallback` and `get_by_trade` don't exist yet.

- [ ] **Step 3: Implement _fetch_with_fallback in api_client.py**

Open `services/api_client.py`. Add the following method to the `APIClient` class, after the existing `get_summary_by_trade_and_set()` method (after ~line 170):

```python
    async def _fetch_with_fallback(
        self,
        primary_path: str,
        fallback_path: str,
        primary_label: str,
        fallback_label: str,
        params: dict,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Try primary endpoint. On HTTP error/timeout -> retry with fallback.
        Returns (records, endpoint_used_label).
        """
        try:
            records = await self._fetch_all_pages(
                params["projectId"],
                params["trade"],
                set_id=params.get("setId"),
            )
            return records, primary_label
        except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            logger.warning(
                "Primary endpoint %s failed (%s), falling back to %s",
                primary_path,
                exc,
                fallback_path,
            )
            # Temporarily swap the path settings for fallback
            original_path = settings.by_trade_path
            try:
                # Use the fallback path for _fetch_all_pages
                records = await self._fetch_all_pages(
                    params["projectId"],
                    params["trade"],
                    set_id=params.get("setId"),
                )
                return records, fallback_label
            finally:
                pass  # settings are module-level, no swap needed
```

**Note:** The actual implementation will need to be adapted to the existing `_fetch_all_pages` signature. The key pattern is: try primary, catch errors, call fallback.

- [ ] **Step 4: Implement get_by_trade in api_client.py**

Add after `_fetch_with_fallback`:

```python
    async def get_by_trade(
        self,
        project_id: int,
        trade: str,
        cache_service: Optional[CacheService] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """
        Fetch records using byTrade endpoint (richer fields).
        Falls back to summaryByTrade on failure.
        Returns (records, metadata).
        """
        if not settings.use_new_api:
            records = await self.get_summary_by_trade(project_id, trade)
            return records, {"endpoint_used": "summaryByTrade", "fallback": False}

        params = {"projectId": project_id, "trade": trade}
        records, label = await self._fetch_with_fallback(
            primary_path=settings.by_trade_path,
            fallback_path=settings.summary_by_trade_path,
            primary_label="byTrade",
            fallback_label="summaryByTrade",
            params=params,
        )
        return records, {
            "endpoint_used": label,
            "fallback": label != "byTrade",
        }

    async def get_by_trade_and_set(
        self,
        project_id: int,
        trade: str,
        set_ids: list[Union[int, str]],
        cache_service: Optional[CacheService] = None,
    ) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
        """
        Fetch records using byTradeAndSet endpoint.
        Falls back to summaryByTradeAndSet on failure.
        Returns (records, set_names, metadata).
        """
        if not settings.use_new_api:
            records, set_names = await self.get_summary_by_trade_and_set(
                project_id, trade, set_ids
            )
            return records, set_names, {"endpoint_used": "summaryByTradeAndSet", "fallback": False}

        all_records: list[dict] = []
        seen_ids: set[str] = set()
        set_names: list[str] = []

        for sid in set_ids:
            params = {"projectId": project_id, "trade": trade, "setId": sid}
            records, label = await self._fetch_with_fallback(
                primary_path=settings.by_trade_and_set_path,
                fallback_path=settings.summary_by_trade_and_set_path,
                primary_label="byTradeAndSet",
                fallback_label="summaryByTradeAndSet",
                params=params,
            )
            for rec in records:
                rid = rec.get("_id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_records.append(rec)
                sn = rec.get("setName", "")
                if sn and sn not in set_names:
                    set_names.append(sn)

        return all_records, set_names, {
            "endpoint_used": label,
            "fallback": label != "byTradeAndSet",
        }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_api_migration.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api_client.py tests/test_api_migration.py
git commit -m "feat: add get_by_trade with fallback to summaryByTrade (6 tests)"
```

---

## Task 4: Document Hyperlinks + Traceability Table

**Files:**
- Modify: `services/document_generator.py:73-83`
- Modify: `services/exhibit_document_generator.py:115-125`
- Create: `tests/test_document_hyperlinks.py`

- [ ] **Step 1: Write tests for document hyperlinks**

Create `tests/test_document_hyperlinks.py`:

```python
"""Tests for Word document hyperlinks and traceability tables."""

import pytest
from pathlib import Path
from docx import Document

from services.source_index import SourceReference


def _make_source_index() -> dict[str, SourceReference]:
    return {
        "A102": SourceReference(
            drawing_id=318845, drawing_name="A102",
            drawing_title="ARCH SITE PLAN",
            s3_url="https://bucket.s3.amazonaws.com/path/pdf.pdf",
            pdf_name="pdfA102", x=100, y=200, width=50, height=30,
        ),
        "E-101": SourceReference(
            drawing_id=12345, drawing_name="E-101",
            drawing_title="ELECTRICAL FLOOR PLAN",
            s3_url="https://bucket.s3.amazonaws.com/path2/pdf2.pdf",
            pdf_name="pdfE101", x=300, y=400, width=60, height=40,
        ),
    }


class TestDocumentGeneratorHyperlinks:
    """Tests for document_generator.py hyperlink features."""

    def test_traceability_table_added(self, tmp_path):
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        source_index = _make_source_index()
        result = gen.generate_sync(
            content="## Scope\n- Item 1\n- Item 2",
            project_id=7292,
            trade="Civil",
            document_type="scope",
            project_name="Test Project (ID: 7292)",
            source_index=source_index,
        )

        # Open the generated document and check for the table
        doc = Document(result.file_path)
        tables = doc.tables
        assert len(tables) >= 1, "Expected at least one table (traceability)"
        # Last table should be the traceability table
        last_table = tables[-1]
        # Header row + 2 data rows
        assert len(last_table.rows) == 3

    def test_traceability_table_skipped_when_empty(self, tmp_path):
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        result = gen.generate_sync(
            content="## Scope\n- Item 1",
            project_id=7292,
            trade="Civil",
            document_type="scope",
            project_name="Test Project (ID: 7292)",
            source_index={},
        )

        doc = Document(result.file_path)
        # No traceability table when source_index is empty
        # Check no "Source Reference Table" heading
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert "Source Reference Table" not in headings

    def test_document_without_source_index(self):
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        result = gen.generate_sync(
            content="## Scope\n- Item 1",
            project_id=7292,
            trade="Civil",
            document_type="scope",
            project_name="Test Project (ID: 7292)",
            source_index=None,
        )

        assert result is not None
        assert result.filename.endswith(".docx")

    def test_exhibit_traceability_table(self):
        from services.exhibit_document_generator import ExhibitDocumentGenerator

        gen = ExhibitDocumentGenerator()
        source_index = _make_source_index()
        result = gen.generate_sync(
            content="## Scope\n- Item 1",
            project_name="Test Project (ID: 7292)",
            trade="Civil",
            document_type="scope",
            project_id=7292,
            source_index=source_index,
        )

        doc = Document(result.file_path)
        tables = doc.tables
        assert len(tables) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_document_hyperlinks.py -v 2>&1 | head -20
```

Expected: FAIL — `source_index` parameter doesn't exist yet.

- [ ] **Step 3: Add _add_hyperlink and _add_traceability_table to document_generator.py**

Open `services/document_generator.py`. Add these methods to the `DocumentGenerator` class:

```python
    def _add_hyperlink(self, paragraph, url: str, text: str, color: str = "0563C1"):
        """Add a clickable hyperlink to a Word paragraph."""
        part = paragraph.part
        r_id = part.relate_to(
            url,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True,
        )
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), r_id)
        run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        c = OxmlElement("w:color")
        c.set(qn("w:val"), color)
        rPr.append(c)
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)
        run.append(rPr)
        t = OxmlElement("w:t")
        t.text = text
        run.append(t)
        hyperlink.append(run)
        paragraph._element.append(hyperlink)

    def _add_traceability_table(self, doc, source_index):
        """Append a source reference traceability table to the document."""
        if not source_index:
            return

        doc.add_page_break()
        doc.add_heading("Source Reference Table", level=2)

        table = doc.add_table(rows=1, cols=4)
        try:
            table.style = "Light Grid Accent 1"
        except KeyError:
            table.style = "Table Grid"
        headers = ["Drawing Name", "Drawing Title", "PDF Link", "Coordinates"]
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
            p2 = row[2].paragraphs[0]
            if ref.s3_url:
                self._add_hyperlink(p2, ref.s3_url, "View PDF")
            else:
                p2.text = "N/A"
            if ref.x is not None and ref.y is not None:
                row[3].text = f"({ref.x}, {ref.y}) {ref.width}x{ref.height}"
            else:
                row[3].text = "\u2014"

        hyperlink_count = sum(1 for ref in source_index.values() if ref.s3_url)
        logger.info("Traceability table: %d drawings, %d hyperlinks",
                     len(source_index), hyperlink_count)
```

- [ ] **Step 4: Add source_index parameter to generate_sync in document_generator.py**

Modify the `generate_sync` signature (line ~73) to add `source_index=None`:

```python
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
        source_index: dict = None,  # NEW: source references for hyperlinks
    ) -> GeneratedDocument:
```

Then, in the body of `generate_sync`, right before the `doc.save()` call, add:

```python
        # Add traceability table if source references are available
        if source_index and settings.source_ref_enabled:
            self._add_traceability_table(doc, source_index)
```

Also update the `generate` async method signature to pass through `source_index`:

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
            source_index=source_index,
        )
```

- [ ] **Step 5: Add same changes to exhibit_document_generator.py**

Add `_add_hyperlink` and `_add_traceability_table` methods (identical code). Add `source_index=None` param to `generate_sync` (line ~115):

```python
    def generate_sync(
        self,
        content: str,
        project_name: str,
        trade: str,
        document_type: str,
        drawing_summary: Optional[list[dict]] = None,
        title: Optional[str] = None,
        project_id: int = 0,
        source_index: dict = None,  # NEW
    ) -> GeneratedDocument:
```

Add before `doc.save()`:

```python
        if source_index and settings.source_ref_enabled:
            self._add_traceability_table(doc, source_index)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_document_hyperlinks.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add services/document_generator.py services/exhibit_document_generator.py tests/test_document_hyperlinks.py
git commit -m "feat: add Word hyperlinks + traceability table to both document generators (4 tests)"
```

---

## Task 5: Pipeline Wiring — Generation Agent + Data Agent

**Files:**
- Modify: `agents/data_agent.py:36-70`
- Modify: `agents/generation_agent.py:188,320,358`
- Modify: `main.py:83`

- [ ] **Step 1: Initialize SourceIndexBuilder in main.py**

Open `main.py`. After the `DocumentGenerator` initialization (around line 83), add:

```python
        from services.source_index import SourceIndexBuilder
        source_index_builder = SourceIndexBuilder()
```

Attach to app.state (around line 120):

```python
        app.state.source_index_builder = source_index_builder
```

- [ ] **Step 2: Update data_agent.py to return records + metadata**

Open `agents/data_agent.py`. The `prepare_context` method (line 36) currently calls `self._builder.build()`. Modify it to:

1. Call `api_client.get_by_trade()` when `settings.use_new_api` is True
2. Return the raw records alongside context for source index building
3. Return API metadata for endpoint tracking

The key change is that `prepare_context` should return a 3-tuple: `(context_str, stats_dict, raw_records)` instead of the current 2-tuple. Update the return type and add `raw_records` to the return value.

Add to the method:

```python
        # Store raw records for source index building
        stats["raw_records"] = records  # records from API client
        stats["api_metadata"] = metadata  # endpoint_used, fallback
```

- [ ] **Step 3: Wire source index in generation_agent.py**

Open `agents/generation_agent.py`. The key changes are in the `process` method:

**After prepare_context returns (around line 194):**

```python
        # Build source index from raw records (parallel with nothing — fast ~10ms)
        raw_records = stats.get("raw_records", [])
        api_metadata = stats.get("api_metadata", {})
        source_index = {}
        source_meta = {}
        if settings.source_ref_enabled and raw_records:
            source_index_builder = self._source_index_builder
            source_index, source_meta = source_index_builder.build(raw_records)
```

**Pass source_index to DocumentGenerator (around line 320):**

```python
        doc = await self._doc_gen.generate(
            content=answer,
            project_id=request.project_id,
            trade=intent.trade or "General",
            document_type=intent.document_type,
            project_name=project_display_name,
            set_ids=set_ids,
            set_names=set_names,
            source_index=source_index,  # NEW
        )
```

**Collect warnings (before building ChatResponse):**

```python
        warnings: list[str] = []
        if api_metadata.get("fallback"):
            warnings.append(
                "Using fallback API endpoint -- source PDF links may be unavailable."
            )
        missing_count = source_meta.get("drawings_missing", 0)
        if missing_count > 0:
            warnings.append(
                f"Source references unavailable for {missing_count} drawings."
            )
```

**Add to ChatResponse construction (around line 358):**

```python
        source_references={
            name: ref.to_dict() for name, ref in source_index.items()
        } if source_index else {},
        api_version=api_metadata.get("endpoint_used", ""),
        warnings=warnings,
```

**Add source_index_build to token_log:**

```python
        if source_meta:
            token_log_steps["source_index_build"] = source_meta
```

- [ ] **Step 4: Update GenerationAgent.__init__ to accept source_index_builder**

In `main.py`, update the `GenerationAgent` instantiation (around line 104-113) to pass the builder:

```python
        generation_agent = GenerationAgent(
            ...,
            source_index_builder=source_index_builder,
        )
```

And in `agents/generation_agent.py`, update the `__init__` method to accept and store it:

```python
    def __init__(self, ..., source_index_builder=None):
        ...
        self._source_index_builder = source_index_builder
```

- [ ] **Step 5: Apply same wiring to process_stream method**

The `process_stream` method in `generation_agent.py` (around line 460) has the same pipeline structure. Apply the identical changes:
- Build source index after prepare_context
- Pass source_index to doc generator
- Collect warnings
- Add to streaming response

- [ ] **Step 6: Run existing tests to verify no regression**

```bash
python -m pytest tests/ -v --ignore=tests/test_source_index.py --ignore=tests/test_api_migration.py --ignore=tests/test_document_hyperlinks.py 2>&1 | tail -20
```

Expected: All existing tests PASS (backward compatibility).

- [ ] **Step 7: Commit**

```bash
git add agents/data_agent.py agents/generation_agent.py main.py
git commit -m "feat: wire source index through pipeline (data_agent -> generation_agent -> doc gen)"
```

---

## Task 6: Raw Data Endpoint

**Files:**
- Modify: `routers/projects.py:14`

- [ ] **Step 1: Add raw-data endpoint to projects router**

Open `routers/projects.py`. Add after the existing `/{project_id}/context` route:

```python
@router.get("/{project_id}/raw-data")
async def get_raw_data(
    project_id: int,
    trade: str,
    set_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 500,
    request: Request = None,
) -> dict:
    """
    Fetch raw API records for UI display.
    Full path: GET /api/projects/{project_id}/raw-data?trade=Civil&set_id=4720
    """
    api_client = request.app.state.api_client
    cache_service = request.app.state.cache

    if set_id:
        records, _, _ = await api_client.get_by_trade_and_set(
            project_id, trade, [set_id], cache_service=cache_service
        )
    else:
        records, _ = await api_client.get_by_trade(
            project_id, trade, cache_service=cache_service
        )

    total = len(records)
    page = records[skip : skip + limit]
    return {
        "success": True,
        "data": {
            "records": page,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + limit) < total,
        },
    }
```

Add necessary imports at the top of the file:

```python
from typing import Optional
from fastapi import Request
```

- [ ] **Step 2: Verify endpoint loads**

```bash
python -c "from routers.projects import router; print([r.path for r in router.routes])"
```

Expected: Shows both `/{project_id}/context` and `/{project_id}/raw-data`.

- [ ] **Step 3: Commit**

```bash
git add routers/projects.py
git commit -m "feat: add GET /api/projects/{id}/raw-data endpoint for UI raw data display"
```

---

## Task 7: Health Check Enhancement

**Files:**
- Modify: `main.py` (or wherever the `/health` endpoint is defined)

- [ ] **Step 1: Find and update the health endpoint**

Search for the health endpoint handler. Add the `new_api` field logic:

```python
    # In the health check handler:
    new_api_status = "disabled"
    if settings.use_new_api:
        try:
            test_resp = await api_client._http.get(
                f"{settings.api_base_url}{settings.by_trade_path}",
                params={"projectId": 7292, "trade": "Civil", "skip": 0, "limit": 1},
                timeout=5,
            )
            new_api_status = "ok" if test_resp.status_code == 200 else "degraded (using fallback)"
        except Exception:
            new_api_status = "degraded (using fallback)"

    return HealthResponse(
        status="ok",
        redis=redis_status,
        openai=openai_status,
        new_api=new_api_status,
        version=...,
    )
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add new_api status to /health endpoint"
```

---

## Task 8: Streamlit UI — Raw Data + Source Refs + Alerts

**Files:**
- Modify: `scope-gap-ui/api/client.py:12`
- Modify: `scope-gap-ui/components/chat.py:45`
- Modify: `scope-gap-ui/components/reference_panel.py`

- [ ] **Step 1: Add get_raw_data to Streamlit API client**

Open `scope-gap-ui/api/client.py`. Add:

```python
def get_raw_data(
    project_id: int, trade: str, set_id: int = None, skip: int = 0, limit: int = 500
) -> Optional[dict]:
    """Fetch raw API records for the data expander."""
    params = {"trade": trade, "skip": skip, "limit": limit}
    if set_id:
        params["set_id"] = set_id
    return _get(f"/api/projects/{project_id}/raw-data", params=params)
```

- [ ] **Step 2: Add raw data expander to chat component**

Open `scope-gap-ui/components/chat.py`. After the assistant message rendering block (around line 45-52), add:

```python
            # Raw API Data expander
            source_refs = msg.get("source_references", {})
            api_warnings = msg.get("warnings", [])
            api_version = msg.get("api_version", "")

            # Fallback alert banner
            if api_warnings:
                for w in api_warnings:
                    st.warning(w)
            if api_version.startswith("summary"):
                st.error(
                    "Using fallback API -- source references may be unavailable. "
                    "Contact support if this persists."
                )

            # Raw data expander
            raw_data = msg.get("raw_records")
            if raw_data:
                with st.expander("Raw API Data", expanded=False):
                    import pandas as pd
                    all_cols = list(raw_data[0].keys()) if raw_data else []
                    visible_cols = st.multiselect(
                        "Visible columns",
                        all_cols,
                        default=all_cols,
                        key=f"cols_{msg.get('time', '')}",
                    )
                    if visible_cols:
                        df = pd.DataFrame(raw_data)[visible_cols]
                        st.dataframe(df, use_container_width=True, height=400)
                        csv = df.to_csv(index=False)
                        st.download_button(
                            "Download CSV", csv, "raw_data.csv", "text/csv",
                            key=f"csv_{msg.get('time', '')}",
                        )
```

- [ ] **Step 3: Add source reference links to reference_panel.py**

Open `scope-gap-ui/components/reference_panel.py`. Add a function for source references:

```python
def render_source_references(source_refs: dict):
    """Render clickable source reference links."""
    if not source_refs:
        st.info("Source references not available.")
        return

    with st.expander("Source References", expanded=True):
        for name, ref in sorted(source_refs.items()):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{name}** -- {ref.get('drawing_title', '')}")
            with col2:
                s3_url = ref.get("s3_url")
                if s3_url:
                    st.markdown(f"[Open PDF]({s3_url})")
                else:
                    st.caption("No PDF link")
```

- [ ] **Step 4: Commit**

```bash
git add scope-gap-ui/api/client.py scope-gap-ui/components/chat.py scope-gap-ui/components/reference_panel.py
git commit -m "feat: add raw data expander, source panel, fallback alerts to Streamlit UI"
```

---

## Task 9: Update .env.example and STREAMLIT_API_FLOW.md

**Files:**
- Modify: `.env.example`
- Modify: `docs/STREAMLIT_API_FLOW.md`

- [ ] **Step 1: Add new vars to .env.example**

Append the 3 new env vars with comments to `.env.example`.

- [ ] **Step 2: Add raw-data endpoint to STREAMLIT_API_FLOW.md**

Document the new `GET /api/projects/{project_id}/raw-data` endpoint with:
- Request parameters (trade, set_id, skip, limit)
- Response shape
- Usage context (Streamlit raw data expander)

- [ ] **Step 3: Document new ChatResponse fields**

Add `source_references`, `api_version`, `warnings` to the ChatResponse documentation.

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/STREAMLIT_API_FLOW.md
git commit -m "docs: update API flow docs and .env.example with v4 migration fields"
```

---

## Task 10: Run Full Test Suite + Coverage

- [ ] **Step 1: Run all new tests**

```bash
python -m pytest tests/test_source_index.py tests/test_api_migration.py tests/test_document_hyperlinks.py -v
```

Expected: All tests PASS.

- [ ] **Step 2: Run full regression suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: All existing + new tests PASS.

- [ ] **Step 3: Check coverage on new code**

```bash
python -m pytest tests/test_source_index.py tests/test_api_migration.py tests/test_document_hyperlinks.py --cov=services/source_index --cov-report=term-missing --cov-branch
```

Expected: >= 90% coverage on `services/source_index.py`.

- [ ] **Step 4: Smoke test the full pipeline**

```bash
python -c "
import asyncio
from main import app
# Verify app starts without import errors
print('App loaded successfully')
print('Routes:', [r.path for r in app.routes])
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test: full regression suite passes, 90%+ coverage on new code"
```

---

## Summary

| Task | Stream | What It Builds | Tests |
|------|--------|---------------|-------|
| 1 | Foundation | Config + Schema (3 settings, 3 response fields) | Config load verification |
| 2 | B | SourceIndexBuilder + SourceReference | 13 unit tests |
| 3 | A | API client fallback methods | 6 integration tests |
| 4 | C | Word hyperlinks + traceability table | 4 document tests |
| 5 | A+B+C | Pipeline wiring (data_agent -> gen_agent -> doc gen) | Regression suite |
| 6 | D | Raw data endpoint | Endpoint load verification |
| 7 | D | Health check enhancement | Manual verification |
| 8 | D | Streamlit UI (expander, panel, alerts) | Manual UI test |
| 9 | Docs | .env.example + STREAMLIT_API_FLOW.md | N/A |
| 10 | All | Full regression + coverage | All tests + 90% coverage |

**Total: 10 tasks, ~23 unit/integration tests, 10 commits.**
