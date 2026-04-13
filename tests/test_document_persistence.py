"""Tests for document persistence features: S3 keys, annotations, listing."""
import pytest


class TestGeneratedDocumentKeyWithSet:

    def test_key_with_set_name_and_id(self):
        from s3_utils.helpers import generated_document_key
        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Granville Hotel",
            project_id=7298,
            set_name="Foundation Plans",
            set_id=4730,
            trade="Electrical",
            filename="scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx",
        )
        assert key == (
            "construction-intelligence-agent/generated_documents/"
            "Granville_Hotel(7298)/Foundation_Plans(4730)/Electrical/"
            "scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx"
        )

    def test_key_without_project_name(self):
        from s3_utils.helpers import generated_document_key
        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name=None,
            project_id=7298,
            set_name="Sheet Set A",
            set_id=100,
            trade="Plumbing",
            filename="scope_plumbing_7298_abcd1234.docx",
        )
        assert key == (
            "construction-intelligence-agent/generated_documents/"
            "Project(7298)/Sheet_Set_A(100)/Plumbing/"
            "scope_plumbing_7298_abcd1234.docx"
        )

    def test_key_sanitizes_special_chars_in_set_name(self):
        from s3_utils.helpers import generated_document_key
        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Test Project",
            project_id=1,
            set_name="HVAC / Mechanical (Phase 2)",
            set_id=99,
            trade="HVAC",
            filename="doc.docx",
        )
        assert "HVAC_Mechanical_Phase_2(99)" in key
        assert "//" not in key

    def test_key_empty_set_name_fallback(self):
        from s3_utils.helpers import generated_document_key
        key = generated_document_key(
            agent_prefix="construction-intelligence-agent",
            project_name="Hotel",
            project_id=1,
            set_name="",
            set_id=50,
            trade="Concrete",
            filename="doc.docx",
        )
        assert "Set(50)" in key


# ── Source Index / Annotations Tests ─────────────────────────────────────────

class TestAnnotationDataclass:
    def test_annotation_to_dict(self):
        from services.source_index import Annotation
        ann = Annotation(text="Panel EP-1", x=100, y=200, width=50, height=30)
        d = ann.to_dict()
        assert d == {"text": "Panel EP-1", "x": 100, "y": 200, "width": 50, "height": 30}

    def test_annotation_with_null_coords(self):
        from services.source_index import Annotation
        ann = Annotation(text="Some note", x=None, y=None, width=None, height=None)
        d = ann.to_dict()
        assert d["text"] == "Some note"
        assert d["x"] is None


class TestSourceReferenceWithAnnotations:
    def test_to_dict_includes_text_and_annotations(self):
        from services.source_index import SourceReference, Annotation
        ref = SourceReference(
            drawing_id=123, drawing_name="A-12", drawing_title="FLOOR PLAN",
            s3_url="https://example.com/A12.pdf", pdf_name="pdfA12",
            x=100, y=200, width=50, height=30, text="Panel EP-1",
            annotations=(
                Annotation(text="Panel EP-1", x=100, y=200, width=50, height=30),
                Annotation(text="Conduit run", x=300, y=150, width=40, height=20),
            ),
        )
        d = ref.to_dict()
        assert d["text"] == "Panel EP-1"
        assert len(d["annotations"]) == 2
        assert d["annotations"][0]["text"] == "Panel EP-1"
        assert d["annotations"][1]["text"] == "Conduit run"
        assert d["x"] == 100
        assert d["y"] == 200

    def test_backward_compat_root_level_fields(self):
        from services.source_index import SourceReference, Annotation
        ref = SourceReference(
            drawing_id=1, drawing_name="B-1", drawing_title="T",
            s3_url="https://x.com/b1.pdf", pdf_name="pdfB1",
            x=10, y=20, width=5, height=3, text="First note",
            annotations=(Annotation(text="First note", x=10, y=20, width=5, height=3),),
        )
        d = ref.to_dict()
        assert "drawing_id" in d
        assert "s3_url" in d
        assert "x" in d and "y" in d and "width" in d and "height" in d


class TestSourceIndexBuilderAnnotations:
    def _make_record(self, drawing_name, text, x=None, y=None, w=None, h=None,
                     s3_path="ifieldsmart/proj/Drawings/pdf", pdf_name="pdfA12",
                     drawing_id=123, drawing_title="FLOOR PLAN"):
        return {
            "drawingName": drawing_name, "text": text,
            "x": x, "y": y, "width": w, "height": h,
            "s3BucketPath": s3_path, "pdfName": pdf_name,
            "drawingId": drawing_id, "drawingTitle": drawing_title,
        }

    def test_single_record_per_drawing(self):
        from services.source_index import SourceIndexBuilder
        builder = SourceIndexBuilder()
        records = [self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30)]
        index, meta = builder.build(records)
        assert "A-12" in index
        ref = index["A-12"]
        assert ref.text == "Panel EP-1"
        assert len(ref.annotations) == 1
        assert ref.x == 100

    def test_multiple_records_same_drawing(self):
        from services.source_index import SourceIndexBuilder
        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30),
            self._make_record("A-12", "Conduit run to MDP", 300, 150, 40, 20),
            self._make_record("A-12", "Junction box JB-3", 500, 100, 25, 15),
        ]
        index, meta = builder.build(records)
        ref = index["A-12"]
        assert len(ref.annotations) == 3
        assert ref.text == "Panel EP-1"
        assert ref.x == 100

    def test_records_with_empty_text_excluded(self):
        from services.source_index import SourceIndexBuilder
        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Panel EP-1", 100, 200, 50, 30),
            self._make_record("A-12", "", 300, 150, 40, 20),
            self._make_record("A-12", "   ", 400, 100, 25, 15),
        ]
        index, meta = builder.build(records)
        assert len(index["A-12"].annotations) == 1

    def test_multiple_drawings(self):
        from services.source_index import SourceIndexBuilder
        builder = SourceIndexBuilder()
        records = [
            self._make_record("A-12", "Note 1", 100, 200, 50, 30),
            self._make_record("A-13", "Note 2", 200, 300, 60, 40,
                              pdf_name="pdfA13", drawing_id=456, drawing_title="PANEL"),
        ]
        index, meta = builder.build(records)
        assert len(index) == 2
        assert index["A-12"].text == "Note 1"
        assert index["A-13"].text == "Note 2"
