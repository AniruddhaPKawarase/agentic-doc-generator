"""
scope_pipeline/services/drawing_index_service.py — Discipline derivation and drawing index.

Provides:
  - derive_discipline(drawing_name, set_trade) -> str
  - DrawingIndexService.build_categorized_tree(records) -> dict
  - DrawingIndexService.build_drawing_metadata(records) -> dict
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 2-char prefixes take priority over 1-char prefixes.
_TWO_CHAR_PREFIXES: dict[str, str] = {
    "FP": "FIRE PROTECTION",
    "FA": "FIRE ALARM",
    "LC": "LIGHTING",
    "ID": "INTERIOR DESIGN",
}

# 1-char prefixes (checked only when no 2-char match).
_ONE_CHAR_PREFIXES: dict[str, str] = {
    "G": "GENERAL",
    "C": "CIVIL",
    "L": "LANDSCAPE",
    "A": "ARCHITECTURAL",
    "S": "STRUCTURAL",
    "M": "MECHANICAL",
    "P": "PLUMBING",
    "E": "ELECTRICAL",
    "T": "TELECOM",
}

_FALLBACK_DISCIPLINE = "GENERAL"


def derive_discipline(
    drawing_name: str,
    set_trade: Optional[str] = None,
) -> str:
    """
    Derive a discipline label from a drawing name.

    Resolution order:
    1. 2-char prefix match (FP, FA, LC, ID)
    2. 1-char prefix match (G, C, L, A, S, M, P, E, T)
    3. set_trade.upper() if provided and non-empty
    4. "GENERAL"

    Args:
        drawing_name: Raw drawing name (e.g. "E-103", "FP-001").
        set_trade: Optional trade label from the record set.

    Returns:
        Uppercase discipline string.
    """
    if drawing_name:
        prefix_two = drawing_name[:2].upper()
        if prefix_two in _TWO_CHAR_PREFIXES:
            return _TWO_CHAR_PREFIXES[prefix_two]

        prefix_one = drawing_name[:1].upper()
        if prefix_one in _ONE_CHAR_PREFIXES:
            return _ONE_CHAR_PREFIXES[prefix_one]

    if set_trade:
        normalized = set_trade.strip()
        if normalized:
            return normalized.upper()

    return _FALLBACK_DISCIPLINE


class DrawingIndexService:
    """Builds categorized trees and metadata indexes from raw drawing records."""

    def build_categorized_tree(self, records: list[dict]) -> dict:
        """
        Build a discipline-keyed tree from raw drawing records.

        Returns:
            {
                "<DISCIPLINE>": {
                    "drawings": [{"drawing_name", "drawing_title", "source_type"}, ...],
                    "specs":    [{"drawing_name", "drawing_title", "source_type"}, ...],
                },
                ...
            }

        Deduplicates entries by drawing_name within each bucket.

        Args:
            records: Raw records with fields drawingName, drawingTitle,
                     setTrade, source_type.
        """
        tree: dict[str, dict[str, list[dict]]] = {}

        # Track seen drawing_names per discipline+bucket to deduplicate.
        seen: dict[tuple[str, str], set[str]] = {}

        for rec in records:
            drawing_name: str = (rec.get("drawingName") or "").strip()
            drawing_title: str = (rec.get("drawingTitle") or "").strip()
            set_trade: str = (rec.get("setTrade") or "").strip()
            source_type: str = (rec.get("source_type") or "drawing").strip().lower()

            discipline = derive_discipline(drawing_name, set_trade)

            # Determine bucket: "drawings" or "specs"
            bucket = "specs" if source_type == "specification" else "drawings"

            if discipline not in tree:
                tree[discipline] = {"drawings": [], "specs": []}
                seen[(discipline, "drawings")] = set()
                seen[(discipline, "specs")] = set()

            key = (discipline, bucket)
            if drawing_name not in seen[key]:
                seen[key].add(drawing_name)
                tree[discipline][bucket].append(
                    {
                        "drawing_name": drawing_name,
                        "drawing_title": drawing_title,
                        "source_type": source_type,
                    }
                )

        logger.debug(
            "build_categorized_tree: %d records → %d disciplines",
            len(records),
            len(tree),
        )
        return tree

    def build_drawing_metadata(self, records: list[dict]) -> dict:
        """
        Build a drawing_name-keyed metadata index from raw drawing records.

        Returns:
            {
                "<drawing_name>": {
                    "drawing_name": str,
                    "drawing_title": str,
                    "discipline": str,
                    "source_type": str,
                    "set_name": str,
                    "set_trade": str,
                    "record_count": int,
                },
                ...
            }

        The first record for a drawing_name wins for non-count fields;
        record_count accumulates across all records for that drawing.

        Args:
            records: Raw records with fields drawingName, drawingTitle,
                     setName, setTrade, source_type.
        """
        metadata: dict[str, dict] = {}

        for rec in records:
            drawing_name: str = (rec.get("drawingName") or "").strip()
            if not drawing_name:
                continue

            if drawing_name not in metadata:
                drawing_title: str = (rec.get("drawingTitle") or "").strip()
                set_name: str = (rec.get("setName") or "").strip()
                set_trade: str = (rec.get("setTrade") or "").strip()
                source_type: str = (rec.get("source_type") or "drawing").strip().lower()
                discipline = derive_discipline(drawing_name, set_trade)

                metadata[drawing_name] = {
                    "drawing_name": drawing_name,
                    "drawing_title": drawing_title,
                    "discipline": discipline,
                    "source_type": source_type,
                    "set_name": set_name,
                    "set_trade": set_trade,
                    "record_count": 1,
                }
            else:
                metadata[drawing_name]["record_count"] += 1

        logger.debug(
            "build_drawing_metadata: %d records → %d unique drawings",
            len(records),
            len(metadata),
        )
        return metadata
