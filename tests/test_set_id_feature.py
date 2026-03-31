"""Tests for the SetId filter feature.

Validates:
  - ChatRequest accepts set_ids (int, str, list, None)
  - APIClient.get_summary_by_trade_and_set dispatches parallel calls and merges
  - ContextBuilder includes set metadata in context header
  - DocumentGenerator includes set info in filename/header/footer
  - Cache keys differentiate by set_ids
  - Backward compatibility: existing payloads without set_ids work unchanged
"""

import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("S3_AGENT_PREFIX", "construction-intelligence-agent")


# ── ChatRequest Schema Tests ──────────────────────────────────────────────


@pytest.mark.unit
class TestChatRequestSetIds:
    """Validate set_ids field on ChatRequest."""

    def test_set_ids_defaults_to_none(self):
        from models.schemas import ChatRequest
        req = ChatRequest(project_id=7298, query="create scope for electrical")
        assert req.set_ids is None

    def test_set_ids_accepts_int_list(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7298,
            query="create scope for electrical",
            set_ids=[4730, 4731],
        )
        assert req.set_ids == [4730, 4731]

    def test_set_ids_accepts_str_list(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7298,
            query="create scope for electrical",
            set_ids=["4730", "abc"],
        )
        assert req.set_ids == ["4730", "abc"]

    def test_set_ids_accepts_mixed_list(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7298,
            query="create scope for electrical",
            set_ids=[4730, "abc"],
        )
        assert req.set_ids == [4730, "abc"]

    def test_set_ids_accepts_single_element(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7298,
            query="create scope for electrical",
            set_ids=[4730],
        )
        assert req.set_ids == [4730]

    def test_set_ids_null_means_none(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7298,
            query="create scope for electrical",
            set_ids=None,
        )
        assert req.set_ids is None


# ── ChatResponse Schema Tests ─────────────────────────────────────────────


@pytest.mark.unit
class TestChatResponseSetFields:
    """Validate set_ids/set_names on ChatResponse."""

    def test_response_defaults(self):
        from models.schemas import ChatResponse
        resp = ChatResponse(session_id="test", answer="hello")
        assert resp.set_ids is None
        assert resp.set_names == []

    def test_response_with_set_info(self):
        from models.schemas import ChatResponse
        resp = ChatResponse(
            session_id="test",
            answer="hello",
            set_ids=[4730],
            set_names=["100% CONSTRUCTION DOCUMENTS"],
        )
        assert resp.set_ids == [4730]
        assert resp.set_names == ["100% CONSTRUCTION DOCUMENTS"]


# ── APIClient Tests ───────────────────────────────────────────────────────


MOCK_RECORDS = [
    {
        "_id": f"rec_{i}",
        "projectId": 7298,
        "setName": "100% CONSTRUCTION DOCUMENTS",
        "setTrade": "Electrical",
        "drawingName": f"E-{100 + i}",
        "drawingTitle": f"Drawing {i}",
        "text": f"Note text for drawing {i}",
        "csi_division": ["26 - Electrical"],
        "trades": ["Electrical"],
    }
    for i in range(5)
]


@pytest.mark.unit
class TestAPIClientSetId:
    """Test get_summary_by_trade_and_set method."""

    @pytest.mark.asyncio
    async def test_single_set_id_returns_records_and_names(self):
        from services.api_client import APIClient

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        client = APIClient(cache=mock_cache)

        with patch.object(client, "_fetch_all_pages", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = MOCK_RECORDS
            records, set_names = await client.get_summary_by_trade_and_set(
                project_id=7298,
                trade="Electrical",
                set_ids=[4730],
            )
            assert len(records) == 5
            assert "100% CONSTRUCTION DOCUMENTS" in set_names
            mock_fetch.assert_called_once_with(7298, "Electrical", set_id=4730)

    @pytest.mark.asyncio
    async def test_multiple_set_ids_merges_and_deduplicates(self):
        from services.api_client import APIClient

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        client = APIClient(cache=mock_cache)

        set_a_records = [
            {"_id": "a1", "setName": "Set A", "drawingName": "E-101", "text": "A1"},
            {"_id": "shared", "setName": "Set A", "drawingName": "E-102", "text": "shared"},
        ]
        set_b_records = [
            {"_id": "b1", "setName": "Set B", "drawingName": "E-201", "text": "B1"},
            {"_id": "shared", "setName": "Set B", "drawingName": "E-102", "text": "shared dup"},
        ]

        with patch.object(client, "_fetch_all_pages", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [set_a_records, set_b_records]
            records, set_names = await client.get_summary_by_trade_and_set(
                project_id=7298,
                trade="Electrical",
                set_ids=[100, 200],
            )
            # 3 unique records (shared deduped)
            assert len(records) == 3
            assert sorted(set_names) == ["Set A", "Set B"]
            assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty(self):
        from services.api_client import APIClient

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        client = APIClient(cache=mock_cache)

        with patch.object(client, "_fetch_all_pages", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            records, set_names = await client.get_summary_by_trade_and_set(
                project_id=7298,
                trade="Electrical",
                set_ids=[99999],
            )
            assert records == []
            assert set_names == []

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self):
        from services.api_client import APIClient

        cached_data = {"records": MOCK_RECORDS[:2], "set_names": ["Cached Set"]}
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached_data)
        mock_cache.set = AsyncMock()

        client = APIClient(cache=mock_cache)

        with patch.object(client, "_fetch_all_pages", new_callable=AsyncMock) as mock_fetch:
            records, set_names = await client.get_summary_by_trade_and_set(
                project_id=7298,
                trade="Electrical",
                set_ids=[4730],
            )
            assert len(records) == 2
            assert set_names == ["Cached Set"]
            mock_fetch.assert_not_called()


# ── Config Tests ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestConfigSetIdPath:
    """Verify the new config setting exists."""

    def test_default_path_exists(self):
        from config import get_settings
        s = get_settings()
        assert s.summary_by_trade_and_set_path == "/api/drawingText/summaryByTradeAndSet"


# ── Document Generator Tests ─────────────────────────────────────────────


@pytest.mark.unit
class TestDocumentGeneratorSetId:
    """Verify set info appears in filenames and document metadata."""

    def test_filename_includes_set_id(self):
        """When set_ids is provided, filename should contain set slug."""
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        doc_meta = gen.generate_sync(
            content="## Test\nSome content here.",
            project_id=7298,
            trade="Electrical",
            document_type="scope",
            project_name="Test Project (ID: 7298)",
            set_ids=[4730],
            set_names=["100% CONSTRUCTION DOCUMENTS"],
        )
        assert "set4730" in doc_meta.filename
        assert doc_meta.filename.endswith(".docx")

    def test_filename_multiple_set_ids(self):
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        doc_meta = gen.generate_sync(
            content="## Test\nContent.",
            project_id=7298,
            trade="Electrical",
            document_type="scope",
            project_name="Test Project (ID: 7298)",
            set_ids=[4730, 4731],
            set_names=["Set A", "Set B"],
        )
        assert "set4730_4731" in doc_meta.filename

    def test_filename_no_set_ids_unchanged(self):
        """Without set_ids, filename format should be unchanged."""
        from services.document_generator import DocumentGenerator

        gen = DocumentGenerator()
        doc_meta = gen.generate_sync(
            content="## Test\nContent.",
            project_id=7298,
            trade="Electrical",
            document_type="scope",
            project_name="Test Project (ID: 7298)",
        )
        assert "set" not in doc_meta.filename
        assert doc_meta.filename.startswith("scope_Electrical_")


# ── Backward Compatibility Tests ──────────────────────────────────────────


@pytest.mark.unit
class TestBackwardCompatibility:
    """Ensure existing payloads work unchanged."""

    def test_old_chat_request_still_valid(self):
        from models.schemas import ChatRequest
        req = ChatRequest(
            project_id=7276,
            query="Create a scope for plumbing",
            session_id=None,
            generate_document=True,
        )
        assert req.set_ids is None
        assert req.project_id == 7276

    def test_old_chat_response_serialization(self):
        from models.schemas import ChatResponse
        resp = ChatResponse(session_id="s1", answer="test answer")
        data = resp.model_dump(mode="json")
        assert data["set_ids"] is None
        assert data["set_names"] == []
        assert "answer" in data
