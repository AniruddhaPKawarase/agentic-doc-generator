"""
scope_pipeline/orchestrator.py — Pipeline orchestrator with backpropagation.

Wires all 7 agents together: extraction -> (classification | ambiguity | gotcha)
-> completeness -> quality -> document generation.

Supports multi-attempt backpropagation when completeness falls below threshold.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from scope_pipeline.config import PipelineConfig
from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    MergedResults,
    PipelineRun,
    PipelineStats,
    QualityReport,
    ScopeGapRequest,
    ScopeGapResult,
    ScopeItem,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

# Default config values when no PipelineConfig is provided
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_COMPLETENESS_THRESHOLD = 95.0
_COST_PER_TOKEN = 0.000002
_MAX_SESSION_RUNS = 10


class ScopeGapPipeline:
    """Master orchestrator for the 7-agent scope gap extraction pipeline.

    Manages parallel fan-out, backpropagation loop, result merging, and
    session persistence.
    """

    def __init__(
        self,
        extraction_agent: Any,
        classification_agent: Any,
        ambiguity_agent: Any,
        gotcha_agent: Any,
        completeness_agent: Any,
        quality_agent: Any,
        document_agent: Any,
        data_fetcher: Any,
        session_manager: Any,
        config: Optional[PipelineConfig] = None,
        sql_service: Any = None,
    ) -> None:
        self._extraction = extraction_agent
        self._classification = classification_agent
        self._ambiguity = ambiguity_agent
        self._gotcha = gotcha_agent
        self._completeness = completeness_agent
        self._quality = quality_agent
        self._document = document_agent
        self._data_fetcher = data_fetcher
        self._session_mgr = session_manager
        self._config = config
        self._sql = sql_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        request: ScopeGapRequest,
        emitter: ProgressEmitter,
        project_name: str = "",
    ) -> ScopeGapResult:
        """Execute the full pipeline with backpropagation loop."""
        pipeline_start = time.monotonic()
        per_agent_timing: dict[str, int] = {}
        total_tokens = 0

        max_attempts = self._get_max_attempts()
        threshold = self._get_threshold()

        # Step 1: Load or create session
        session = await self._session_mgr.get_or_create(
            project_id=request.project_id,
            trade=request.trade,
            set_ids=request.set_ids,
        )

        # Step 2: Fetch data
        emitter.emit("data_fetch", {"message": "Fetching drawing records..."})
        fetch_result = await self._data_fetcher.fetch_records(
            request.project_id,
            request.trade,
            request.set_ids,
        )
        all_records: list[dict[str, Any]] = fetch_result["records"]
        source_drawings: set[str] = set(fetch_result["drawing_names"])
        source_csi: set[str] = set(fetch_result["csi_codes"])

        # Step 2b: Fetch project display info from SQL
        project_display: dict[str, str] = {
            "name": project_name or f"Project {request.project_id}",
            "city": "",
        }
        if self._sql:
            try:
                project_display = await self._sql.get_project_display_info(request.project_id)
            except Exception as exc:
                logger.warning("SQL project info failed: %s", exc)

        # Step 2c: Extract S3 URL mapping from fetched records
        drawing_s3_urls: dict[str, str] = fetch_result.get("drawing_s3_urls", {})

        # Accumulate across attempts
        all_items: list[ScopeItem] = []
        all_classified: list[ClassifiedItem] = []
        ambiguities: list[AmbiguityItem] = []
        gotchas: list[GotchaItem] = []
        completeness_report: Optional[CompletenessReport] = None
        seen_keys: set[tuple[str, str]] = set()
        attempt_count = 0

        # Step 3: Backpropagation loop
        for attempt in range(1, max_attempts + 1):
            attempt_count = attempt

            # 3a: Build extraction input
            if attempt == 1:
                records_for_extraction = all_records
            else:
                missing = completeness_report.missing_drawings if completeness_report else []
                missing_set = set(missing)
                records_for_extraction = [
                    r for r in all_records
                    if (r.get("drawingName") or r.get("drawing_name", "")) in missing_set
                ]

            # Normalize records for extraction agent
            extraction_input = {
                "drawing_records": [
                    {
                        "drawing_name": r.get("drawingName") or r.get("drawing_name", ""),
                        "drawing_title": r.get("drawingTitle") or r.get("drawing_title", ""),
                        "text": r.get("text", ""),
                    }
                    for r in records_for_extraction
                ],
                "trade": request.trade,
                "drawing_list": sorted(source_drawings),
            }

            # 3b: Run extraction
            extraction_result = await self._extraction.run(
                extraction_input, emitter, attempt=attempt,
            )
            new_items: list[ScopeItem] = extraction_result.data
            total_tokens += extraction_result.tokens_used
            per_agent_timing[f"extraction_attempt_{attempt}"] = extraction_result.elapsed_ms

            # 3c: Merge new items with existing (dedup by drawing_name + text)
            for item in new_items:
                key = (item.drawing_name, item.text)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_items.append(item)

            # 3d: Run classification + ambiguity + gotcha in PARALLEL
            items_for_parallel = list(all_items)

            classification_task = self._classification.run(
                items_for_parallel, emitter,
                attempt=attempt, trade=request.trade,
            )
            ambiguity_task = self._ambiguity.run(
                items_for_parallel, emitter, attempt=attempt,
            )
            gotcha_task = self._gotcha.run(
                items_for_parallel, emitter,
                attempt=attempt, trade=request.trade,
            )

            class_result, amb_result, gotcha_result = await asyncio.gather(
                classification_task, ambiguity_task, gotcha_task,
            )

            total_tokens += class_result.tokens_used
            total_tokens += amb_result.tokens_used
            total_tokens += gotcha_result.tokens_used
            per_agent_timing[f"classification_attempt_{attempt}"] = class_result.elapsed_ms
            per_agent_timing[f"ambiguity_attempt_{attempt}"] = amb_result.elapsed_ms
            per_agent_timing[f"gotcha_attempt_{attempt}"] = gotcha_result.elapsed_ms

            # 3e: Merge classified items (dedup by drawing_name + text)
            new_classified: list[ClassifiedItem] = class_result.data
            classified_keys: set[tuple[str, str]] = {
                (c.drawing_name, c.text) for c in all_classified
            }
            for item in new_classified:
                key = (item.drawing_name, item.text)
                if key not in classified_keys:
                    classified_keys.add(key)
                    all_classified.append(item)

            # 3f: On attempt 1 store ambiguities + gotchas; on retries keep originals
            if attempt == 1:
                ambiguities = list(amb_result.data)
                gotchas = list(gotcha_result.data)

            # 3g: Build MergedResults
            merged = MergedResults(
                items=list(all_items),
                classified_items=list(all_classified),
                ambiguities=list(ambiguities),
                gotchas=list(gotchas),
            )

            # 3h: Run completeness check
            completeness_result = await self._completeness.run(
                merged,
                emitter,
                source_drawings=source_drawings,
                source_csi=source_csi,
                attempt=attempt,
                threshold=threshold,
                trade=request.trade,
            )
            completeness_report = completeness_result.data
            total_tokens += completeness_result.tokens_used
            per_agent_timing[f"completeness_attempt_{attempt}"] = completeness_result.elapsed_ms

            # 3i: If complete, break
            if completeness_report.is_complete:
                break

            # 3j: If not last attempt, emit backpropagation event
            if attempt < max_attempts:
                emitter.emit("backpropagation", {
                    "attempt": attempt,
                    "missing_drawings": completeness_report.missing_drawings,
                    "message": f"Attempt {attempt} incomplete, retrying with targeted extraction...",
                })

        # Step 4: Remove hallucinated items
        hallucinated_ids = set(
            completeness_report.hallucinated_items if completeness_report else []
        )
        final_items = [i for i in all_items if i.id not in hallucinated_ids]
        final_classified = [i for i in all_classified if i.id not in hallucinated_ids]

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
                    force_result = await self._extraction.run(
                        force_input, emitter, attempt=attempt_count + 1,
                    )
                    force_items = force_result.data
                    total_tokens += force_result.tokens_used

                    for item in force_items:
                        key = (item.drawing_name, item.text)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            final_items.append(item)

                    force_class = await self._classification.run(
                        force_items, emitter, trade=request.trade,
                    )
                    total_tokens += force_class.tokens_used
                    classified_keys = {
                        (c.drawing_name, c.text) for c in final_classified
                    }
                    for item in force_class.data:
                        key = (item.drawing_name, item.text)
                        if key not in classified_keys:
                            classified_keys.add(key)
                            final_classified.append(item)

                except Exception as exc:
                    logger.warning(
                        "Force-extract failed for drawing %s: %s", drawing_name, exc,
                    )

        # Step 5: Run quality agent
        final_merged = MergedResults(
            items=final_items,
            classified_items=final_classified,
            ambiguities=list(ambiguities),
            gotchas=list(gotchas),
        )
        quality_result = await self._quality.run(final_merged, emitter)
        quality_report: QualityReport = quality_result.data
        total_tokens += quality_result.tokens_used
        per_agent_timing["quality"] = quality_result.elapsed_ms

        # Step 6: Generate documents
        pipeline_stats = PipelineStats(
            total_ms=int((time.monotonic() - pipeline_start) * 1000),
            attempts=attempt_count,
            tokens_used=total_tokens,
            estimated_cost_usd=round(total_tokens * _COST_PER_TOKEN, 6),
            per_agent_timing=dict(per_agent_timing),
            records_processed=len(all_records),
            items_extracted=len(final_items),
        )

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

        # Step 7 (already built): pipeline stats

        # Step 8: Build ScopeGapResult
        result = ScopeGapResult(
            project_id=request.project_id,
            project_name=project_display.get("name", project_name),
            trade=request.trade,
            items=final_classified,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness_report,
            quality=quality_report,
            documents=documents,
            pipeline_stats=pipeline_stats,
        )

        try:
            from services.audit_logger import log_audit_event
            log_audit_event(
                "pipeline_complete",
                project_id=request.project_id,
                trade=request.trade,
                metadata={"items_count": len(final_items), "tokens_used": total_tokens},
            )
        except Exception:
            pass

        # Step 9: Update session
        run_record = PipelineRun(
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            status="complete" if completeness_report.is_complete else "partial",
            attempts=attempt_count,
            completeness_pct=completeness_report.overall_pct,
            items_count=len(final_classified),
            ambiguities_count=len(ambiguities),
            gotchas_count=len(gotchas),
            token_usage=total_tokens,
            cost_usd=round(total_tokens * _COST_PER_TOKEN, 6),
            documents=documents,
        )
        session.runs.insert(0, run_record)
        session.runs = session.runs[:_MAX_SESSION_RUNS]
        session.latest_result = result
        await self._session_mgr.update(session)

        # Step 10: Emit terminal event
        if completeness_report.is_complete:
            emitter.emit("pipeline_complete", {
                "project_id": request.project_id,
                "trade": request.trade,
                "items_count": len(final_classified),
                "attempts": attempt_count,
                "completeness_pct": completeness_report.overall_pct,
            })
        else:
            emitter.emit("pipeline_partial", {
                "project_id": request.project_id,
                "trade": request.trade,
                "items_count": len(final_classified),
                "attempts": attempt_count,
                "completeness_pct": completeness_report.overall_pct,
                "missing_drawings": completeness_report.missing_drawings,
            })

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_max_attempts(self) -> int:
        if self._config is not None:
            return self._config.max_attempts
        return _DEFAULT_MAX_ATTEMPTS

    def _get_threshold(self) -> float:
        if self._config is not None:
            return self._config.completeness_threshold
        return _DEFAULT_COMPLETENESS_THRESHOLD
