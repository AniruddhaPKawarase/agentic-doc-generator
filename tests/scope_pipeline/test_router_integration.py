"""tests/scope_pipeline/test_router_integration.py — Integration tests for scope_gap router endpoints.

Tests exercise endpoint handler logic with mocked app.state services
using a minimal FastAPI test app with httpx.AsyncClient + ASGITransport.
"""

import asyncio
import json

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock

from scope_pipeline.models import (
    ClassifiedItem,
    AmbiguityItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    PipelineStats,
    QualityReport,
    ScopeGapResult,
    ScopeGapSession,
    SessionMessage,
)
from scope_pipeline.routers.scope_gap import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(project_id: int = 7166, trade: str = "Electrical") -> ScopeGapResult:
    """Minimal valid ScopeGapResult."""
    return ScopeGapResult(
        project_id=project_id,
        project_name="Test Project",
        trade=trade,
        items=[],
        ambiguities=[],
        gotchas=[],
        completeness=CompletenessReport(
            drawing_coverage_pct=100,
            csi_coverage_pct=100,
            hallucination_count=0,
            overall_pct=100,
            missing_drawings=[],
            missing_csi_codes=[],
            hallucinated_items=[],
            is_complete=True,
            attempt=1,
        ),
        quality=QualityReport(
            accuracy_score=1.0,
            corrections=[],
            validated_items=[],
            removed_items=[],
            summary="ok",
        ),
        documents=DocumentSet(),
        pipeline_stats=PipelineStats(
            total_ms=500,
            attempts=1,
            tokens_used=1000,
            estimated_cost_usd=0.01,
            per_agent_timing={},
            records_processed=10,
            items_extracted=5,
        ),
    )


def _make_session(
    project_id: int = 7166,
    trade: str = "Electrical",
    with_result: bool = False,
) -> ScopeGapSession:
    """Create a ScopeGapSession, optionally with a latest_result."""
    session = ScopeGapSession(project_id=project_id, trade=trade)
    if with_result:
        session.latest_result = _make_result(project_id, trade)
    return session


def _build_test_app() -> tuple:
    """Build a FastAPI test app with the scope_gap router and mock state objects."""
    test_app = FastAPI()
    test_app.include_router(router)

    mock_pipeline = AsyncMock()
    mock_pipeline.run = AsyncMock(return_value=_make_result())

    mock_job_manager = MagicMock()
    mock_job_manager.submit = AsyncMock(
        return_value={"job_id": "job_abc123", "status": "queued"}
    )
    mock_job_manager.list_jobs = MagicMock(return_value=[])
    mock_job_manager.get_job = MagicMock(return_value=None)
    mock_job_manager.cancel = AsyncMock(return_value=True)

    mock_session_manager = MagicMock()
    mock_session_manager.list_sessions = MagicMock(return_value=[])
    mock_session_manager.get_session_by_id = MagicMock(return_value=None)
    mock_session_manager.update = AsyncMock()
    mock_session_manager.delete = AsyncMock()

    mock_chat_handler = AsyncMock()
    mock_chat_handler.handle = AsyncMock(
        return_value={"answer": "Test answer", "source_refs": []}
    )

    test_app.state.scope_pipeline = mock_pipeline
    test_app.state.scope_job_manager = mock_job_manager
    test_app.state.scope_session_manager = mock_session_manager
    test_app.state.scope_chat_handler = mock_chat_handler
    test_app.state.api_client = MagicMock()

    return (
        test_app,
        mock_pipeline,
        mock_job_manager,
        mock_session_manager,
        mock_chat_handler,
    )


@pytest_asyncio.fixture
async def app_and_mocks():
    """Fixture returning (AsyncClient, pipeline, job_mgr, session_mgr, chat_handler)."""
    test_app, pipeline, job_mgr, session_mgr, chat_handler = _build_test_app()
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, pipeline, job_mgr, session_mgr, chat_handler


# ---------------------------------------------------------------------------
# Pipeline execution endpoints
# ---------------------------------------------------------------------------


class TestGenerate:
    """POST /api/scope-gap/generate"""

    @pytest.mark.asyncio
    async def test_generate_success(self, app_and_mocks):
        client, pipeline, *_ = app_and_mocks
        resp = await client.post(
            "/api/scope-gap/generate",
            json={"project_id": 7166, "trade": "Electrical"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == 7166
        assert body["trade"] == "Electrical"
        pipeline.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_pipeline_error_returns_500(self, app_and_mocks):
        client, pipeline, *_ = app_and_mocks
        pipeline.run = AsyncMock(side_effect=RuntimeError("LLM quota exceeded"))
        resp = await client.post(
            "/api/scope-gap/generate",
            json={"project_id": 7166, "trade": "Electrical"},
        )
        assert resp.status_code == 500
        assert "LLM quota exceeded" in resp.json()["detail"]


class TestSubmit:
    """POST /api/scope-gap/submit"""

    @pytest.mark.asyncio
    async def test_submit_returns_202(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        resp = await client.post(
            "/api/scope-gap/submit",
            json={"project_id": 7166, "trade": "Electrical"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"] == "job_abc123"
        assert body["status"] == "queued"
        assert "poll_url" in body

    @pytest.mark.asyncio
    async def test_submit_error_returns_500(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.submit = AsyncMock(side_effect=RuntimeError("Semaphore full"))
        resp = await client.post(
            "/api/scope-gap/submit",
            json={"project_id": 7166, "trade": "Electrical"},
        )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Job management endpoints
# ---------------------------------------------------------------------------


class TestListJobs:
    """GET /api/scope-gap/jobs"""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, app_and_mocks):
        client, *_ = app_and_mocks
        resp = await client.get("/api/scope-gap/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.list_jobs = MagicMock(
            return_value=[{"job_id": "job_x", "status": "running", "project_id": 7166}]
        )
        resp = await client.get("/api/scope-gap/jobs?project_id=7166&status=running")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        job_mgr.list_jobs.assert_called_once_with(project_id=7166, status="running")


class TestJobStatus:
    """GET /api/scope-gap/jobs/{job_id}/status"""

    @pytest.mark.asyncio
    async def test_job_status_found(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_x", "status": "running", "progress": 50.0}
        )
        resp = await client.get("/api/scope-gap/jobs/job_x/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_job_status_not_found(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(return_value=None)
        resp = await client.get("/api/scope-gap/jobs/job_x/status")
        assert resp.status_code == 404


class TestJobResult:
    """GET /api/scope-gap/jobs/{job_id}/result"""

    @pytest.mark.asyncio
    async def test_job_result_completed(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_x", "status": "completed"}
        )
        resp = await client.get("/api/scope-gap/jobs/job_x/result")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

    @pytest.mark.asyncio
    async def test_job_result_partial(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_x", "status": "partial"}
        )
        resp = await client.get("/api/scope-gap/jobs/job_x/result")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_job_result_still_running_returns_409(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_x", "status": "running"}
        )
        resp = await client.get("/api/scope-gap/jobs/job_x/result")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_job_result_not_found(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(return_value=None)
        resp = await client.get("/api/scope-gap/jobs/job_x/result")
        assert resp.status_code == 404


class TestContinueJob:
    """POST /api/scope-gap/jobs/{job_id}/continue"""

    @pytest.mark.asyncio
    async def test_continue_partial_job(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={
                "job_id": "job_old",
                "status": "partial",
                "project_id": 7166,
                "trade": "Electrical",
            }
        )
        job_mgr.submit = AsyncMock(
            return_value={"job_id": "job_new", "status": "queued"}
        )
        resp = await client.post("/api/scope-gap/jobs/job_old/continue")
        assert resp.status_code == 202
        body = resp.json()
        assert body["continued_from"] == "job_old"
        assert body["job_id"] == "job_new"

    @pytest.mark.asyncio
    async def test_continue_non_partial_returns_409(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_old", "status": "completed"}
        )
        resp = await client.post("/api/scope-gap/jobs/job_old/continue")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_continue_not_found(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.get_job = MagicMock(return_value=None)
        resp = await client.post("/api/scope-gap/jobs/job_nonexistent/continue")
        assert resp.status_code == 404


class TestCancelJob:
    """DELETE /api/scope-gap/jobs/{job_id}"""

    @pytest.mark.asyncio
    async def test_cancel_success(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.cancel = AsyncMock(return_value=True)
        resp = await client.delete("/api/scope-gap/jobs/job_x")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True

    @pytest.mark.asyncio
    async def test_cancel_completed_returns_409(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.cancel = AsyncMock(return_value=False)
        job_mgr.get_job = MagicMock(
            return_value={"job_id": "job_x", "status": "completed"}
        )
        resp = await client.delete("/api/scope-gap/jobs/job_x")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_not_found(self, app_and_mocks):
        client, _, job_mgr, *_ = app_and_mocks
        job_mgr.cancel = AsyncMock(return_value=False)
        job_mgr.get_job = MagicMock(return_value=None)
        resp = await client.delete("/api/scope-gap/jobs/job_x")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session management endpoints
# ---------------------------------------------------------------------------


class TestListSessions:
    """GET /api/scope-gap/sessions"""

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, app_and_mocks):
        client, *_ = app_and_mocks
        resp = await client.get("/api/scope-gap/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_sessions_returns_session_summaries(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session(with_result=True)
        session_mgr.list_sessions = MagicMock(return_value=[session])
        resp = await client.get("/api/scope-gap/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["project_id"] == 7166
        assert body[0]["has_result"] is True
        assert "created_at" in body[0]
        assert "runs_count" in body[0]

    @pytest.mark.asyncio
    async def test_list_sessions_with_filters(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.list_sessions = MagicMock(return_value=[])
        resp = await client.get("/api/scope-gap/sessions?project_id=7166&trade=Electrical")
        assert resp.status_code == 200
        session_mgr.list_sessions.assert_called_once_with(
            project_id=7166, trade="Electrical"
        )


class TestGetSession:
    """GET /api/scope-gap/sessions/{session_id}"""

    @pytest.mark.asyncio
    async def test_get_session_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.get(f"/api/scope-gap/sessions/{session.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == 7166

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.get("/api/scope-gap/sessions/nonexistent")
        assert resp.status_code == 404


class TestDeleteSession:
    """DELETE /api/scope-gap/sessions/{session_id}"""

    @pytest.mark.asyncio
    async def test_delete_session_success(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.delete(f"/api/scope-gap/sessions/{session.id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        session_mgr.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.delete("/api/scope-gap/sessions/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# User decision endpoints
# ---------------------------------------------------------------------------


class TestResolveAmbiguity:
    """POST /api/scope-gap/sessions/{session_id}/resolve-ambiguity"""

    @pytest.mark.asyncio
    async def test_resolve_ambiguity_success(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/resolve-ambiguity",
            json={"ambiguity_id": "amb_abc12345", "assigned_trade": "Plumbing"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["assigned_trade"] == "Plumbing"
        session_mgr.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolve_ambiguity_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.post(
            "/api/scope-gap/sessions/nonexistent/resolve-ambiguity",
            json={"ambiguity_id": "amb_abc12345", "assigned_trade": "Plumbing"},
        )
        assert resp.status_code == 404


class TestAcknowledgeGotcha:
    """POST /api/scope-gap/sessions/{session_id}/acknowledge-gotcha"""

    @pytest.mark.asyncio
    async def test_acknowledge_gotcha_success(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/acknowledge-gotcha",
            json={"gotcha_id": "gtc_abc12345"},
        )
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True
        assert "gtc_abc12345" in session.gotcha_acknowledgments
        session_mgr.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acknowledge_gotcha_idempotent(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session.gotcha_acknowledgments = ["gtc_abc12345"]
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/acknowledge-gotcha",
            json={"gotcha_id": "gtc_abc12345"},
        )
        assert resp.status_code == 200
        # update NOT called because already acknowledged
        session_mgr.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_acknowledge_gotcha_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.post(
            "/api/scope-gap/sessions/nonexistent/acknowledge-gotcha",
            json={"gotcha_id": "gtc_abc12345"},
        )
        assert resp.status_code == 404


class TestIgnoreItem:
    """POST /api/scope-gap/sessions/{session_id}/ignore-item"""

    @pytest.mark.asyncio
    async def test_ignore_item_success(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/ignore-item",
            json={"item_id": "itm_abc12345"},
        )
        assert resp.status_code == 200
        assert resp.json()["ignored"] is True
        assert "itm_abc12345" in session.ignored_items
        session_mgr.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignore_item_idempotent(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session.ignored_items = ["itm_abc12345"]
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/ignore-item",
            json={"item_id": "itm_abc12345"},
        )
        assert resp.status_code == 200
        session_mgr.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ignore_item_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.post(
            "/api/scope-gap/sessions/nonexistent/ignore-item",
            json={"item_id": "itm_abc12345"},
        )
        assert resp.status_code == 404


class TestRestoreItem:
    """POST /api/scope-gap/sessions/{session_id}/restore-item"""

    @pytest.mark.asyncio
    async def test_restore_item_success(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session.ignored_items = ["itm_abc12345", "itm_other"]
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/restore-item",
            json={"item_id": "itm_abc12345"},
        )
        assert resp.status_code == 200
        assert resp.json()["restored"] is True
        assert "itm_abc12345" not in session.ignored_items
        session_mgr.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_item_not_ignored(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session = _make_session()
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/restore-item",
            json={"item_id": "itm_nonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json()["restored"] is False
        session_mgr.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restore_item_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.post(
            "/api/scope-gap/sessions/nonexistent/restore-item",
            json={"item_id": "itm_abc12345"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


class TestChat:
    """POST /api/scope-gap/sessions/{session_id}/chat"""

    @pytest.mark.asyncio
    async def test_chat_success(self, app_and_mocks):
        client, _, _, session_mgr, chat_handler = app_and_mocks
        session = _make_session(with_result=True)
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/chat",
            json={"message": "How many items were extracted?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Test answer"
        chat_handler.handle.assert_awaited_once()
        session_mgr.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chat_session_not_found(self, app_and_mocks):
        client, _, _, session_mgr, *_ = app_and_mocks
        session_mgr.get_session_by_id = MagicMock(return_value=None)
        resp = await client.post(
            "/api/scope-gap/sessions/nonexistent/chat",
            json={"message": "test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_handler_error_returns_500(self, app_and_mocks):
        client, _, _, session_mgr, chat_handler = app_and_mocks
        session = _make_session(with_result=True)
        session_mgr.get_session_by_id = MagicMock(return_value=session)
        chat_handler.handle = AsyncMock(side_effect=RuntimeError("OpenAI down"))
        resp = await client.post(
            f"/api/scope-gap/sessions/{session.id}/chat",
            json={"message": "test"},
        )
        assert resp.status_code == 500
