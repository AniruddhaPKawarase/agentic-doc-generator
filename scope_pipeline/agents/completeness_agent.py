"""
scope_pipeline/agents/completeness_agent.py — Pure Python completeness validation.

NO LLM calls. Measures:
  - Drawing coverage: extracted vs source drawings
  - CSI coverage: extracted vs source CSI codes (filtered by trade)
  - Hallucination: items referencing non-existent drawings

Weighted formula: (drawing * 0.65) + (csi * 0.15) + (no_hallucination * 0.2)

When a *trade* kwarg is supplied, CSI coverage is computed against only
the CSI codes whose 2-digit division prefix matches that trade (see
``TRADE_CSI_PREFIX``). If the trade has no mapping, all source codes
are used as before.
"""

from __future__ import annotations

from typing import Any

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import CompletenessReport, MergedResults
from scope_pipeline.services.progress_emitter import ProgressEmitter

# ---------------------------------------------------------------------------
# Trade-to-CSI-division mapping
# ---------------------------------------------------------------------------
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


def _filter_csi_for_trade(
    source_csi: set[str],
    trade: str,
) -> set[str]:
    """Return the subset of *source_csi* relevant to *trade*.

    Each CSI code is expected to start with a 2-digit division prefix
    (e.g. ``"03 30 00"``).  Only codes whose prefix appears in
    ``TRADE_CSI_PREFIX[trade]`` are kept.

    If *trade* is empty or has no mapping, all codes are returned
    unchanged so the calculation falls back to the original behaviour.
    """
    if not trade:
        return set(source_csi)

    prefixes = TRADE_CSI_PREFIX.get(trade)
    if prefixes is None:
        return set(source_csi)

    return {
        code for code in source_csi
        if any(code.lstrip().startswith(p) for p in prefixes)
    }


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
        trade: str = kwargs.get("trade", "")
        attempt: int = kwargs.get("attempt", 1)
        threshold: float = kwargs.get("threshold", 95.0)

        # ----- Drawing coverage -----
        extracted_drawings = {item.drawing_name for item in merged.items}
        missing_drawings = sorted(source_drawings - extracted_drawings)
        drawing_pct = (
            len(extracted_drawings & source_drawings) / len(source_drawings) * 100
            if source_drawings else 100.0
        )

        # ----- CSI coverage (trade-filtered) -----
        extracted_csi = {
            item.csi_code
            for item in merged.classified_items
            if item.csi_code
        }
        relevant_csi = _filter_csi_for_trade(source_csi, trade)
        missing_csi = sorted(relevant_csi - extracted_csi)
        csi_pct = (
            len(extracted_csi & relevant_csi) / len(relevant_csi) * 100
            if relevant_csi else 100.0
        )

        # ----- Hallucination detection -----
        hallucinated = [
            item for item in merged.items
            if source_drawings and item.drawing_name not in source_drawings
        ]

        total_items = max(len(merged.items), 1)
        no_hallucination_pct = (1 - len(hallucinated) / total_items) * 100

        # ----- Weighted overall score -----
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
