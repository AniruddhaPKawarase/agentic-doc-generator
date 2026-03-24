"""
tests/excel_loader.py — Reads the Scope Gap Excel file and provides it as
structured context data, mimicking the shape returned by the MongoDB APIs.

Excel columns:
  Project Name | Trade Name | Drawing No | Note | Scope Trades | CSI Division

This module is used by test_scope.py to drive scope generation tests
without a live MongoDB connection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ExcelDataLoader:
    """Loads the Scope Gap Excel file and provides trade-filtered context."""

    DEFAULT_PATH = Path(__file__).parent.parent / "Scope Gap - Electrical.xlsx"

    def __init__(self, excel_path: str | Path | None = None):
        self._path = Path(excel_path) if excel_path else self.DEFAULT_PATH
        self._rows: list[dict[str, Any]] = []
        self._loaded = False

    # ── Public API (mirrors what APIClient returns) ────────────────

    def load(self) -> None:
        """Parse the Excel workbook into memory (call once at startup)."""
        try:
            import openpyxl
        except ImportError:
            raise ImportError("openpyxl is required for the test module. Run: pip install openpyxl")

        if not self._path.exists():
            raise FileNotFoundError(f"Excel file not found: {self._path}")

        wb = openpyxl.load_workbook(str(self._path), read_only=True, data_only=True)
        sheet = wb.worksheets[0]

        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            raise ValueError("Excel file is empty")

        # Identify columns from header row
        headers = [str(h).strip() if h else "" for h in raw_rows[0]]
        col = {name: idx for idx, name in enumerate(headers)}

        for row in raw_rows[1:]:
            if not any(row):
                continue
            record = {
                "project_name": self._cell(row, col, "Project Name"),
                "trade_name": self._cell(row, col, "Trade Name"),
                "drawing_no": self._cell(row, col, "Drawing No"),
                "note": self._cell(row, col, "Note"),
                "scope_trades": self._cell(row, col, "Scope Trades"),
                "csi_division": self._cell(row, col, "CSI Division"),
            }
            if record["note"]:
                self._rows.append(record)

        wb.close()
        self._loaded = True
        logger.info("Loaded %d rows from %s", len(self._rows), self._path.name)

    def get_project_name(self) -> str:
        self._ensure_loaded()
        names = {r["project_name"] for r in self._rows if r["project_name"]}
        return next(iter(names), "Unknown Project")

    def get_unique_trades(self) -> list[str]:
        """All unique values in the Trade Name column."""
        self._ensure_loaded()
        seen: set[str] = set()
        result: list[str] = []
        for row in self._rows:
            t = row["trade_name"]
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return sorted(result)

    def get_scope_trades(self) -> list[str]:
        """All unique scope-trade values across Scope Trades column (comma-split)."""
        self._ensure_loaded()
        seen: set[str] = set()
        result: list[str] = []
        for row in self._rows:
            for t in self._split_multi(row["scope_trades"]):
                if t and t not in seen:
                    seen.add(t)
                    result.append(t)
        return sorted(result)

    def get_unique_csi_divisions(self) -> list[str]:
        """All unique CSI division values."""
        self._ensure_loaded()
        seen: set[str] = set()
        result: list[str] = []
        for row in self._rows:
            for c in self._split_multi(row["csi_division"]):
                if c and c not in seen:
                    seen.add(c)
                    result.append(c)
        return sorted(result)

    def get_drawing_data_for_trade(
        self,
        scope_trade: str,
        drawing_trade_filter: str = "",
    ) -> list[dict[str, Any]]:
        """
        Return rows where scope_trade appears in the Scope Trades column.
        Optionally also filter by Trade Name (drawing_trade_filter).

        Returns records shaped like DrawingRecord — compatible with
        ContextBuilder.group_drawing_records().
        """
        self._ensure_loaded()
        trade_lower = scope_trade.lower().strip()

        results: list[dict[str, Any]] = []
        for row in self._rows:
            scope_trades_lower = [s.lower() for s in self._split_multi(row["scope_trades"])]
            if not any(trade_lower in s for s in scope_trades_lower):
                continue
            if drawing_trade_filter:
                if row["trade_name"].lower() != drawing_trade_filter.lower():
                    continue

            results.append({
                "drawingName": row["drawing_no"],
                "drawingTitle": row["drawing_no"],
                "setTrade": row["trade_name"],
                "trade": row["trade_name"],
                "text": row["note"],
                "csi_division": self._split_multi(row["csi_division"]),
                "scope_trades": self._split_multi(row["scope_trades"]),
                "project_name": row["project_name"],
            })

        return results

    def build_context_block(
        self,
        scope_trade: str,
        user_query: str = "",
        max_rows: int = 400,
    ) -> str:
        """
        Build a structured context string ready for LLM ingestion.

        Groups records by drawing number and formats as:
          ## Drawing: E-101
          Trade: Electrical
          CSI: 26 - Electrical
          - <note text>
          - <note text>
        """
        records = self.get_drawing_data_for_trade(scope_trade)
        if not records:
            return f"No data found for trade: {scope_trade}"

        # Group by drawing number
        grouped: dict[str, list[dict]] = {}
        for rec in records[:max_rows]:
            key = rec["drawingName"] or "Unknown"
            grouped.setdefault(key, []).append(rec)

        project_name = self.get_project_name()
        lines: list[str] = [
            f"## Project: {project_name}",
            f"## Trade Scope: {scope_trade}",
            f"## Total Source Records: {len(records)}",
            "",
        ]

        for drawing_no, recs in sorted(grouped.items()):
            csi_vals = list({c for r in recs for c in r["csi_division"] if c})
            source_trades = list({r["setTrade"] for r in recs if r["setTrade"]})
            lines.append(f"### Drawing: {drawing_no}")
            if source_trades:
                lines.append(f"Source Trade: {', '.join(source_trades)}")
            if csi_vals:
                lines.append(f"CSI: {', '.join(sorted(csi_vals))}")
            for rec in recs:
                note = rec["text"].strip()
                if note:
                    lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines)

    def get_drawing_summary(self, scope_trade: str) -> list[dict[str, Any]]:
        """
        Return a per-drawing summary list for use in document tables:
        [{drawing_no, source_trade, csi, notes: [...]}, ...]
        """
        records = self.get_drawing_data_for_trade(scope_trade)
        grouped: dict[str, dict] = {}
        for rec in records:
            key = rec["drawingName"] or "Unknown"
            if key not in grouped:
                grouped[key] = {
                    "drawing_no": key,
                    "source_trade": rec["setTrade"],
                    "csi": set(),
                    "scope_trades": set(),
                    "notes": [],
                }
            for c in rec["csi_division"]:
                if c:
                    grouped[key]["csi"].add(c)
            for s in rec["scope_trades"]:
                if s:
                    grouped[key]["scope_trades"].add(s)
            note = rec["text"].strip()
            if note:
                grouped[key]["notes"].append(note)

        result = []
        for drawing_no, data in sorted(grouped.items()):
            result.append({
                "drawing_no": drawing_no,
                "source_trade": data["source_trade"],
                "csi": sorted(data["csi"]),
                "scope_trades": sorted(data["scope_trades"]),
                "notes": data["notes"],
            })
        return result

    # ── Internal helpers ───────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    @staticmethod
    def _cell(row: tuple, col_map: dict, key: str) -> str:
        idx = col_map.get(key)
        if idx is None or idx >= len(row):
            return ""
        val = row[idx]
        return str(val).strip() if val is not None else ""

    @staticmethod
    def _split_multi(value: str) -> list[str]:
        """Split a comma-separated cell value, stripping whitespace."""
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]
