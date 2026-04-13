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
