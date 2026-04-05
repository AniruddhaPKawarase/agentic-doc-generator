"""
scope_pipeline/agents/completeness_agent.py — Pure Python completeness validation.

NO LLM calls. Measures:
  - Drawing coverage: extracted vs source drawings
  - CSI coverage: extracted vs source CSI codes
  - Hallucination: items referencing non-existent drawings

Weighted formula: (drawing * 0.5) + (csi * 0.3) + (no_hallucination * 0.2)
"""

from __future__ import annotations

from typing import Any

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import CompletenessReport, MergedResults
from scope_pipeline.services.progress_emitter import ProgressEmitter


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

        extracted_drawings = {item.drawing_name for item in merged.items}
        missing_drawings = sorted(source_drawings - extracted_drawings)
        drawing_pct = (
            len(extracted_drawings) / len(source_drawings) * 100
            if source_drawings else 100.0
        )

        extracted_csi = {
            item.csi_code
            for item in merged.classified_items
            if item.csi_code
        }
        missing_csi = sorted(source_csi - extracted_csi)
        csi_pct = (
            len(extracted_csi) / len(source_csi) * 100
            if source_csi else 100.0
        )

        hallucinated = [
            item for item in merged.items
            if source_drawings and item.drawing_name not in source_drawings
        ]

        total_items = max(len(merged.items), 1)
        no_hallucination_pct = (1 - len(hallucinated) / total_items) * 100

        overall = (
            drawing_pct * 0.5
            + csi_pct * 0.3
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
