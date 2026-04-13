"""Unit tests for services/source_index.py — SourceIndexBuilder."""

import pytest
from unittest.mock import patch


def _make_record(
    drawing_name: str = "A102",
    s3_path: str = "ifieldsmart/proj123/Drawings/pdf456",
    pdf_name: str = "pdfA102Plan1-1",
    drawing_id: int = 318845,
    drawing_title: str = "ARCH SITE PLAN",
    x: int = 3743,
    y: int = 738,
    width: int = 144,
    height: int = 69,
    **overrides,
) -> dict:
    rec = {
        "_id": f"id_{drawing_name}",
        "projectId": 7292,
        "drawingId": drawing_id,
        "drawingName": drawing_name,
        "drawingTitle": drawing_title,
        "s3BucketPath": s3_path,
        "pdfName": pdf_name,
        "text": "Some note text",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "csi_division": ["03 - Concrete"],
        "trades": ["Civil"],
    }
    rec.update(overrides)
    return rec


class TestSourceIndexBuilder:
    def test_build_from_valid_records(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(drawing_name=f"D-{i}") for i in range(10)]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)
        assert len(index) == 10
        assert meta["drawings_total"] == 10
        assert meta["drawings_missing"] == 0
        assert meta["build_ms"] >= 0
        ref = index["D-0"]
        assert ref.drawing_id == 318845
        assert ref.drawing_name == "D-0"
        assert "ifieldsmart/proj123" in ref.s3_url
        assert ref.pdf_name == "pdfA102Plan1-1"

    def test_build_with_missing_s3_path(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(s3_path="")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)
        assert len(index) == 0
        assert meta["drawings_missing"] == 1

    def test_build_with_missing_pdf_name(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(pdf_name="")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)
        assert len(index) == 0
        assert meta["drawings_missing"] == 1

    def test_sibling_recovery(self):
        from services.source_index import SourceIndexBuilder
        rec_a = _make_record(drawing_name="X-1", s3_path="", pdf_name="")
        rec_b = _make_record(
            drawing_name="X-1",
            s3_path="ifieldsmart/proj/Drawings/pdf",
            pdf_name="pdfX1Plan",
            drawing_id=999,
        )
        rec_b["_id"] = "id_X-1_b"
        builder = SourceIndexBuilder()
        index, meta = builder.build([rec_a, rec_b])
        assert "X-1" in index
        assert index["X-1"].drawing_id == 999
        # new build() groups all records per drawing; recovery is built-in (no separate count)
        assert meta["drawings_total"] == 1

    def test_path_traversal_blocked(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(s3_path="../../../etc/passwd")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)
        assert len(index) == 0

    def test_invalid_prefix_blocked(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(s3_path="malicious/bucket/path")]
        builder = SourceIndexBuilder()
        index, meta = builder.build(records)
        assert len(index) == 0

    def test_coordinate_validation_negative(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(x=-5, y=-10, width=-1, height=-1)]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)
        ref = index["A102"]
        assert ref.x is None
        assert ref.y is None
        assert ref.width is None
        assert ref.height is None

    def test_coordinate_zero_is_valid(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(x=0, y=0, width=100, height=50)]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)
        ref = index["A102"]
        assert ref.x == 0
        assert ref.y == 0
        assert ref.width == 100
        assert ref.height == 50

    def test_empty_records(self):
        from services.source_index import SourceIndexBuilder
        builder = SourceIndexBuilder()
        index, meta = builder.build([])
        assert index == {}
        assert meta["drawings_total"] == 0

    def test_dedup_by_drawing_name(self):
        from services.source_index import SourceIndexBuilder
        rec1 = _make_record(drawing_name="A102", drawing_id=111)
        rec2 = _make_record(drawing_name="A102", drawing_id=222)
        rec2["_id"] = "id_A102_b"
        builder = SourceIndexBuilder()
        index, _ = builder.build([rec1, rec2])
        assert len(index) == 1
        assert index["A102"].drawing_id == 111

    def test_url_construction(self):
        from services.source_index import SourceIndexBuilder
        records = [_make_record(
            s3_path="ifieldsmart/proj/Drawings/pdf",
            pdf_name="myPdf",
        )]
        builder = SourceIndexBuilder()
        index, _ = builder.build(records)
        ref = index["A102"]
        assert ref.s3_url == (
            "https://agentic-ai-production.s3.amazonaws.com/"
            "ifieldsmart/proj/Drawings/pdf/myPdf.pdf"
        )

    def test_to_dict(self):
        from services.source_index import SourceReference
        ref = SourceReference(
            drawing_id=1, drawing_name="A1", drawing_title="Title",
            s3_url="https://example.com", pdf_name="pdf1",
            x=10, y=20, width=100, height=50,
            text="", annotations=(),
        )
        d = ref.to_dict()
        assert d["drawing_id"] == 1
        assert d["s3_url"] == "https://example.com"
        assert d["x"] == 10

    def test_source_reference_is_frozen(self):
        from services.source_index import SourceReference
        ref = SourceReference(
            drawing_id=1, drawing_name="A1", drawing_title="T",
            s3_url="u", pdf_name="p", x=0, y=0, width=0, height=0,
            text="", annotations=(),
        )
        with pytest.raises(AttributeError):
            ref.drawing_id = 999
