"""Phase 7.1: Construction Agent S3 migration tests."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import boto3
import pytest
from moto import mock_aws

AGENT_ROOT = Path(__file__).resolve().parent.parent
PROD_ROOT = AGENT_ROOT.parent
sys.path.insert(0, str(PROD_ROOT))
sys.path.insert(0, str(AGENT_ROOT))

TEST_BUCKET = "test-vcs-agents"


def _reset_s3_caches():
    """Reset module-level S3 client and config caches."""
    from s3_utils.config import get_s3_config
    import s3_utils.client as _client_mod
    get_s3_config.cache_clear()
    _client_mod._s3_client = None


@pytest.fixture(autouse=True)
def s3_env(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET_NAME", TEST_BUCKET)
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("S3_AGENT_PREFIX", "construction-intelligence-agent")
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    _reset_s3_caches()


@pytest.fixture
def s3_bucket():
    with mock_aws():
        _reset_s3_caches()
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket=TEST_BUCKET)
        yield conn
        _reset_s3_caches()


class TestDocumentS3Upload:
    """Test document upload to S3 after local save."""

    def test_upload_docx_to_s3(self, s3_bucket, tmp_path):
        from s3_utils.operations import upload_file, object_exists
        from s3_utils.helpers import generated_document_key
        doc_file = tmp_path / "scope_electrical_Granville_7298_abc12345.docx"
        doc_file.write_bytes(b"PK fake docx content for testing")
        s3_key = generated_document_key(
            "construction-intelligence-agent", "Granville", 7298, "Foundation Plans", 4730, "Electrical", doc_file.name
        )
        assert upload_file(str(doc_file), s3_key) is True
        assert object_exists(s3_key) is True

    def test_upload_exhibit_to_s3(self, s3_bucket, tmp_path):
        from s3_utils.operations import upload_file, object_exists
        from s3_utils.helpers import generated_document_key
        doc_file = tmp_path / "Exhibit_GranvilleHotel_Electrical_scope_7298_e5f6g7h8.docx"
        doc_file.write_bytes(b"PK fake exhibit content")
        s3_key = generated_document_key(
            "construction-intelligence-agent", "GranvilleHotel", 7298, "Foundation Plans", 4730, "Electrical", doc_file.name
        )
        assert upload_file(str(doc_file), s3_key) is True
        assert object_exists(s3_key) is True

    def test_s3_key_structure(self):
        from s3_utils.helpers import generated_document_key
        key = generated_document_key(
            "construction-intelligence-agent", "Granville Hotel", 7298, "HVAC Plans", 4730, "HVAC / Mechanical", "doc.docx"
        )
        assert key == "construction-intelligence-agent/generated_documents/Granville_Hotel(7298)/HVAC_Plans(4730)/HVAC_Mechanical/doc.docx"

    def test_upload_preserves_local_on_s3_failure(self, tmp_path):
        """When S3 is unavailable, local file must still exist."""
        doc_file = tmp_path / "scope_plumbing_Test_7000_def456.docx"
        doc_file.write_bytes(b"PK local content")
        # No mock context -- S3 calls will fail gracefully
        from s3_utils.operations import upload_file
        result = upload_file(str(doc_file), "will/fail.docx")
        assert result is False
        assert doc_file.exists()


class TestDocumentS3Download:
    """Test document download from S3 with presigned URLs."""

    def test_presigned_url_generation(self, s3_bucket):
        from s3_utils.operations import upload_bytes, generate_presigned_url
        s3_key = "construction-intelligence-agent/generated_documents/Test_7000/Electrical/test.docx"
        upload_bytes(b"docx content", s3_key)
        url = generate_presigned_url(s3_key)
        assert url is not None
        assert "test.docx" in url

    def test_download_file_from_s3(self, s3_bucket, tmp_path):
        from s3_utils.operations import upload_bytes, download_file
        s3_key = "construction-intelligence-agent/generated_documents/Test_7000/Electrical/test.docx"
        content = b"PK real docx bytes here"
        upload_bytes(content, s3_key)
        local_path = tmp_path / "downloaded.docx"
        assert download_file(s3_key, str(local_path)) is True
        assert local_path.read_bytes() == content

    def test_list_documents_by_prefix(self, s3_bucket):
        from s3_utils.operations import upload_bytes, list_objects
        prefix = "construction-intelligence-agent/generated_documents/"
        for i in range(3):
            upload_bytes(b"doc", f"{prefix}Project_{i}/Electrical/doc_{i}.docx")
        objects = list_objects(prefix)
        assert len(objects) == 3

    def test_list_documents_by_project(self, s3_bucket):
        from s3_utils.operations import upload_bytes, list_objects
        prefix = "construction-intelligence-agent/generated_documents/Granville_7298/"
        upload_bytes(b"a", f"{prefix}Electrical/scope.docx")
        upload_bytes(b"b", f"{prefix}Plumbing/scope.docx")
        upload_bytes(b"c", f"{prefix}HVAC/scope.docx")
        objects = list_objects(prefix)
        assert len(objects) == 3


class TestDocumentS3Delete:
    """Test document deletion from S3."""

    def test_delete_single_document(self, s3_bucket):
        from s3_utils.operations import upload_bytes, delete_object, object_exists
        s3_key = "construction-intelligence-agent/generated_documents/Test/Electrical/del.docx"
        upload_bytes(b"content", s3_key)
        assert delete_object(s3_key) is True
        assert object_exists(s3_key) is False

    def test_delete_project_documents(self, s3_bucket):
        from s3_utils.operations import upload_bytes, delete_prefix, list_objects
        prefix = "construction-intelligence-agent/generated_documents/OldProject_9999/"
        for trade in ["Electrical", "Plumbing", "HVAC"]:
            upload_bytes(b"x", f"{prefix}{trade}/doc.docx")
        deleted = delete_prefix(prefix)
        assert deleted == 3
        assert list_objects(prefix) == []


class TestConversationMemoryS3:
    """Test session export to S3."""

    def test_upload_session_json(self, s3_bucket):
        from s3_utils.operations import upload_bytes, download_bytes
        from s3_utils.helpers import conversation_memory_key
        session_data = {
            "session_id": "abc123",
            "messages": [{"role": "user", "content": "test query"}],
            "created_at": "2026-03-23T00:00:00Z",
        }
        s3_key = conversation_memory_key("construction-intelligence-agent", "abc123")
        data = json.dumps(session_data).encode()
        assert upload_bytes(data, s3_key) is True
        restored = json.loads(download_bytes(s3_key))
        assert restored["session_id"] == "abc123"


class TestRollback:
    """Test STORAGE_BACKEND=local rollback."""

    def test_local_mode_skips_s3(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        from s3_utils.config import get_s3_config
        get_s3_config.cache_clear()
        config = get_s3_config()
        assert config.is_s3_enabled is False

    def test_s3_client_returns_none_in_local_mode(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        _reset_s3_caches()
        from s3_utils.client import get_s3_client
        assert get_s3_client() is None

    def test_operations_return_false_in_local_mode(self, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        _reset_s3_caches()
        from s3_utils.operations import upload_bytes, download_bytes, list_objects
        assert upload_bytes(b"test", "key") is False
        assert download_bytes("key") is None
        assert list_objects("prefix/") == []
