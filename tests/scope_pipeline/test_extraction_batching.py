"""
tests/scope_pipeline/test_extraction_batching.py — Tests for extraction batching helpers.

Covers:
  - _group_records_by_drawing correctly groups records
  - _create_batches respects max_records_per_batch
  - A single drawing with many records stays in one batch
"""

from __future__ import annotations

import pytest

from scope_pipeline.agents.extraction_agent import (
    _create_batches,
    _group_records_by_drawing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(drawing_name: str, text: str = "some text") -> dict:
    """Helper to create a minimal drawing record."""
    return {"drawing_name": drawing_name, "text": text}


# ---------------------------------------------------------------------------
# _group_records_by_drawing
# ---------------------------------------------------------------------------

class TestGroupRecordsByDrawing:
    def test_empty_input(self) -> None:
        result = _group_records_by_drawing([])
        assert result == {}

    def test_single_drawing(self) -> None:
        records = [_make_record("E-101"), _make_record("E-101")]
        result = _group_records_by_drawing(records)
        assert list(result.keys()) == ["E-101"]
        assert len(result["E-101"]) == 2

    def test_multiple_drawings(self) -> None:
        records = [
            _make_record("E-101"),
            _make_record("E-102"),
            _make_record("E-101"),
            _make_record("M-201"),
        ]
        result = _group_records_by_drawing(records)
        assert sorted(result.keys()) == ["E-101", "E-102", "M-201"]
        assert len(result["E-101"]) == 2
        assert len(result["E-102"]) == 1
        assert len(result["M-201"]) == 1

    def test_missing_drawing_name_defaults_to_unknown(self) -> None:
        records = [{"text": "no name field"}]
        result = _group_records_by_drawing(records)
        assert "Unknown" in result
        assert len(result["Unknown"]) == 1

    def test_does_not_mutate_input(self) -> None:
        records = [_make_record("A"), _make_record("B")]
        original = [r.copy() for r in records]
        _group_records_by_drawing(records)
        assert records == original


# ---------------------------------------------------------------------------
# _create_batches
# ---------------------------------------------------------------------------

class TestCreateBatches:
    def test_empty_grouped(self) -> None:
        result = _create_batches({})
        assert result == []

    def test_single_drawing_under_limit(self) -> None:
        grouped = {"E-101": [_make_record("E-101") for _ in range(5)]}
        batches = _create_batches(grouped, max_records_per_batch=10)
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_respects_max_records_per_batch(self) -> None:
        grouped = {
            "A-001": [_make_record("A-001") for _ in range(10)],
            "A-002": [_make_record("A-002") for _ in range(10)],
            "A-003": [_make_record("A-003") for _ in range(10)],
        }
        batches = _create_batches(grouped, max_records_per_batch=15)
        # A-001 (10) fits in batch 1. A-002 (10) would push to 20 > 15 -> new batch.
        # A-003 (10) would push batch 2 to 20 > 15 -> new batch.
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) <= 15

    def test_drawings_kept_together(self) -> None:
        """A single drawing with 20 records should not be split across batches."""
        grouped = {"E-501": [_make_record("E-501") for _ in range(20)]}
        batches = _create_batches(grouped, max_records_per_batch=10)
        # Even though 20 > 10, the drawing is kept intact in a single batch
        assert len(batches) == 1
        assert len(batches[0]) == 20

    def test_batches_are_sorted_by_drawing_name(self) -> None:
        grouped = {
            "Z-001": [_make_record("Z-001")],
            "A-001": [_make_record("A-001")],
            "M-001": [_make_record("M-001")],
        }
        batches = _create_batches(grouped, max_records_per_batch=100)
        # All fit in one batch; verify ordering by drawing name
        assert len(batches) == 1
        names = [rec["drawing_name"] for rec in batches[0]]
        assert names == ["A-001", "M-001", "Z-001"]

    def test_two_small_drawings_fit_in_one_batch(self) -> None:
        grouped = {
            "D-001": [_make_record("D-001") for _ in range(5)],
            "D-002": [_make_record("D-002") for _ in range(5)],
        }
        batches = _create_batches(grouped, max_records_per_batch=30)
        assert len(batches) == 1
        assert len(batches[0]) == 10

    def test_exact_boundary_fits_without_new_batch(self) -> None:
        grouped = {
            "A-001": [_make_record("A-001") for _ in range(15)],
            "A-002": [_make_record("A-002") for _ in range(15)],
        }
        batches = _create_batches(grouped, max_records_per_batch=30)
        # 15 + 15 == 30, not > 30, so they fit in one batch
        assert len(batches) == 1
        assert len(batches[0]) == 30

    def test_one_over_boundary_creates_new_batch(self) -> None:
        grouped = {
            "A-001": [_make_record("A-001") for _ in range(15)],
            "A-002": [_make_record("A-002") for _ in range(16)],
        }
        batches = _create_batches(grouped, max_records_per_batch=30)
        # 15 + 16 == 31 > 30, so A-002 goes to a new batch
        assert len(batches) == 2
        assert len(batches[0]) == 15
        assert len(batches[1]) == 16
