"""
Context assembly from summaryByTrade API data.

OPTIMIZATION v2 (2026-03-18) — Fixes hallucination on large datasets:

Root cause: previous implementation used a character-budget estimate
  (budget × 4 chars = 479,500 chars) which dropped ~90% of records for
  11k-record trades. The LLM invented drawing numbers for missing data.

New approach — three-layer compression:

  Layer 1: Group by drawingName + aggressive 50-char dedup fingerprint
    → many records for same drawing collapse to unique notes only

  Layer 2: Per-note truncation (adaptive: 300→200→150→100 chars)
    → each note capped to preserve equipment tags while reducing volume

  Layer 3: Token-precise budget enforcement
    → exact count_tokens() check per compression level
    → adaptive: tries each level until context fits in 85% of budget

CRITICAL: ALL drawing numbers are ALWAYS extracted programmatically
  and returned in stats["all_drawing_numbers"] regardless of context size.
  GenerationAgent injects this list into the system prompt as an authoritative
  anchor — the LLM cannot invent drawing numbers not in this list.

Record schema from summaryByTrade:
  { _id, projectId, setName, setTrade, drawingName, drawingTitle,
    text, csi_division: list[str], trades: list[str] }
"""

import logging
from typing import Any

from config import get_settings
from services.api_client import APIClient
from utils.token_counter import count_tokens, truncate_to_token_budget

logger = logging.getLogger(__name__)
settings = get_settings()

# Adaptive note-truncation levels tried in order until context fits budget.
# Values are max characters per individual note.
_ADAPTIVE_NOTE_LEVELS = [300, 200, 150, 100]


class ContextBuilder:
    """
    Builds a trade-focused context block from summaryByTrade records.

    v2: adaptive note compression ensures ALL drawing numbers are represented
    in context regardless of record volume, eliminating drawing-number hallucination.
    """

    def __init__(self, api_client: APIClient):
        self._api = api_client

    async def build(
        self,
        project_id: int,
        trade: str,
        csi_divisions: list[str],
        user_query: str,
        token_budget: int = None,
    ) -> tuple[str, dict[str, int]]:
        """
        Fetch records and build a structured context string for LLM ingestion.

        Returns:
          context_str — grouped drawing notes block with drawing index
          stats       — record counts, token metrics, and all_drawing_numbers list
        """
        budget = token_budget or settings.max_context_tokens
        stats: dict[str, Any] = {}

        records = await self._api.get_summary_by_trade(project_id, trade)
        stats["total_records"] = len(records)

        if not records:
            context = (
                f"## Project Drawing Notes — Trade: {trade}\n"
                "No drawing notes were found for this trade in the project. "
                "Please verify the trade name or project ID."
            )
            stats["unique_drawings"] = 0
            stats["all_drawing_numbers"] = []
            stats["raw_tokens"] = count_tokens(context)
            stats["compressed_tokens"] = stats["raw_tokens"]
            stats["note_max_chars_used"] = 0
            return context, stats

        grouped = self._group_by_drawing(records)

        # Exclude the sentinel from the authoritative index — these are records
        # where the API returned null/empty drawingName.  They still contribute
        # their text notes to context but must never appear as drawing numbers.
        real_drawing_numbers = sorted(k for k in grouped if k != "__NO_DRAWING__")
        no_dn_count = len(grouped.get("__NO_DRAWING__", []))
        if no_dn_count:
            logger.info(
                "trade=%s: %d records have no drawingName — included in context "
                "but excluded from drawing number index",
                trade, no_dn_count,
            )

        stats["unique_drawings"] = len(real_drawing_numbers)
        stats["all_drawing_numbers"] = real_drawing_numbers
        stats["no_drawing_number_records"] = no_dn_count

        # Use 85% of budget — leave 15% headroom for system prompt and query
        effective_budget = int(budget * 0.85)

        context, note_max_used = self._build_adaptive_context(
            grouped=grouped,
            trade=trade,
            total_records=len(records),
            token_budget=effective_budget,
        )

        raw_tokens = count_tokens(context)
        stats["raw_tokens"] = raw_tokens
        stats["note_max_chars_used"] = note_max_used

        if raw_tokens > budget:
            # Final safety truncation (should rarely be reached after adaptive compression)
            context, compressed_tokens = truncate_to_token_budget(context, budget)
            stats["compressed_tokens"] = compressed_tokens
            logger.warning(
                "Context still over budget after adaptive compression — "
                "hard-truncated %d→%d tokens for trade=%s project=%s",
                raw_tokens, compressed_tokens, trade, project_id,
            )
        else:
            stats["compressed_tokens"] = raw_tokens

        logger.info(
            "Context built: trade=%s records=%d drawings=%d no_dn=%d tokens=%d "
            "note_max=%d%s",
            trade, len(records), len(real_drawing_numbers), no_dn_count,
            stats["compressed_tokens"],
            note_max_used,
            " (adaptive compressed)" if note_max_used < (settings.note_max_chars or 300) else "",
        )
        return context, stats

    # -- Metadata summary (pure-string, no I/O) -----------------------

    async def build_metadata_summary(
        self,
        project_id: int,
        trades: list[str],
        csi_divisions: list[str],
    ) -> str:
        return self.build_metadata_summary_sync(project_id, trades, csi_divisions)

    def build_metadata_summary_sync(
        self,
        project_id: int,
        trades: list[str],
        csi_divisions: list[str],
    ) -> str:
        return f"## Project Metadata\nProject ID: {project_id}\n"

    # -- Internal helpers -----------------------------------------------

    def _build_adaptive_context(
        self,
        grouped: dict[str, list[dict]],
        trade: str,
        total_records: int,
        token_budget: int,
    ) -> tuple[str, int]:
        """
        Try each note_max_chars level until context fits in token_budget.

        Returns (context_str, note_max_chars_used).
        The drawing-number index is always included at the top regardless
        of compression level — this is the hallucination-prevention anchor.
        """
        configured_max = settings.note_max_chars or 300

        # Build levels to try: start at configured value, step down if needed
        levels_to_try = [lvl for lvl in _ADAPTIVE_NOTE_LEVELS if lvl <= configured_max]
        if not levels_to_try:
            levels_to_try = _ADAPTIVE_NOTE_LEVELS
        # Ensure we always try the configured max first
        if configured_max not in levels_to_try:
            levels_to_try = [configured_max] + levels_to_try

        for note_max in levels_to_try:
            context = self._build_context_block(
                grouped=grouped,
                trade=trade,
                total_records=total_records,
                note_max_chars=note_max,
            )
            if count_tokens(context) <= token_budget:
                return context, note_max

        # Return best-effort (smallest level)
        context = self._build_context_block(
            grouped=grouped,
            trade=trade,
            total_records=total_records,
            note_max_chars=_ADAPTIVE_NOTE_LEVELS[-1],
        )
        logger.warning(
            "Context exceeds budget even at note_max=%d chars — "
            "returning best-effort context for trade=%s (%d drawings)",
            _ADAPTIVE_NOTE_LEVELS[-1], trade, len(grouped),
        )
        return context, _ADAPTIVE_NOTE_LEVELS[-1]

    def _build_context_block(
        self,
        grouped: dict[str, list[dict]],
        trade: str,
        total_records: int,
        note_max_chars: int,
    ) -> str:
        """
        Build the full context block for one compression level.

        Structure:
          ## Drawing Number Index  ← programmatic anchor (always present)
          ## Drawing Notes — Trade: ...
          ### Drawing: E-101
            Title: ...
            Source Trade: ...
            CSI: ...
            - note 1 (truncated to note_max_chars)
            - note 2
          ### Drawing: E-102
            ...
        """
        # Separate real drawing numbers from the sentinel group.
        # "__NO_DRAWING__" records are included in context notes but NEVER
        # added to the Drawing Number Index — this prevents "Unknown" from
        # appearing in the LLM's drawing-number fields.
        real_drawing_numbers = sorted(k for k in grouped if k != "__NO_DRAWING__")
        no_dn_recs = grouped.get("__NO_DRAWING__", [])

        # --- Drawing index: compact, always present, used as LLM anchor ---
        index_lines = [
            f"## Drawing Number Index — Trade: {trade}",
            f"## Total: {total_records} records across {len(real_drawing_numbers)} drawings",
            "## Drawing Numbers: " + ", ".join(real_drawing_numbers),
            "",
        ]

        # --- Per-drawing detail blocks ---
        detail_lines: list[str] = [
            f"## Drawing Notes — Trade: {trade}",
            "",
        ]

        for drawing_no in real_drawing_numbers:
            recs = grouped[drawing_no]
            block = self._build_drawing_block(drawing_no, recs, note_max_chars)
            detail_lines.extend(block)

        # --- Notes without an assigned drawing number (excluded from index) ---
        if no_dn_recs:
            detail_lines.append(
                "## Additional Trade Notes (No Drawing Number Assigned — "
                "DO NOT use as drawing number)"
            )
            detail_lines.append("")
            # Reuse _build_drawing_block but suppress the "### Drawing:" header line
            block = self._build_drawing_block("__NO_DRAWING__", no_dn_recs, note_max_chars)
            # block[0] is the header line; skip it and include only the notes
            detail_lines.extend(block[1:])

        return "\n".join(index_lines) + "\n".join(detail_lines)

    @staticmethod
    def _group_by_drawing(records: list[dict[str, Any]]) -> dict[str, list[dict]]:
        """
        Group records by drawingName.

        Records where drawingName is null/empty are grouped under the sentinel
        key "__NO_DRAWING__".  This sentinel is excluded from the Drawing Number
        Index and the authoritative anchor — the LLM never sees it as a valid
        drawing number, preventing "Drawing Number: Unknown" in the output.
        """
        grouped: dict[str, list[dict]] = {}
        for rec in records:
            drawing_name = (rec.get("drawingName") or "").strip()
            key = drawing_name if drawing_name else "__NO_DRAWING__"
            grouped.setdefault(key, []).append(rec)
        return grouped

    def _build_drawing_block(
        self,
        drawing_no: str,
        recs: list[dict[str, Any]],
        note_max_chars: int,
    ) -> list[str]:
        """
        Build context lines for one drawing group.

        Deduplication uses a 50-char prefix fingerprint (v2: was 100-char).
        Notes are truncated to note_max_chars to fit budget.
        """
        lines: list[str] = []

        # Collect unique CSI codes and source trades
        csi_set: set[str] = set()
        source_trades: set[str] = set()
        for r in recs:
            for c in r.get("csi_division") or []:
                if c and isinstance(c, str):
                    csi_set.add(c.strip())
            st = r.get("setTrade", "")
            if st:
                source_trades.add(st.strip())

        if drawing_no == "__NO_DRAWING__":
            lines.append("### Notes (No Drawing Number Assigned)")
        else:
            lines.append(f"### Drawing: {drawing_no}")

        drawing_title = (recs[0].get("drawingTitle") or "").strip()
        if drawing_title and drawing_title not in (drawing_no, "__NO_DRAWING__"):
            lines.append(f"Title: {drawing_title}")

        if source_trades:
            lines.append(f"Source Trade: {', '.join(sorted(source_trades))}")

        if csi_set:
            lines.append(f"CSI: {', '.join(sorted(csi_set))}")

        # Deduplicate notes by configurable prefix fingerprint (v2: 50 chars, was 100)
        dedup_chars = settings.note_dedup_prefix_chars or 50
        seen: set[str] = set()
        for r in recs:
            note = (r.get("text") or "").strip()
            if not note:
                continue
            fingerprint = note[:dedup_chars].lower()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            # Truncate note to fit note_max_chars budget
            if note_max_chars and len(note) > note_max_chars:
                note = note[:note_max_chars].rstrip() + "…"
            lines.append(f"- {note}")

        lines.append("")  # blank line separator between drawings
        return lines
