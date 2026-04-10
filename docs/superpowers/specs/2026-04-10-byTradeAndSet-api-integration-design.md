# Design Spec: `byTradeAndSet` API Integration + Source References + Document Enrichment + UI Raw Data

**Date:** 2026-04-10
**Status:** DRAFT — Awaiting User Approval
**Scope:** Core API migration, source reference index, document hyperlinks, traceability table, Streamlit raw data display
**Agent:** Construction Intelligence Agent
**Questionnaire:** [2026-04-10-api-integration-questionnaire.md](2026-04-10-api-integration-questionnaire.md)

---

## 1. Problem Statement

The construction agent currently uses `summaryByTrade`/`summaryByTradeAndSet` endpoints that return a subset of available fields. A richer endpoint `byTradeAndSet` exists that returns additional source-tracing fields (`drawingId`, `s3BucketPath`, `pdfName`, `x`, `y`, `width`, `height`). These fields enable:

1. **Clickable PDF hyperlinks** in generated Word documents — users click a drawing name to open the source PDF
2. **Source traceability tables** — audit-grade mapping from scope items to exact drawing/PDF/coordinates
3. **Raw API data transparency** — users see the full data the agent used to generate their response
4. **Future PDF annotation** — coordinates enable highlighting the exact text region on the source drawing

**What already exists (no work needed):**
- `services/sql_service.py` — project name lookup (fully implemented)
- Project name in both document generators (fully implemented)
- `by_trade_and_set_path` in `config.py` (already defined)
- Scope pipeline partial S3 extraction in `scope_pipeline/services/data_fetcher.py` (separate subsystem)

---

## 2. Decisions Summary (from Questionnaire)

| # | Decision | Choice |
|---|----------|--------|
| Q1.1 | Endpoint migration | **(C)** Add new methods with routing switch + auto-fallback to `summaryByTrade` on failure |
| Q1.2 | Data volume | **(C)** Two-tier extraction: lightweight for LLM, full for docs |
| Q1.3 | Concurrency | **(A)** Keep at 30 |
| Q2.1 | Source index build | **(B)** Build after dedup |
| Q2.2 | S3 URL format | **(A)** Direct S3 bucket URLs |
| Q2.3 | Source in LLM | **(A)** No source data in LLM context |
| Q4.1 | Request changes | **(A)** No ChatRequest changes |
| Q4.2 | Response changes | **(D)** Source refs in response + separate raw data endpoint |
| Q4.3 | Missing fields | **(C)** Log warning, skip hyperlink |
| Q5.1 | Path security | **(B+C)** Sanitize + allowlist prefix |
| Q6.1 | Test coverage | **90%** on new code |
| Q6.2 | Feature flag | **(B)** `USE_NEW_API` env var |
| Q7.2 | Traceability table | **(B)** In **every** document type |
| Q9.2 | Missing source recovery | Active resolution (backpropagation/retry), not just banner |
| Q11.2 | S3 access | Public for testing, authenticated in production |
| Q13.1 | API version in response | **(B)** Add `api_version` field |
| Q14.1 | Fallback alerting | **(C)** Immediate alert on Streamlit UI |
| Q15.1 | Raw data UI | **(B)** Collapsible `st.expander` below chat, ALL records |
| Q15.2 | Source ref UI | **(C)** Inline hyperlinks + dedicated source panel |
| Q15.3 | Raw table features | Search, sort, pagination, CSV export, column toggle — all in v1 |

---

## 3. Architecture Overview

Four independent work streams converging in the pipeline:

```
Stream A: API Migration (api_client.py, config.py)
  └─ Switch primary endpoints to byTrade/byTradeAndSet with summaryByTrade fallback

Stream B: Source Reference Index (NEW: services/source_index.py)
  └─ Build {drawingName → {drawingId, s3Url, pdfName, x, y, w, h}} after dedup

Stream C: Document Enrichment (document_generator.py, exhibit_document_generator.py)
  └─ Clickable hyperlinks on drawing names + traceability table appendix

Stream D: UI Integration (scope-gap-ui/, routers/chat.py)
  └─ Raw data expander, source panel, fallback alert banner
```

Data flow:

```
ChatRequest
  │
  ▼
APIClient.get_by_trade()              ◄── Stream A: new endpoint + fallback
  │
  ├─► records[] (full fields)
  │     │
  │     ├─► ContextBuilder.build()    ◄── existing: uses text/drawingName/csi only
  │     │     └─► LLM context (no source fields)
  │     │
  │     └─► SourceIndexBuilder.build() ◄── Stream B: extracts source fields
  │           └─► source_index dict
  │
  ├─► LLM generation (unchanged)
  │
  ├─► DocumentGenerator.generate()     ◄── Stream C: receives source_index
  │     ├─► Hyperlinks on drawing names
  │     └─► Traceability table appendix
  │
  └─► ChatResponse                     ◄── Stream D: source_references + api_version + warnings
        │
        └─► Streamlit UI
              ├─► Raw data expander (all records)
              ├─► Source reference panel
              └─► Fallback alert banner (if degraded)
```

---

## 4. Stream A: API Migration

### 4.1 Config Changes (`config.py`)

Add three new settings:

```python
# ── API Migration ────────────────────────────────────────
use_new_api: bool = True                    # Feature flag: True = byTrade, False = summaryByTrade
s3_pdf_url_pattern: str = "https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf"
source_ref_enabled: bool = True             # Kill switch for source reference generation
```

### 4.2 API Client Changes (`services/api_client.py`)

**New method: `get_by_trade()`**

Mirrors existing `get_summary_by_trade()` but calls `byTrade` endpoint. Includes auto-fallback:

```python
async def get_by_trade(
    self,
    project_id: int,
    trade: str,
    cache_service: Optional[CacheService] = None,
) -> tuple[list[dict], dict]:
    """
    Fetch records from byTrade endpoint (richer fields).
    Falls back to summaryByTrade if byTrade returns HTTP 404/500/503.
    Returns (records, metadata) where metadata includes {"endpoint_used": "byTrade"|"summaryByTrade", "fallback": bool}.
    """
```

**New method: `get_by_trade_and_set()`**

Same pattern for the set-filtered variant:

```python
async def get_by_trade_and_set(
    self,
    project_id: int,
    trade: str,
    set_ids: list[Union[int, str]],
    cache_service: Optional[CacheService] = None,
) -> tuple[list[dict], list[str], dict]:
    """
    Fetch records from byTradeAndSet endpoint.
    Falls back to summaryByTradeAndSet on failure.
    Returns (records, set_names, metadata).
    """
```

**Fallback logic (shared helper):**

```python
async def _fetch_with_fallback(
    self,
    primary_path: str,
    fallback_path: str,
    primary_label: str,
    fallback_label: str,
    params: dict,
) -> tuple[list[dict], str]:
    """
    Try primary endpoint. On HTTP 404/500/502/503/timeout → retry with fallback.
    Returns (records, endpoint_used_label).
    Logs WARN on fallback.
    """
    try:
        records = await self._fetch_all_pages(primary_path, params)
        return records, primary_label
    except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
        logger.warning("Primary endpoint %s failed (%s), falling back to %s",
                       primary_path, exc, fallback_path)
        records = await self._fetch_all_pages(fallback_path, params)
        return records, fallback_label
```

**Callers pass the correct labels:**
- `get_by_trade()` → `primary_label="byTrade"`, `fallback_label="summaryByTrade"`
- `get_by_trade_and_set()` → `primary_label="byTradeAndSet"`, `fallback_label="summaryByTradeAndSet"`

**Note:** `_fetch_all_pages` is the existing parallel pagination method in `api_client.py`.

**Routing in existing callers:**

`GenerationAgent` and `DataAgent` switch from calling `get_summary_by_trade()` to `get_by_trade()` when `settings.use_new_api` is `True`. When `False`, existing methods are called (zero behavior change).

### 4.3 New API Response Fields

The `byTradeAndSet` endpoint returns these additional fields per record:

```json
{
  "_id": "69a700bd12179a5f1c8263d5",
  "projectId": 7292,
  "setId": 4720,
  "tradeId": 10,
  "drawingId": 318845,
  "drawingName": "A102",
  "drawingTitle": "ARCHITECTURAL SITE PLAN - NEW VET HOSPITAL",
  "s3BucketPath": "ifieldsmart/acsveterinarianhospital2502202613322528/Drawings/pdf2502202613361561",
  "pdfName": "2502202613395178A102ARCHITECTURALSITEPLANNEWVETHOSPITAL1-1",
  "text": "MATCH EXISTING SIDEWALK. RE; CIVIL",
  "x": 3743,
  "y": 738,
  "width": 144,
  "height": 69,
  "csi_division": ["03 - Concrete", "31 - Earthwork"],
  "trades": ["Concrete", "Civil"]
}
```

**No changes to `_extract_list()`** — it already passes through all fields without filtering.

---

## 5. Stream B: Source Reference Index

### 5.1 New File: `services/source_index.py`

A pure-Python service (no LLM) that builds a source reference mapping from deduplicated records.

```python
"""
services/source_index.py — Builds source reference index from API records.

Extracts drawingId, s3BucketPath, pdfName, coordinates from raw API records.
Used by document generators for hyperlinks and traceability tables.
"""

import logging
import time
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import quote

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Allowlisted S3 path prefixes (security: prevent path traversal)
_ALLOWED_S3_PREFIXES = ("ifieldsmart/", "agentic-ai-production/")

# Sentinel: coordinates (None, None) = unknown; (0, 0) = valid top-left
_COORD_SENTINEL = None


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Immutable source reference for a single drawing."""
    drawing_id: int
    drawing_name: str
    drawing_title: str
    s3_url: str
    pdf_name: str
    x: int | None      # None = unknown, 0 = valid top-left
    y: int | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceIndexBuilder:
    """Builds a source index from deduplicated API records."""

    def build(self, records: list[dict]) -> tuple[dict[str, SourceReference], dict]:
        """
        Build {drawingName → SourceReference} from raw records.
        Returns (source_index, build_metadata).

        Algorithm:
        1. Iterate deduplicated records
        2. For each record with a non-empty drawingName:
           a. Skip if drawingName already in index (first-wins dedup)
           b. Extract s3BucketPath and pdfName
           c. Sanitize S3 path (reject traversal, validate prefix)
           d. If valid: build S3 URL, validate coordinates, create SourceReference
           e. If invalid: log warning, skip this record (may be recovered later)
        3. Run sibling recovery pass (_recover_missing_sources)
        4. Return index + metadata (total, missing, recovered, build_ms)
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

        # Recovery pass: fill gaps from sibling records
        pre_recovery = len(index)
        index = self._recover_missing_sources(records, index)
        recovered = len(index) - pre_recovery

        build_ms = int((time.perf_counter() - start) * 1000)
        if warnings:
            logger.warning("Missing source fields for %d drawings: %s",
                           len(warnings), warnings[:10])

        metadata = {
            "drawings_total": len(index),
            "drawings_missing": len(warnings) - recovered,
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
        """Construct direct S3 URL from path + PDF name."""
        bucket = settings.s3_bucket_name
        pattern = settings.s3_pdf_url_pattern
        return pattern.format(bucket=bucket, path=s3_path, name=pdf_name)

    def _validate_coordinates(self, record: dict) -> tuple[int | None, int | None, int | None, int | None]:
        """
        Extract and validate x, y, width, height.
        Returns None for each coordinate that is missing or non-integer.
        (0, 0) is a VALID position (top-left corner), not treated as absent.
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
```

### 5.2 Source Index Build Timing

**Sequencing:** Dedup happens inside `APIClient._fetch_all_pages()` (by `_id`). The deduplicated records are returned to `DataAgent.prepare_context()`. The source index build runs **after** records are fetched and deduped, **in parallel with** context text assembly:

```python
# In data_agent.py prepare_context():
# Step 1: Fetch + dedup (sequential — must complete first)
records, metadata = await api_client.get_by_trade(project_id, trade)

# Step 2: Context build + source index build (parallel — both read from records)
context_task = asyncio.create_task(
    asyncio.to_thread(context_builder.build, records, trade, ...)
)
source_index_task = asyncio.create_task(
    asyncio.to_thread(source_index_builder.build, records)
)
context, stats = await context_task
source_index, source_meta = await source_index_task
```

Build time logged in `token_log["source_index_build_ms"]`.

### 5.3 Missing Source Recovery (Backpropagation)

Per user requirement, missing source fields must be **actively resolved**, not just warned about.

Recovery strategy (applied during source index build):

1. **Primary extraction**: Get `s3BucketPath` and `pdfName` from the first record per drawingName
2. **Sibling lookup** (backpropagation): If a drawing's first record lacks source fields, scan ALL other records with the same `drawingName` — a sibling may have the S3 path
3. **Final fallback**: If all siblings also lack source fields, log structured warning and skip hyperlink

```python
def _recover_missing_sources(
    self,
    records: list[dict],
    index: dict[str, SourceReference],
) -> dict[str, SourceReference]:
    """
    Backpropagation pass: fill gaps in source index from sibling records.
    A sibling = another record with the same drawingName that has source fields.
    Returns a NEW dict (does not mutate input).
    """
    # Group all records by drawingName
    by_drawing: dict[str, list[dict]] = {}
    for rec in records:
        dn = (rec.get("drawingName") or "").strip()
        if dn:
            by_drawing.setdefault(dn, []).append(rec)

    # Build recovered entries separately (immutability)
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
                    break  # first valid sibling wins

    # Return new merged dict (no mutation of original)
    return {**index, **recovered}
```

---

## 6. Stream C: Document Enrichment

### 6.1 Hyperlinks in Word Documents

Both `document_generator.py` and `exhibit_document_generator.py` receive the `source_index` dict.

**Standard document generator signature change (`document_generator.py`):**

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
    source_index: dict[str, "SourceReference"] = None,  # NEW
) -> GeneratedDocument:
```

**Exhibit document generator signature change (`exhibit_document_generator.py`):**

Note: exhibit generator has a DIFFERENT parameter order/set than standard generator.

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
    source_index: dict[str, "SourceReference"] = None,  # NEW
) -> GeneratedDocument:
```

**Hyperlink injection in `_parse_and_add_content()`:**

When a heading or text contains a drawing name that exists in `source_index`, wrap it in a Word hyperlink pointing to the S3 URL:

```python
def _add_hyperlink(self, paragraph, url: str, text: str, color: str = "0563C1"):
    """Add a clickable hyperlink to a Word paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
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
```

### 6.2 Traceability Table (All Document Types)

Appended at the end of every generated document:

```
┌──────────────────────────────────────────────────────────────────────┐
│  SOURCE REFERENCE TABLE                                              │
├──────────────┬─────────────────────────┬─────────────┬──────────────┤
│ Drawing Name │ Drawing Title           │ PDF Link    │ Coordinates  │
├──────────────┼─────────────────────────┼─────────────┼──────────────┤
│ A102 (link)  │ ARCH SITE PLAN - VET    │ View PDF ↗  │ (3743, 738)  │
│ E-101 (link) │ ELECTRICAL FLOOR PLAN   │ View PDF ↗  │ (1200, 450)  │
│ ...          │ ...                     │ ...         │ ...          │
└──────────────┴─────────────────────────┴─────────────┴──────────────┘
```

Implementation in `_add_traceability_table()`:

```python
def _add_traceability_table(
    self, doc: Document, source_index: dict[str, "SourceReference"]
):
    """Append a source reference traceability table to the document."""
    if not source_index:
        return

    doc.add_page_break()
    heading = doc.add_heading("Source Reference Table", level=2)

    table = doc.add_table(rows=1, cols=4)
    try:
        table.style = "Light Grid Accent 1"
    except KeyError:
        table.style = "Table Grid"  # fallback for default template
    headers = ["Drawing Name", "Drawing Title", "PDF Link", "Coordinates"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h

    for ref in sorted(source_index.values(), key=lambda r: r.drawing_name):
        row = table.add_row().cells
        # Drawing name cell with hyperlink
        p = row[0].paragraphs[0]
        if ref.s3_url:
            self._add_hyperlink(p, ref.s3_url, ref.drawing_name)
        else:
            p.text = ref.drawing_name
        row[1].text = ref.drawing_title
        # PDF link cell
        p2 = row[2].paragraphs[0]
        if ref.s3_url:
            self._add_hyperlink(p2, ref.s3_url, "View PDF")
        else:
            p2.text = "N/A"
        # Coordinates — None = unknown, 0 = valid (top-left corner)
        if ref.x is not None and ref.y is not None:
            row[3].text = f"({ref.x}, {ref.y}) {ref.width}x{ref.height}"
        else:
            row[3].text = "—"
```

---

## 7. Stream D: UI Integration

### 7.1 ChatResponse Schema Changes (`models/schemas.py`)

New fields (all optional with defaults — zero breaking changes):

```python
class ChatResponse(BaseModel):
    # ... existing fields unchanged ...

    # NEW: Source references for hyperlinks
    source_references: dict[str, dict] = Field(
        default_factory=dict,
        description="Map of drawingName → {drawing_id, s3_url, pdf_name, x, y, width, height}",
    )
    # NEW: Which API endpoint was used
    api_version: str = Field(
        "",
        description="API endpoint used: 'byTrade', 'byTradeAndSet', 'summaryByTrade' (fallback)",
    )
    # NEW: Non-blocking warnings (degraded source refs, fallback triggered, etc.)
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings: missing sources, fallback alerts, etc.",
    )
```

### 7.2 New API Endpoint: Raw Data (`routers/projects.py`)

**Note:** Placed in `routers/projects.py` (prefix `/api/projects`), NOT `routers/chat.py`, to avoid double `/api/api` prefix and because this is project-scoped data.

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
    Returns all fields from byTradeAndSet endpoint.
    Paginated: skip/limit for large datasets (11K+ records).

    Caching: uses existing CacheService (5-min TTL on API data) so repeated
    pagination calls hit cache instead of re-fetching all records from upstream.
    """
    api_client: APIClient = request.app.state.api_client
    cache_service: CacheService = request.app.state.cache_service

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

### 7.3 HealthResponse Enhancement (`models/schemas.py`)

```python
class HealthResponse(BaseModel):
    status: str = "ok"
    redis: str = "unknown"
    openai: str = "unknown"
    new_api: str = "unknown"     # NEW: "ok" | "degraded (using fallback)" | "disabled"
    version: str = ""
```

**Health check handler** (in `main.py` or `routers/chat.py`, wherever `GET /health` is defined):

```python
# Populate new_api field in health check:
if not settings.use_new_api:
    new_api_status = "disabled"
else:
    try:
        # Quick probe: fetch 1 record from byTrade to verify endpoint is up
        test_resp = await api_client._http.get(
            f"{settings.api_base_url}{settings.by_trade_path}",
            params={"projectId": 7292, "trade": "Civil", "skip": 0, "limit": 1},
            timeout=5,
        )
        new_api_status = "ok" if test_resp.status_code == 200 else "degraded (using fallback)"
    except Exception:
        new_api_status = "degraded (using fallback)"
```

### 7.4 Streamlit UI Changes (`scope-gap-ui/`)

**7.4.1 Raw API Data Expander (below chat response)**

In the chat page, after each assistant message:

```python
with st.expander("📄 Raw API Data", expanded=False):
    if raw_records:
        # Column visibility toggle
        all_cols = list(raw_records[0].keys()) if raw_records else []
        visible_cols = st.multiselect(
            "Visible columns", all_cols, default=all_cols, key=f"cols_{msg_id}"
        )
        # Searchable, sortable dataframe
        import pandas as pd
        df = pd.DataFrame(raw_records)[visible_cols]
        st.dataframe(df, use_container_width=True, height=400)
        # CSV export
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, "raw_data.csv", "text/csv")
    else:
        st.info("No raw data available for this response.")
```

**7.4.2 Source Reference Panel**

Collapsible sidebar panel showing all source drawings with clickable links:

```python
with st.expander("🔗 Source References", expanded=True):
    if source_refs:
        for name, ref in sorted(source_refs.items()):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{name}** — {ref.get('drawing_title', '')}")
            with col2:
                if ref.get("s3_url"):
                    st.markdown(f"[Open PDF]({ref['s3_url']})")
                else:
                    st.caption("No PDF link")
    else:
        st.info("Source references not available.")
```

**7.4.3 Fallback Alert Banner**

Displayed immediately when `api_version` indicates fallback or `warnings` is non-empty:

```python
if response.get("warnings"):
    for w in response["warnings"]:
        st.warning(w)

if response.get("api_version", "").startswith("summary"):
    st.error("⚠️ Using fallback API — source references may be unavailable. "
             "Contact support if this persists.")
```

---

## 8. Pipeline Integration (`agents/generation_agent.py`)

### 8.1 Modified Pipeline Flow

```
Phase 1 (parallel, ~50ms):  — UNCHANGED
  ├── SessionService.get_or_create()
  ├── CacheService.get(pre_cache_key)
  └── SQLService.get_project_name()

Phase 2 (parallel, ~200ms):  — MODIFIED
  ├── IntentAgent.detect_sync()
  ├── DataAgent.prepare_context():
  │     ├── APIClient.get_by_trade()           ◄── NEW: uses new endpoint
  │     ├── ContextBuilder.build()              (unchanged, uses text/drawingName/csi only)
  │     └── SourceIndexBuilder.build(records)   ◄── NEW: parallel with context build
  ├── IntentAgent.detect()
  └── CacheService.get(prelim_cache_key)

LLM Generation (~2000ms):  — UNCHANGED
  └── OpenAI chat.completions.create()

Post-LLM (parallel, ~500ms):  — MODIFIED
  ├── HallucinationGuard.check()
  ├── DocumentGenerator.generate(source_index=source_index)  ◄── NEW: passes source_index
  └── Follow-up questions

Response assembly:  — MODIFIED
  ├── ChatResponse.source_references = source_index.to_dict()  ◄── NEW
  ├── ChatResponse.api_version = metadata["endpoint_used"]      ◄── NEW
  ├── ChatResponse.warnings = collected_warnings                 ◄── NEW
  └── Persist (session + cache)
```

### 8.2 Warning Collection

Warnings are collected throughout the pipeline and added to the response:

```python
warnings: list[str] = []

# After API call
if metadata.get("fallback"):
    warnings.append(
        "Using fallback API endpoint — source PDF links may be unavailable."
    )

# After source index build
missing = [dn for dn in all_drawing_names if dn not in source_index]
if missing:
    warnings.append(
        f"Source references unavailable for {len(missing)} drawings: "
        f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
    )
```

---

## 9. New .env Variables

```bash
# ── API Migration (v4) ───────────────────────────────────
USE_NEW_API=true                    # Feature flag: true = byTrade endpoints, false = summaryByTrade
S3_PDF_URL_PATTERN=https://{bucket}.s3.amazonaws.com/{path}/{name}.pdf
SOURCE_REF_ENABLED=true             # Kill switch for source reference generation
```

**Rollback procedure:**
1. Set `USE_NEW_API=false` in `.env`
2. `systemctl restart construction-agent`
3. Agent reverts to `summaryByTrade` — all other functionality unchanged
4. Total rollback time: <30 seconds

---

## 10. File Inventory

### New Files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `services/source_index.py` | Source reference index builder + validator + sanitizer | ~180 |
| `tests/test_source_index.py` | Unit tests for source index builder | ~250 |
| `tests/test_api_migration.py` | Integration tests for endpoint fallback | ~150 |
| `tests/test_document_hyperlinks.py` | Tests for Word hyperlinks + traceability table | ~200 |

### Modified Files

| File | Change | Impact |
|------|--------|--------|
| `config.py` | Add 3 new settings (`use_new_api`, `s3_pdf_url_pattern`, `source_ref_enabled`) | Low |
| `models/schemas.py` | Add `source_references`, `api_version`, `warnings` to ChatResponse; add `new_api` to HealthResponse | Low |
| `services/api_client.py` | Add `get_by_trade()`, `get_by_trade_and_set()`, `_fetch_with_fallback()` | Medium |
| `services/document_generator.py` | Add `source_index` param, `_add_hyperlink()`, `_add_traceability_table()` | Medium |
| `services/exhibit_document_generator.py` | Same as document_generator.py | Medium |
| `agents/generation_agent.py` | Wire source index build, pass to doc generators, collect warnings | Medium |
| `agents/data_agent.py` | Switch API call routing based on `use_new_api` flag | Low |
| `routers/projects.py` | Add `GET /api/projects/{id}/raw-data` endpoint | Low |
| `main.py` | Initialize `SourceIndexBuilder` in lifespan, attach to `app.state` | Low |
| `scope-gap-ui/components/chat.py` | Add raw data expander + fallback banner | Medium |
| `scope-gap-ui/components/reference_panel.py` | Add source reference links panel | Medium |
| `scope-gap-ui/api/client.py` | Add `get_raw_data()` method | Low |

### Unchanged Files

- `services/context_builder.py` — still uses only text/drawingName/drawingTitle/csi (no source fields)
- `services/sql_service.py` — already complete
- `services/cache_service.py` — existing semantic caching works with new fields
- `services/session_service.py` — no changes
- `agents/intent_agent.py` — no changes
- `scope_pipeline/` — separate system, no changes in this spec

---

## 11. Testing Strategy

**Target: 90% coverage on new code.**

### Unit Tests (`tests/test_source_index.py`)

| Test | Description |
|------|-------------|
| `test_build_from_valid_records` | 10 records with all fields → 10 SourceReferences |
| `test_build_with_missing_s3_path` | Records without s3BucketPath → skipped with warning |
| `test_build_with_missing_pdf_name` | Records without pdfName → skipped with warning |
| `test_sibling_recovery` | Record A missing source, Record B (same drawing) has source → A recovered |
| `test_path_traversal_blocked` | `s3BucketPath: "../../../etc/passwd"` → sanitized out |
| `test_invalid_prefix_blocked` | `s3BucketPath: "malicious/path"` → rejected |
| `test_coordinate_validation` | Negative/non-integer coords → default to 0 |
| `test_empty_records` | Empty list → empty index |
| `test_dedup_by_drawing_name` | Multiple records same drawingName → single reference (first wins) |
| `test_url_construction` | Verify S3 URL matches pattern |

### Integration Tests (`tests/test_api_migration.py`)

| Test | Description |
|------|-------------|
| `test_byTrade_success` | Mock byTrade returning 200 → records extracted |
| `test_byTrade_fallback_on_404` | Mock byTrade 404 → summaryByTrade called |
| `test_byTrade_fallback_on_500` | Mock byTrade 500 → summaryByTrade called |
| `test_byTrade_fallback_on_timeout` | Mock byTrade timeout → summaryByTrade called |
| `test_metadata_tracks_endpoint` | Verify metadata["endpoint_used"] is correct |
| `test_feature_flag_false` | `USE_NEW_API=false` → summaryByTrade called directly |
| `test_live_byTradeAndSet` | Live call to project 7292/Civil/4720 → records with source fields |

### Document Tests (`tests/test_document_hyperlinks.py`)

| Test | Description |
|------|-------------|
| `test_hyperlink_in_heading` | Drawing name in heading → clickable hyperlink |
| `test_traceability_table_added` | Source index with 5 entries → 5-row table at end |
| `test_traceability_table_skipped` | Empty source index → no table added |
| `test_document_without_source_index` | `source_index=None` → document generates normally |
| `test_exhibit_document_hyperlinks` | Same tests for exhibit generator |

### E2E Test

| Test | Description |
|------|-------------|
| `test_full_pipeline_with_source_refs` | POST /api/chat → response has `source_references`, `api_version`, document has hyperlinks |
| `test_raw_data_endpoint` | GET /api/projects/7292/raw-data?trade=Civil → returns all records |

---

## 12. Observability

### Structured Log Entries

```json
{"level": "INFO",  "event": "api_endpoint_used",      "endpoint": "byTradeAndSet", "project_id": 7292}
{"level": "INFO",  "event": "source_index_built",      "drawings": 42, "missing": 3, "build_ms": 8}
{"level": "INFO",  "event": "hyperlinks_added",        "count": 28, "document_id": "abc123"}
{"level": "WARN",  "event": "api_fallback_triggered",  "primary": "byTrade", "fallback": "summaryByTrade", "reason": "HTTP 500"}
{"level": "WARN",  "event": "missing_source_fields",   "drawings": ["A102", "A103"], "field": "s3BucketPath"}
```

### Token Log Additions

```python
token_log["steps"]["source_index_build"] = {
    "elapsed_ms": build_ms,
    "drawings_total": len(source_index),
    "drawings_missing": len(missing),
    "recovery_count": recovery_count,
}
```

---

## 13. Backward Compatibility

| Guarantee | Mechanism |
|-----------|-----------|
| Existing `ChatRequest` works unchanged | No new required fields |
| Existing `ChatResponse` fields preserved | New fields have defaults (empty dict, empty string, empty list) |
| Documents generate without source refs | `source_index=None` → no hyperlinks, no traceability table |
| `USE_NEW_API=false` → identical to current behavior | Feature flag routes to existing methods |
| All existing tests pass | Regression suite required before merge |
| Streamlit UI works without changes | New UI elements are additive (expander, panel) |

---

## 14. Dependencies

**Zero new Python packages.** All functionality uses:
- `httpx` (existing) — API calls
- `python-docx` (existing) — Word hyperlinks via OxmlElement
- `urllib.parse` (stdlib) — URL encoding
- `re` (stdlib) — Path sanitization
- `pandas` (existing in Streamlit) — Raw data display

---

## 15. Performance Impact

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| API fetch (11K records) | ~50s | ~50s | 0 (same server, same pagination) |
| Source index build | N/A | ~10ms | +10ms (parallel, hidden by context build) |
| Context build | ~3s | ~3s | 0 (unchanged, no source fields in LLM context) |
| LLM generation | ~2.4min | ~2.4min | 0 (unchanged prompt, same token budget) |
| Document generation | ~200ms | ~250ms | +50ms (hyperlinks + table) |
| **Total pipeline** | **~4min** | **~4min** | **<100ms additional** |

---

## 16. Security

| Threat | Mitigation |
|--------|------------|
| S3 path traversal | `_sanitize_s3_path()`: reject `../`, allowlist prefixes |
| Malicious PDF names | URL-encode all special characters via `urllib.parse.quote()` |
| Raw data exposure | Internal tool, no PII in drawing metadata; Phase 10 auth adds access control |
| SQL injection | Already parameterized in `sql_service.py` |
| S3 bucket access | Public for testing; production: transition to presigned URLs or app-gated access |

### Pre-Production S3 Checklist (MUST complete before production deploy)

1. Switch `S3_PDF_URL_PATTERN` from direct URL to presigned URL generation
2. Add `s3_pdf_url_expiry_seconds` config (e.g., 3600 = 1 hour)
3. Update `_build_s3_url()` to call `boto3.client('s3').generate_presigned_url()`
4. Verify S3 bucket policy blocks public access
5. Test: generate document → click hyperlink → PDF opens (presigned URL)
6. Test: wait for expiry → link returns 403 (expected)

**This checklist is a GATE for production deployment. Do not deploy to production with public S3 URLs.**

### Test Coverage Measurement

Use `pytest --cov=services/source_index --cov=tests/ --cov-report=term-missing --cov-branch` targeting 90% on new code. Coverage gate enforced in CI.
