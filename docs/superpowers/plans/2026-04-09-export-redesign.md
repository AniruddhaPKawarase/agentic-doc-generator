# Export Document Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up exported documents (remove internal pipeline details), add project name from SQL, add S3 drawing hyperlinks, and fix 100% data coverage.

**Architecture:** Four independent streams converging in `document_agent.py`. Stream A: export cleanup. Stream B: SQL project name. Stream C: S3 hyperlinks. Stream D: coverage fix. All changes are in `scope_pipeline/` and `services/`.

**Tech Stack:** Python, python-docx, reportlab, pyodbc, boto3, asyncio

**Spec:** `docs/superpowers/specs/2026-04-09-export-redesign-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `scope_pipeline/services/document_agent.py` | Major rewrite | Word/PDF/CSV builders — clean export format |
| `scope_pipeline/orchestrator.py` | Modify | SQL call, S3 mapping, force-extract loop |
| `scope_pipeline/services/data_fetcher.py` | Modify | Extract S3 path mapping from records |
| `scope_pipeline/agents/extraction_agent.py` | Modify | Batch extraction by drawing |
| `scope_pipeline/agents/completeness_agent.py` | Modify | Trade-relevant CSI filter, weight change |
| `scope_pipeline/config.py` | Modify | max_attempts 3 → 5 |
| `services/sql_service.py` | Modify | Add `get_project_display_info()` |
| `tests/scope_pipeline/test_document_agent_v2.py` | Create | Tests for clean exports |
| `tests/scope_pipeline/test_completeness_v2.py` | Create | Tests for CSI filtering + weights |
| `tests/scope_pipeline/test_extraction_batching.py` | Create | Tests for batch extraction |

---

### Task 1: Config — Increase Max Attempts

**Files:**
- Modify: `scope_pipeline/config.py:72`

- [ ] **Step 1: Change default max_attempts from 3 to 5**

In `scope_pipeline/config.py`, line 72, change:

```python
max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "5")),
```

- [ ] **Step 2: Verify config loads correctly**

Run: `cd "C:/Users/ANIRUDDHA ASUS/Downloads/projects/VCS/VCS/PROD_SETUP/construction-intelligence-agent" && python -c "from scope_pipeline.config import get_pipeline_config; c = get_pipeline_config(); print(f'max_attempts={c.max_attempts}')"`

Expected: `max_attempts=5`

- [ ] **Step 3: Commit**

```bash
git add scope_pipeline/config.py
git commit -m "feat: increase scope gap max attempts from 3 to 5"
```

---

### Task 2: Completeness Agent — Trade-Relevant CSI Filtering + Weight Change

**Files:**
- Modify: `scope_pipeline/agents/completeness_agent.py`
- Create: `tests/scope_pipeline/test_completeness_v2.py`

- [ ] **Step 1: Write failing test for trade-relevant CSI filtering**

Create `tests/scope_pipeline/test_completeness_v2.py`:

```python
"""Tests for completeness agent v2 — trade-relevant CSI filtering + new weights."""

import pytest
from unittest.mock import AsyncMock

from scope_pipeline.agents.completeness_agent import CompletenessAgent, TRADE_CSI_PREFIX
from scope_pipeline.models import ScopeItem, ClassifiedItem, MergedResults
from scope_pipeline.services.progress_emitter import ProgressEmitter


def _make_classified(drawing_name: str, csi_code: str, text: str = "test") -> ClassifiedItem:
    return ClassifiedItem(
        text=text,
        drawing_name=drawing_name,
        csi_code=csi_code,
        csi_division="",
        trade="Concrete",
        classification_confidence=0.9,
        classification_reason="test",
    )


def _make_item(drawing_name: str, text: str = "test") -> ScopeItem:
    return ScopeItem(text=text, drawing_name=drawing_name)


class TestTradeRelevantCSI:
    """CSI coverage should only count codes relevant to the trade."""

    def test_concrete_filters_to_03_prefix(self):
        assert "Concrete" in TRADE_CSI_PREFIX
        assert "03" in TRADE_CSI_PREFIX["Concrete"]

    @pytest.mark.asyncio
    async def test_irrelevant_csi_codes_excluded(self):
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        items = [_make_item("A-1")]
        classified = [_make_classified("A-1", "03 30 00")]

        merged = MergedResults(
            items=items,
            classified_items=classified,
            ambiguities=[],
            gotchas=[],
        )

        # Source CSI includes irrelevant codes (Masonry, Plumbing)
        source_csi = {"03 - Concrete", "04 - Masonry", "22 - Plumbing", "03 30 00"}

        result = await agent.run(
            merged,
            emitter,
            source_drawings={"A-1"},
            source_csi=source_csi,
            trade="Concrete",
        )
        report = result.data

        # Should only count 03-prefixed CSI codes, not 04 or 22
        assert report.csi_coverage_pct > 40.0  # Was 25% (1/4), now should be 50%+ (1/2)


class TestNewWeights:
    """Completeness weights: drawing=0.65, csi=0.15, hallucination=0.2."""

    @pytest.mark.asyncio
    async def test_drawing_weight_dominates(self):
        agent = CompletenessAgent()
        emitter = ProgressEmitter()

        items = [_make_item("A-1")]
        classified = [_make_classified("A-1", "03 30 00")]

        merged = MergedResults(
            items=items,
            classified_items=classified,
            ambiguities=[],
            gotchas=[],
        )

        result = await agent.run(
            merged,
            emitter,
            source_drawings={"A-1"},
            source_csi=set(),
            trade="Concrete",
        )
        report = result.data

        # 100% drawing * 0.65 + 100% csi * 0.15 + 100% halluc * 0.2 = 100%
        assert report.overall_pct == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scope_pipeline/test_completeness_v2.py -v`

Expected: FAIL — `TRADE_CSI_PREFIX` not defined, `trade` kwarg not accepted

- [ ] **Step 3: Add TRADE_CSI_PREFIX mapping and modify _execute**

Edit `scope_pipeline/agents/completeness_agent.py`. Replace the entire file content with:

```python
"""
scope_pipeline/agents/completeness_agent.py — Pure Python completeness validation.

NO LLM calls. Measures:
  - Drawing coverage: extracted vs source drawings
  - CSI coverage: extracted vs source CSI codes (filtered to trade-relevant only)
  - Hallucination: items referencing non-existent drawings

Weighted formula: (drawing * 0.65) + (csi * 0.15) + (no_hallucination * 0.2)
"""

from __future__ import annotations

from typing import Any

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import CompletenessReport, MergedResults
from scope_pipeline.services.progress_emitter import ProgressEmitter

# Trade → CSI MasterFormat 2-digit prefixes that are relevant to that trade.
# Only these prefixes are counted for CSI coverage — irrelevant codes are excluded.
TRADE_CSI_PREFIX: dict[str, list[str]] = {
    "Concrete": ["03"],
    "Electrical": ["26", "27"],
    "Plumbing": ["22"],
    "HVAC": ["23"],
    "Structural": ["05"],
    "Masonry": ["04"],
    "Roofing": ["07"],
    "Waterproofing": ["07"],
    "Drywall": ["09"],
    "Painting": ["09"],
    "Glazing": ["08"],
    "Doors": ["08"],
    "Insulation": ["07"],
    "Carpentry": ["06"],
    "Fire Protection": ["21"],
    "Fire Sprinkler": ["21"],
    "Mechanical": ["23"],
    "Sitework": ["31", "32", "33"],
    "Steel": ["05"],
    "Framing": ["06"],
}


def _filter_csi_for_trade(source_csi: set[str], trade: str) -> set[str]:
    """Filter source CSI codes to only those relevant to the given trade.

    If the trade has no mapping, return all codes (no filtering).
    """
    prefixes = TRADE_CSI_PREFIX.get(trade)
    if not prefixes:
        return source_csi

    filtered = set()
    for code in source_csi:
        code_stripped = code.strip()
        for prefix in prefixes:
            # Match "03 - Concrete", "03 30 00", "03" etc.
            if code_stripped.startswith(prefix):
                filtered.add(code)
                break
    return filtered


class CompletenessAgent(BaseAgent):
    name = "completeness"
    requires_llm = False
    max_retries = 1

    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> CompletenessReport:
        merged: MergedResults = input_data
        source_drawings: set[str] = kwargs.get("source_drawings", set())
        source_csi: set[str] = kwargs.get("source_csi", set())
        attempt: int = kwargs.get("attempt", 1)
        threshold: float = kwargs.get("threshold", 95.0)
        trade: str = kwargs.get("trade", "")

        extracted_drawings = {item.drawing_name for item in merged.items}
        missing_drawings = sorted(source_drawings - extracted_drawings)
        drawing_pct = (
            len(extracted_drawings) / len(source_drawings) * 100
            if source_drawings else 100.0
        )

        # Filter CSI codes to trade-relevant only
        relevant_csi = _filter_csi_for_trade(source_csi, trade)

        extracted_csi = {
            item.csi_code
            for item in merged.classified_items
            if item.csi_code
        }
        missing_csi = sorted(relevant_csi - extracted_csi)
        csi_pct = (
            len(extracted_csi & relevant_csi) / len(relevant_csi) * 100
            if relevant_csi else 100.0
        )

        hallucinated = [
            item for item in merged.items
            if source_drawings and item.drawing_name not in source_drawings
        ]

        total_items = max(len(merged.items), 1)
        no_hallucination_pct = (1 - len(hallucinated) / total_items) * 100

        # New weights: drawing coverage matters most
        overall = (
            drawing_pct * 0.65
            + csi_pct * 0.15
            + no_hallucination_pct * 0.2
        )

        report = CompletenessReport(
            drawing_coverage_pct=round(drawing_pct, 1),
            csi_coverage_pct=round(csi_pct, 1),
            hallucination_count=len(hallucinated),
            overall_pct=round(overall, 1),
            missing_drawings=missing_drawings,
            missing_csi_codes=missing_csi,
            hallucinated_items=[h.id for h in hallucinated],
            is_complete=overall >= threshold,
            attempt=attempt,
        )

        emitter.emit("completeness", {
            "attempt": attempt,
            "overall_pct": report.overall_pct,
            "drawing_coverage_pct": report.drawing_coverage_pct,
            "csi_coverage_pct": report.csi_coverage_pct,
            "missing_drawings": report.missing_drawings,
            "hallucination_count": report.hallucination_count,
            "is_complete": report.is_complete,
        })

        return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scope_pipeline/test_completeness_v2.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/agents/completeness_agent.py tests/scope_pipeline/test_completeness_v2.py
git commit -m "feat: trade-relevant CSI filtering + new completeness weights (0.65/0.15/0.2)"
```

---

### Task 3: Extraction Agent — Batch by Drawing

**Files:**
- Modify: `scope_pipeline/agents/extraction_agent.py`
- Create: `tests/scope_pipeline/test_extraction_batching.py`

- [ ] **Step 1: Write failing test for batching**

Create `tests/scope_pipeline/test_extraction_batching.py`:

```python
"""Tests for extraction agent batching by drawing."""

from scope_pipeline.agents.extraction_agent import _group_records_by_drawing, _create_batches


class TestGroupRecordsByDrawing:
    def test_groups_correctly(self):
        records = [
            {"drawing_name": "A-1", "text": "a"},
            {"drawing_name": "A-1", "text": "b"},
            {"drawing_name": "A-2", "text": "c"},
        ]
        grouped = _group_records_by_drawing(records)
        assert len(grouped["A-1"]) == 2
        assert len(grouped["A-2"]) == 1


class TestCreateBatches:
    def test_batches_respect_max_size(self):
        grouped = {"A-1": [{"text": "a"}] * 20, "A-2": [{"text": "b"}] * 15}
        batches = _create_batches(grouped, max_records_per_batch=30)
        assert len(batches) >= 1
        for batch in batches:
            assert len(batch) <= 35  # up to 30 + one full drawing group

    def test_single_drawing_in_one_batch(self):
        grouped = {"A-1": [{"text": "a"}] * 5}
        batches = _create_batches(grouped, max_records_per_batch=30)
        assert len(batches) == 1
        assert len(batches[0]) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scope_pipeline/test_extraction_batching.py -v`

Expected: FAIL — `_group_records_by_drawing` not found

- [ ] **Step 3: Add batching helper functions to extraction_agent.py**

Add these functions at the module level in `scope_pipeline/agents/extraction_agent.py`, before the `ExtractionAgent` class:

```python
def _group_records_by_drawing(records: list[dict]) -> dict[str, list[dict]]:
    """Group extraction records by drawing_name."""
    grouped: dict[str, list[dict]] = {}
    for rec in records:
        name = rec.get("drawing_name", "Unknown")
        grouped.setdefault(name, []).append(rec)
    return grouped


def _create_batches(grouped: dict[str, list[dict]], max_records_per_batch: int = 30) -> list[list[dict]]:
    """Create batches from grouped records, keeping drawings together.

    Each batch has at most max_records_per_batch records, but a single drawing
    group is never split across batches.
    """
    batches: list[list[dict]] = []
    current_batch: list[dict] = []

    for drawing_name in sorted(grouped.keys()):
        drawing_records = grouped[drawing_name]
        if current_batch and len(current_batch) + len(drawing_records) > max_records_per_batch:
            batches.append(current_batch)
            current_batch = []
        current_batch.extend(drawing_records)

    if current_batch:
        batches.append(current_batch)

    return batches
```

- [ ] **Step 4: Modify _execute to use batching**

Replace the `_execute` method body in `ExtractionAgent` (lines 70-116) with:

```python
    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> list[ScopeItem]:
        records = input_data.get("drawing_records", [])
        trade = input_data.get("trade", "")
        drawing_list = input_data.get("drawing_list", [])

        # Group records by drawing and process in batches
        grouped = _group_records_by_drawing(records)
        batches = _create_batches(grouped, max_records_per_batch=30)

        all_items: list[ScopeItem] = []
        for batch_idx, batch in enumerate(batches):
            emitter.emit("agent_progress", {
                "agent": self.name,
                "message": f"Extracting scope from batch {batch_idx + 1}/{len(batches)} "
                           f"({len(batch)} records) for {trade}...",
            })

            context_blocks = []
            for rec in batch:
                name = rec.get("drawing_name", "Unknown")
                title = rec.get("drawing_title", "")
                text = rec.get("text", "")
                header = f"=== DRAWING: {name}"
                if title:
                    header += f" ({title})"
                header += " ==="
                context_blocks.append(f"{header}\n{text}")

            context = "\n\n".join(context_blocks)

            system = SYSTEM_PROMPT.format(
                trade=trade,
                drawing_list=", ".join(drawing_list),
            )

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Extract all {trade} scope items:\n\n{context}"},
                ],
                max_tokens=self._max_tokens,
                temperature=0.3,
            )

            raw = response.choices[0].message.content or ""
            if hasattr(response, "usage") and response.usage:
                self._last_tokens_used = getattr(self, "_last_tokens_used", 0) + response.usage.total_tokens

            batch_items = self._parse_response(raw)
            all_items.extend(batch_items)

        return all_items
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/scope_pipeline/test_extraction_batching.py -v`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add scope_pipeline/agents/extraction_agent.py tests/scope_pipeline/test_extraction_batching.py
git commit -m "feat: batch extraction by drawing (max 30 records per LLM call)"
```

---

### Task 4: Data Fetcher — Extract S3 Path Mapping

**Files:**
- Modify: `scope_pipeline/services/data_fetcher.py`

- [ ] **Step 1: Add S3 path extraction to fetch_records return value**

Edit `scope_pipeline/services/data_fetcher.py`. Add S3 mapping extraction after the existing metadata extraction (after line 68):

```python
        # Extract S3 path mapping: drawing_name -> S3 URL
        drawing_s3_urls: dict[str, str] = {}
        for rec in records:
            dn = rec.get("drawingName", "") or rec.get("drawing_name", "") or rec.get("pdfName", "")
            s3_path = rec.get("s3BucketPath", "")
            pdf_name = rec.get("pdfName", "")
            if dn and s3_path and pdf_name and dn not in drawing_s3_urls:
                drawing_s3_urls[dn] = f"{s3_path}/{pdf_name}"
```

Update the return dict (replace lines 76-80) to include the new field:

```python
        return {
            "records": records,
            "drawing_names": drawing_names,
            "csi_codes": csi_codes,
            "drawing_s3_urls": drawing_s3_urls,
        }
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from scope_pipeline.services.data_fetcher import DataFetcher; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scope_pipeline/services/data_fetcher.py
git commit -m "feat: extract S3 path mapping from drawing records"
```

---

### Task 5: SQL Service — Add get_project_display_info

**Files:**
- Modify: `services/sql_service.py`

- [ ] **Step 1: Add get_project_display_info method**

Add this method to the `SQLService` class in `services/sql_service.py`, after the `get_project_name` method (after line 108):

```python
    async def get_project_display_info(
        self, project_id: int
    ) -> dict[str, str]:
        """Return project name and city for document headers.

        Returns:
            {"name": "SINGH RESIDENCE", "city": "Nashville"}
            Falls back to {"name": "Project {id}", "city": ""} on failure.
        """
        if not self._available or not settings.sql_server_host:
            return {"name": f"Project {project_id}", "city": ""}

        cache_key = f"project_info:{project_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached

        info = await asyncio.to_thread(self._query_project_info_sync, project_id)
        if info["name"] != f"Project {project_id}":
            await self._cache.set(cache_key, info, ttl=settings.cache_ttl_project_name)
        return info

    def _query_project_info_sync(self, project_id: int) -> dict[str, str]:
        """Sync query for project name + city. Called via to_thread."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ProjectName, City FROM Projects WHERE ProjectID = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                name = str(row[0]).strip()
                city = str(row[1]).strip() if row[1] else ""
                return {"name": name, "city": city}
            return {"name": f"Project {project_id}", "city": ""}
        except Exception as exc:
            logger.warning("get_project_display_info failed for %s: %s", project_id, exc)
            self._conn = None
            return {"name": f"Project {project_id}", "city": ""}
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from services.sql_service import SQLService; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/sql_service.py
git commit -m "feat: add get_project_display_info for document headers"
```

---

### Task 6: Orchestrator — SQL Call, S3 Mapping, Force-Extract Loop

**Files:**
- Modify: `scope_pipeline/orchestrator.py`

- [ ] **Step 1: Add SQL service parameter to pipeline constructor**

In `scope_pipeline/orchestrator.py`, add `sql_service` to `__init__` (after line 61, `session_manager`):

```python
        sql_service: Any = None,
```

And store it (after line 73, `self._config = config`):

```python
        self._sql = sql_service
```

- [ ] **Step 2: Fetch project info and S3 mapping at pipeline start**

In the `run` method, after `Step 2: Fetch data` (after line 109, `source_csi`), add:

```python
        # Step 2b: Fetch project display info from SQL
        project_display = {"name": project_name or f"Project {request.project_id}", "city": ""}
        if self._sql:
            try:
                project_display = await self._sql.get_project_display_info(request.project_id)
            except Exception as exc:
                logger.warning("SQL project info failed: %s", exc)

        # Step 2c: Extract S3 URL mapping from fetched records
        drawing_s3_urls: dict[str, str] = fetch_result.get("drawing_s3_urls", {})
```

- [ ] **Step 3: Pass new data to completeness agent**

In the completeness agent call (around line 215-222), add the `trade` kwarg:

```python
            completeness_result = await self._completeness.run(
                merged,
                emitter,
                source_drawings=source_drawings,
                source_csi=source_csi,
                attempt=attempt,
                threshold=threshold,
                trade=request.trade,
            )
```

- [ ] **Step 4: Add force-extract loop after backpropagation**

After `Step 4: Remove hallucinated items` (after line 244, `final_classified`), add:

```python
        # Step 4b: Force-extract missing drawings (guaranteed coverage sweep)
        if completeness_report and completeness_report.missing_drawings:
            force_missing = list(completeness_report.missing_drawings)
            logger.info(
                "Force-extracting %d missing drawings: %s",
                len(force_missing), force_missing,
            )
            for drawing_name in force_missing:
                drawing_records = [
                    r for r in all_records
                    if (r.get("drawingName") or r.get("drawing_name", "")) == drawing_name
                ]
                if not drawing_records:
                    continue

                force_input = {
                    "drawing_records": [
                        {
                            "drawing_name": r.get("drawingName") or r.get("drawing_name", ""),
                            "drawing_title": r.get("drawingTitle") or r.get("drawing_title", ""),
                            "text": r.get("text", ""),
                        }
                        for r in drawing_records
                    ],
                    "trade": request.trade,
                    "drawing_list": sorted(source_drawings),
                }

                try:
                    force_result = await self._extraction.run(force_input, emitter, attempt=attempt_count + 1)
                    force_items = force_result.data
                    total_tokens += force_result.tokens_used

                    for item in force_items:
                        key = (item.drawing_name, item.text)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            final_items.append(item)

                    # Classify forced items
                    force_class = await self._classification.run(force_items, emitter, trade=request.trade)
                    total_tokens += force_class.tokens_used
                    classified_keys = {(c.drawing_name, c.text) for c in final_classified}
                    for item in force_class.data:
                        key = (item.drawing_name, item.text)
                        if key not in classified_keys:
                            classified_keys.add(key)
                            final_classified.append(item)

                except Exception as exc:
                    logger.warning("Force-extract failed for drawing %s: %s", drawing_name, exc)
```

- [ ] **Step 5: Pass new data to document agent**

Replace the `documents: DocumentSet = await self._document.generate_all(...)` call (lines 269-279) with:

```python
        documents: DocumentSet = await self._document.generate_all(
            items=final_classified,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness_report,
            quality=quality_report,
            project_id=request.project_id,
            project_name=project_display.get("name", project_name),
            project_location=project_display.get("city", ""),
            trade=request.trade,
            stats=pipeline_stats,
            drawing_s3_urls=drawing_s3_urls,
        )
```

- [ ] **Step 6: Wire SQL service in main.py**

In `main.py`, find where `ScopeGapPipeline` is constructed and add `sql_service=sql_service`:

```python
    scope_pipe = ScopeGapPipeline(
        extraction_agent=extraction_agent,
        classification_agent=classification_agent,
        ambiguity_agent=ambiguity_agent,
        gotcha_agent=gotcha_agent,
        completeness_agent=completeness_agent,
        quality_agent=quality_agent,
        document_agent=scope_doc_agent,
        data_fetcher=scope_data_fetcher,
        session_manager=scope_session_mgr,
        config=pcfg,
        sql_service=sql_service,
    )
```

- [ ] **Step 7: Commit**

```bash
git add scope_pipeline/orchestrator.py main.py
git commit -m "feat: orchestrator gets SQL project info, S3 mapping, force-extract loop"
```

---

### Task 7: Document Agent — Clean Export Format

This is the largest task. Rewrites Word, PDF, CSV builders.

**Files:**
- Modify: `scope_pipeline/services/document_agent.py`
- Create: `tests/scope_pipeline/test_document_agent_v2.py`

- [ ] **Step 1: Write failing tests for clean Word output**

Create `tests/scope_pipeline/test_document_agent_v2.py`:

```python
"""Tests for document agent v2 — clean export format."""

import os
import json
import csv
import tempfile

import pytest
from docx import Document

from scope_pipeline.services.document_agent import DocumentAgent
from scope_pipeline.models import (
    ClassifiedItem, AmbiguityItem, GotchaItem,
    CompletenessReport, QualityReport, PipelineStats,
)


def _make_item(drawing: str, text: str, csi: str = "03 30 00") -> ClassifiedItem:
    return ClassifiedItem(
        text=text,
        drawing_name=drawing,
        csi_code=csi,
        csi_division="03 - Concrete",
        trade="Concrete",
        classification_confidence=0.9,
        classification_reason="test",
        source_snippet="source text here",
        confidence=0.5,
    )


def _make_completeness() -> CompletenessReport:
    return CompletenessReport(
        drawing_coverage_pct=100.0,
        csi_coverage_pct=100.0,
        hallucination_count=0,
        overall_pct=100.0,
        missing_drawings=[],
        missing_csi_codes=[],
        hallucinated_items=[],
        is_complete=True,
        attempt=1,
    )


def _make_quality() -> QualityReport:
    return QualityReport(
        accuracy_score=0.95,
        corrections=[],
        validated_items=[],
        removed_items=[],
        summary="OK",
    )


def _make_stats() -> PipelineStats:
    return PipelineStats(
        total_ms=1000,
        attempts=1,
        tokens_used=100,
        estimated_cost_usd=0.001,
        per_agent_timing={},
        records_processed=5,
        items_extracted=3,
    )


class TestCleanWordExport:
    def test_no_ambiguities_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = DocumentAgent(docs_dir=tmpdir)
            items = [_make_item("A-1", "Contractor shall install concrete.")]
            ambiguities = [AmbiguityItem(
                scope_text="test", competing_trades=["A", "B"],
                severity="medium", recommendation="fix",
            )]

            path = agent.generate_word_sync(
                os.path.join(tmpdir, "test.docx"),
                items=items,
                ambiguities=ambiguities,
                gotchas=[],
                completeness=_make_completeness(),
                quality=_make_quality(),
                project_id=7276,
                project_name="SINGH RESIDENCE",
                project_location="Nashville, TN",
                trade="Concrete",
                stats=_make_stats(),
                drawing_s3_urls={},
            )

            doc = Document(path)
            all_text = "\n".join(p.text for p in doc.paragraphs)

            assert "Ambiguities" not in all_text
            assert "Gotchas" not in all_text
            assert "Completeness Report" not in all_text
            assert "Generated by" not in all_text
            assert "Confidence" not in all_text
            assert "Source:" not in all_text

    def test_has_project_name_in_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = DocumentAgent(docs_dir=tmpdir)
            items = [_make_item("A-1", "Contractor shall install concrete.")]

            path = agent.generate_word_sync(
                os.path.join(tmpdir, "test.docx"),
                items=items,
                ambiguities=[],
                gotchas=[],
                completeness=_make_completeness(),
                quality=_make_quality(),
                project_id=7276,
                project_name="SINGH RESIDENCE",
                project_location="Nashville, TN",
                trade="Concrete",
                stats=_make_stats(),
                drawing_s3_urls={},
            )

            doc = Document(path)
            all_text = "\n".join(p.text for p in doc.paragraphs)

            assert "SINGH RESIDENCE" in all_text
            assert "SCOPE OF WORK" in all_text
            assert "Nashville" in all_text


class TestCleanCSVExport:
    def test_csv_has_6_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = DocumentAgent(docs_dir=tmpdir)
            items = [_make_item("A-1", "Contractor shall install concrete.")]

            path = agent.generate_csv_sync(
                os.path.join(tmpdir, "test.csv"),
                items=items,
                ambiguities=[],
                gotchas=[],
                completeness=_make_completeness(),
                quality=_make_quality(),
                project_id=7276,
                project_name="SINGH RESIDENCE",
                project_location="",
                trade="Concrete",
                stats=_make_stats(),
                drawing_s3_urls={},
            )

            with open(path) as f:
                reader = csv.reader(f)
                header = next(reader)
                assert header == ["Drawing", "Drawing Title", "Scope Item", "CSI Code", "CSI Division", "Trade"]
                row = next(reader)
                assert len(row) == 6
                assert "Source" not in str(header)
                assert "Confidence" not in str(header)


class TestProfessionalFilename:
    def test_filename_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = DocumentAgent(docs_dir=tmpdir)
            name = agent._build_filename("SINGH RESIDENCE", 7276, "Concrete", "docx")
            assert "7276" in name
            assert "Singh_Residence" in name
            assert "Concrete" in name
            assert "Scope_of_Work" in name
            assert name.endswith(".docx")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/scope_pipeline/test_document_agent_v2.py -v`

Expected: FAIL — `project_location` and `drawing_s3_urls` not accepted, `_build_filename` not found

- [ ] **Step 3: Rewrite document_agent.py**

Replace the entire content of `scope_pipeline/services/document_agent.py` with:

```python
"""
scope_pipeline/services/document_agent.py — Agent 7: Document generation (NO LLM).

v2: Clean export format — no ambiguities/gotchas/completeness/source metadata.
    Adds project name from SQL, S3 drawing hyperlinks, professional filenames.
    JSON export unchanged (full data dump).
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    PipelineStats,
    QualityReport,
)

logger = logging.getLogger(__name__)

_DARK_BLUE = (0, 51, 102)


class DocumentAgent:
    """Generate Word, PDF, CSV, JSON output files from validated pipeline results."""

    def __init__(self, docs_dir: str = "./generated_docs") -> None:
        self._docs_dir = docs_dir
        os.makedirs(self._docs_dir, exist_ok=True)

    @staticmethod
    def _build_filename(project_name: str, project_id: int, trade: str, ext: str) -> str:
        """Build professional filename: 7276_Singh_Residence_Concrete_Scope_of_Work.docx"""
        slug = re.sub(r"[^\w\s-]", "", project_name).strip()
        slug = re.sub(r"\s+", "_", slug).title()
        trade_slug = re.sub(r"[^\w\s-]", "", trade).strip()
        trade_slug = re.sub(r"\s+", "_", trade_slug).title()
        return f"{project_id}_{slug}_{trade_slug}_Scope_of_Work.{ext}"

    async def generate_all(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        project_location: str = "",
        trade: str = "",
        stats: PipelineStats = None,
        drawing_s3_urls: dict[str, str] = None,
    ) -> DocumentSet:
        """Generate all 4 document formats in parallel. Returns DocumentSet."""
        if drawing_s3_urls is None:
            drawing_s3_urls = {}

        word_name = self._build_filename(project_name, project_id, trade, "docx")
        pdf_name = self._build_filename(project_name, project_id, trade, "pdf")
        csv_name = self._build_filename(project_name, project_id, trade, "csv")
        json_name = self._build_filename(project_name, project_id, trade, "json")

        word_path = os.path.join(self._docs_dir, word_name)
        pdf_path = os.path.join(self._docs_dir, pdf_name)
        csv_path = os.path.join(self._docs_dir, csv_name)
        json_path = os.path.join(self._docs_dir, json_name)

        common: dict[str, Any] = dict(
            items=items,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness,
            quality=quality,
            project_id=project_id,
            project_name=project_name,
            project_location=project_location,
            trade=trade,
            stats=stats,
            drawing_s3_urls=drawing_s3_urls,
        )

        results = await asyncio.gather(
            asyncio.to_thread(self.generate_word_sync, word_path, **common),
            asyncio.to_thread(self.generate_pdf_sync, pdf_path, **common),
            asyncio.to_thread(self.generate_csv_sync, csv_path, **common),
            asyncio.to_thread(self.generate_json_sync, json_path, **common),
            return_exceptions=True,
        )

        doc_set = DocumentSet()
        paths = [word_path, pdf_path, csv_path, json_path]
        attrs = ["word_path", "pdf_path", "csv_path", "json_path"]
        for result, path, attr in zip(results, paths, attrs):
            if isinstance(result, Exception):
                logger.error("Document generation failed for %s: %s", attr, result)
            else:
                setattr(doc_set, attr, path)

        return doc_set

    # ------------------------------------------------------------------
    # Word (.docx) — Clean export
    # ------------------------------------------------------------------

    def generate_word_sync(self, path: str, **kwargs: Any) -> str:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        items: list[ClassifiedItem] = kwargs["items"]
        project_id: int = kwargs["project_id"]
        project_name: str = kwargs["project_name"]
        project_location: str = kwargs.get("project_location", "")
        trade: str = kwargs["trade"]
        drawing_s3_urls: dict[str, str] = kwargs.get("drawing_s3_urls", {})

        doc = Document()
        style = doc.styles["Normal"]
        style.font.size = Pt(10)
        style.font.name = "Calibri"

        # --- Title ---
        title = doc.add_heading(f"SCOPE OF WORK \u2014 {trade.upper()}", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            run.font.color.rgb = RGBColor(*_DARK_BLUE)
            run.font.size = Pt(16)

        # --- Project Info ---
        now = datetime.now(timezone.utc).strftime("%B %d, %Y")
        info_lines = [
            f"Project: {project_name} (ID: {project_id})",
        ]
        if project_location:
            info_lines.append(f"Location: {project_location}")
        info_lines.append(f"Date: {now}")

        for line in info_lines:
            p = doc.add_paragraph(line)
            for run in p.runs:
                run.font.color.rgb = RGBColor(102, 102, 102)
                run.font.size = Pt(11)

        doc.add_paragraph("")  # spacer

        # --- Scope Items grouped by drawing ---
        grouped: dict[str, list[ClassifiedItem]] = {}
        for item in items:
            grouped.setdefault(item.drawing_name, []).append(item)

        for drawing_name in sorted(grouped.keys()):
            drawing_items = grouped[drawing_name]
            heading = doc.add_heading(level=2)

            # Add hyperlink if S3 URL available
            s3_key = drawing_s3_urls.get(drawing_name, "")
            if s3_key:
                _add_hyperlink(heading, s3_key, drawing_name)
            else:
                run = heading.add_run(drawing_name)
                run.font.color.rgb = RGBColor(*_DARK_BLUE)

            for item in drawing_items:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(item.text)

        doc.save(path)
        logger.info("Word document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # PDF — Mirrors Word
    # ------------------------------------------------------------------

    def generate_pdf_sync(self, path: str, **kwargs: Any) -> str:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        items: list[ClassifiedItem] = kwargs["items"]
        project_id: int = kwargs["project_id"]
        project_name: str = kwargs["project_name"]
        project_location: str = kwargs.get("project_location", "")
        trade: str = kwargs["trade"]
        drawing_s3_urls: dict[str, str] = kwargs.get("drawing_s3_urls", {})

        pdf_doc = SimpleDocTemplate(path, pagesize=letter)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ScopeTitle", parent=styles["Title"],
            textColor=HexColor("#003366"), fontSize=16,
        )
        heading_style = ParagraphStyle(
            "ScopeHeading", parent=styles["Heading2"],
            textColor=HexColor("#003366"),
        )
        bullet_style = ParagraphStyle(
            "ScopeBullet", parent=styles["Normal"],
            leftIndent=20, bulletIndent=10, spaceBefore=2,
        )

        story: list[Any] = []

        # Title
        story.append(Paragraph(f"SCOPE OF WORK \u2014 {trade.upper()}", title_style))
        story.append(Spacer(1, 12))

        # Project info
        now = datetime.now(timezone.utc).strftime("%B %d, %Y")
        info = f"Project: {project_name} (ID: {project_id})<br/>"
        if project_location:
            info += f"Location: {project_location}<br/>"
        info += f"Date: {now}"
        story.append(Paragraph(info, styles["Normal"]))
        story.append(Spacer(1, 18))

        # Scope items grouped by drawing
        grouped: dict[str, list[ClassifiedItem]] = {}
        for item in items:
            grouped.setdefault(item.drawing_name, []).append(item)

        for drawing_name in sorted(grouped.keys()):
            s3_key = drawing_s3_urls.get(drawing_name, "")
            if s3_key:
                heading_text = f'<a href="{s3_key}" color="#003366">{drawing_name}</a>'
            else:
                heading_text = drawing_name
            story.append(Paragraph(heading_text, heading_style))
            story.append(Spacer(1, 4))

            for item in grouped[drawing_name]:
                story.append(Paragraph(f"\u2022 {item.text}", bullet_style))
                story.append(Spacer(1, 2))

        pdf_doc.build(story)
        logger.info("PDF document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # CSV — 6 columns
    # ------------------------------------------------------------------

    def generate_csv_sync(self, path: str, **kwargs: Any) -> str:
        items: list[ClassifiedItem] = kwargs["items"]

        header = ["Drawing", "Drawing Title", "Scope Item", "CSI Code", "CSI Division", "Trade"]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for item in items:
                writer.writerow([
                    item.drawing_name,
                    item.drawing_title or "",
                    item.text,
                    item.csi_code,
                    item.csi_division,
                    item.trade,
                ])

        logger.info("CSV document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # JSON — Full data dump (UNCHANGED)
    # ------------------------------------------------------------------

    def generate_json_sync(self, path: str, **kwargs: Any) -> str:
        output = {
            "project_id": kwargs["project_id"],
            "project_name": kwargs["project_name"],
            "trade": kwargs["trade"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [item.model_dump() for item in kwargs["items"]],
            "ambiguities": [amb.model_dump() for amb in kwargs["ambiguities"]],
            "gotchas": [gtc.model_dump() for gtc in kwargs["gotchas"]],
            "completeness": kwargs["completeness"].model_dump(),
            "quality": kwargs["quality"].model_dump(),
            "pipeline_stats": kwargs["stats"].model_dump() if kwargs.get("stats") else {},
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("JSON document saved: %s", path)
        return path


def _add_hyperlink(paragraph, url: str, text: str) -> None:
    """Add a clickable hyperlink to a python-docx paragraph."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.shared import RGBColor

    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "003366")
    rPr.append(color)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    new_run.append(rPr)
    new_run.text = text
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scope_pipeline/test_document_agent_v2.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scope_pipeline/services/document_agent.py tests/scope_pipeline/test_document_agent_v2.py
git commit -m "feat: clean export format — no ambiguities/gotchas/completeness, add project name + S3 links"
```

---

### Task 8: Deploy and Verify

**Files:** None (deployment)

- [ ] **Step 1: Run existing test suite to check for regressions**

Run: `python -m pytest tests/ -v --tb=short 2>&1 | tail -30`

Expected: All existing tests pass (or pre-existing failures only)

- [ ] **Step 2: Deploy to sandbox**

```bash
bash scripts/deploy_to_sandbox.sh
```

- [ ] **Step 3: Test health endpoint**

```bash
curl -s http://54.197.189.113:8003/health
```

Expected: `{"status": "ok", ...}`

- [ ] **Step 4: Test pipeline with small trade (Doors = 3 records)**

```bash
curl -s -X POST http://54.197.189.113:8003/api/scope-gap/generate \
  -H "Content-Type: application/json" \
  -d '{"project_id": 7276, "trade": "Doors"}'
```

Verify in response:
- `documents.word_path` contains "Singh_Residence" and "Scope_of_Work"
- `items` array has scope items
- Pipeline completes without error

- [ ] **Step 5: Download and inspect the Word document**

```bash
# Get the file_id from the response documents.word_path
curl -s http://54.197.189.113:8003/api/documents/{file_id}/download -o test_output.docx
```

Open the .docx and verify:
- Title: "SCOPE OF WORK — DOORS"
- Header has "SINGH RESIDENCE (ID: 7276)"
- No ambiguities, gotchas, completeness, or footer sections
- Scope items are clean bullet text (no CSI/confidence/source metadata)

- [ ] **Step 6: Test CSV has 6 columns**

```bash
# Download CSV and check header
curl -s http://54.197.189.113:8003/api/documents/{csv_file_id}/download | head -2
```

Expected: `Drawing,Drawing Title,Scope Item,CSI Code,CSI Division,Trade`

- [ ] **Step 7: Commit deployment verification**

```bash
git add -A
git commit -m "chore: export redesign deployed and verified on sandbox"
```

---

## Task Dependency Graph

```
Task 1 (config) ─────────────────────────────┐
Task 2 (completeness CSI filter) ────────────┤
Task 3 (extraction batching) ────────────────┤
Task 4 (data fetcher S3 mapping) ────────────┼── Task 6 (orchestrator wiring) ── Task 7 (document agent) ── Task 8 (deploy)
Task 5 (SQL service) ───────────────────────┘
```

Tasks 1-5 are independent and can be implemented in parallel. Task 6 depends on 4+5. Task 7 depends on 6. Task 8 depends on all.
