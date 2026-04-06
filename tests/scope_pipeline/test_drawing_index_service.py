"""tests/scope_pipeline/test_drawing_index_service.py"""

import pytest

from scope_pipeline.services.drawing_index_service import (
    DrawingIndexService,
    derive_discipline,
)


# ---------------------------------------------------------------------------
# derive_discipline
# ---------------------------------------------------------------------------


def test_derive_discipline_electrical():
    """Single-char prefix E → ELECTRICAL."""
    assert derive_discipline("E-103") == "ELECTRICAL"


def test_derive_discipline_electrical_no_separator():
    """Prefix match works without separator character."""
    assert derive_discipline("E103") == "ELECTRICAL"


def test_derive_discipline_fire_protection():
    """Two-char prefix FP → FIRE PROTECTION (takes priority over F which has no mapping)."""
    assert derive_discipline("FP-201") == "FIRE PROTECTION"


def test_derive_discipline_fire_alarm():
    """Two-char prefix FA → FIRE ALARM."""
    assert derive_discipline("FA-01") == "FIRE ALARM"


def test_derive_discipline_lighting():
    """Two-char prefix LC → LIGHTING."""
    assert derive_discipline("LC-10") == "LIGHTING"


def test_derive_discipline_interior_design():
    """Two-char prefix ID → INTERIOR DESIGN."""
    assert derive_discipline("ID-05") == "INTERIOR DESIGN"


def test_derive_discipline_structural():
    """Single-char prefix S → STRUCTURAL."""
    assert derive_discipline("S-001") == "STRUCTURAL"


def test_derive_discipline_mechanical():
    """Single-char prefix M → MECHANICAL."""
    assert derive_discipline("M-200") == "MECHANICAL"


def test_derive_discipline_plumbing():
    """Single-char prefix P → PLUMBING."""
    assert derive_discipline("P-300") == "PLUMBING"


def test_derive_discipline_fallback_to_set_trade():
    """Unknown prefix falls back to set_trade when provided."""
    result = derive_discipline("X-999", set_trade="hvac")
    assert result == "HVAC"


def test_derive_discipline_fallback_to_set_trade_strips_whitespace():
    """set_trade is stripped before uppercasing."""
    result = derive_discipline("X-001", set_trade="  plumbing  ")
    assert result == "PLUMBING"


def test_derive_discipline_fallback_to_general():
    """Unknown prefix + no set_trade → GENERAL."""
    assert derive_discipline("X-001") == "GENERAL"


def test_derive_discipline_empty_drawing_name_uses_set_trade():
    """Empty drawing_name uses set_trade fallback."""
    assert derive_discipline("", set_trade="civil") == "CIVIL"


def test_derive_discipline_empty_drawing_name_no_trade():
    """Empty drawing_name and no set_trade → GENERAL."""
    assert derive_discipline("") == "GENERAL"


def test_derive_discipline_two_char_prefix_beats_one_char():
    """FA prefix matches FIRE ALARM, not an 'F'-keyed single-char rule (which doesn't exist)."""
    assert derive_discipline("FA01") == "FIRE ALARM"


# ---------------------------------------------------------------------------
# DrawingIndexService.build_categorized_tree
# ---------------------------------------------------------------------------


def _make_records() -> list[dict]:
    return [
        {
            "drawingName": "E-101",
            "drawingTitle": "Electrical Plan 1",
            "setTrade": "Electrical",
            "source_type": "drawing",
        },
        {
            "drawingName": "E-102",
            "drawingTitle": "Electrical Plan 2",
            "setTrade": "Electrical",
            "source_type": "drawing",
        },
        # Duplicate of E-101 — should be deduped
        {
            "drawingName": "E-101",
            "drawingTitle": "Electrical Plan 1",
            "setTrade": "Electrical",
            "source_type": "drawing",
        },
        {
            "drawingName": "S-001",
            "drawingTitle": "Structural Foundation",
            "setTrade": "Structural",
            "source_type": "drawing",
        },
        {
            "drawingName": "FP-201",
            "drawingTitle": "Fire Sprinkler Layout",
            "setTrade": "Fire Protection",
            "source_type": "drawing",
        },
        {
            "drawingName": "E-SPEC-001",
            "drawingTitle": "Division 26 Spec",
            "setTrade": "Electrical",
            "source_type": "specification",
        },
    ]


def test_build_categorized_tree():
    svc = DrawingIndexService()
    records = _make_records()
    tree = svc.build_categorized_tree(records)

    # Disciplines present
    assert "ELECTRICAL" in tree
    assert "STRUCTURAL" in tree
    assert "FIRE PROTECTION" in tree

    # Dedup: E-101 appears twice in input but once in output
    electrical_drawings = tree["ELECTRICAL"]["drawings"]
    drawing_names = [d["drawing_name"] for d in electrical_drawings]
    assert drawing_names.count("E-101") == 1

    # Both electrical drawings present
    assert "E-102" in drawing_names

    # Spec goes to specs bucket, not drawings
    assert len(tree["ELECTRICAL"]["specs"]) == 1
    assert tree["ELECTRICAL"]["specs"][0]["drawing_name"] == "E-SPEC-001"

    # Non-spec records go to drawings bucket
    assert len(tree["STRUCTURAL"]["drawings"]) == 1
    assert tree["STRUCTURAL"]["specs"] == []


def test_build_categorized_tree_entry_shape():
    """Each entry contains drawing_name, drawing_title, source_type."""
    svc = DrawingIndexService()
    records = [
        {
            "drawingName": "M-100",
            "drawingTitle": "HVAC Roof Plan",
            "setTrade": "Mechanical",
            "source_type": "drawing",
        }
    ]
    tree = svc.build_categorized_tree(records)
    entry = tree["MECHANICAL"]["drawings"][0]
    assert entry["drawing_name"] == "M-100"
    assert entry["drawing_title"] == "HVAC Roof Plan"
    assert entry["source_type"] == "drawing"


def test_build_categorized_tree_empty_input():
    svc = DrawingIndexService()
    assert svc.build_categorized_tree([]) == {}


# ---------------------------------------------------------------------------
# DrawingIndexService.build_drawing_metadata
# ---------------------------------------------------------------------------


def test_build_drawing_metadata():
    svc = DrawingIndexService()
    records = [
        {
            "drawingName": "E-101",
            "drawingTitle": "Power Plan",
            "setName": "Electrical Set A",
            "setTrade": "Electrical",
            "source_type": "drawing",
        },
        # Second record for same drawing_name → increments record_count
        {
            "drawingName": "E-101",
            "drawingTitle": "Power Plan",
            "setName": "Electrical Set A",
            "setTrade": "Electrical",
            "source_type": "drawing",
        },
        {
            "drawingName": "P-300",
            "drawingTitle": "Plumbing Floor Plan",
            "setName": "Plumbing Set B",
            "setTrade": "Plumbing",
            "source_type": "drawing",
        },
    ]
    meta = svc.build_drawing_metadata(records)

    # Keys
    assert "E-101" in meta
    assert "P-300" in meta

    e101 = meta["E-101"]
    assert e101["drawing_name"] == "E-101"
    assert e101["drawing_title"] == "Power Plan"
    assert e101["discipline"] == "ELECTRICAL"
    assert e101["source_type"] == "drawing"
    assert e101["set_name"] == "Electrical Set A"
    assert e101["set_trade"] == "Electrical"
    assert e101["record_count"] == 2

    p300 = meta["P-300"]
    assert p300["discipline"] == "PLUMBING"
    assert p300["record_count"] == 1


def test_build_drawing_metadata_skips_empty_drawing_name():
    """Records with missing drawingName are silently skipped."""
    svc = DrawingIndexService()
    records = [
        {"drawingName": "", "drawingTitle": "No Name", "source_type": "drawing"},
        {"drawingTitle": "Also No Name", "source_type": "drawing"},
        {"drawingName": "A-001", "drawingTitle": "Floor Plan", "source_type": "drawing"},
    ]
    meta = svc.build_drawing_metadata(records)
    assert list(meta.keys()) == ["A-001"]


def test_build_drawing_metadata_empty_input():
    svc = DrawingIndexService()
    assert svc.build_drawing_metadata([]) == {}
