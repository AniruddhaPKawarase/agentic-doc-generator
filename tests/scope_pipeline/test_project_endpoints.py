"""tests/scope_pipeline/test_project_endpoints.py — Tests for project-level API endpoints.

Uses httpx.AsyncClient with ASGITransport and mocked app.state services to
exercise the project_endpoints router without real infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from scope_pipeline.models_v2 import ProjectSession, TradeResultContainer, TradeRunRecord
from scope_pipeline.routers.project_endpoints import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_ID = 7166

_SAMPLE_TRADES = [
    {"trade": "Electrical", "record_count": 42},
    {"trade": "Plumbing", "record_count": 15},
    {"trade": "HVAC", "record_count": 30},
]

_SAMPLE_RECORDS = [
    {
        "_id": "r1",
        "drawingName": "E-101",
        "drawingTitle": "Electrical Plan",
        "setTrade": "Electrical",
        "source_type": "drawing",
        "setName": "Set A",
    },
    {
        "_id": "r2",
        "drawingName": "P-101",
        "drawingTitle": "Plumbing Plan",
        "setTrade": "Plumbing",
        "source_type": "drawing",
        "setName": "Set A",
    },
    {
        "_id": "r3",
        "drawingName": "SP-001",
        "drawingTitle": "Plumbing Spec",
        "setTrade": "Plumbing",
        "source_type": "specification",
        "setName": "Set B",
    },
]


def _build_test_app():
    """Build a minimal FastAPI app with project_endpoints router and mocked state."""
    app = FastAPI()
    app.include_router(router)

    mock_trade_discovery = MagicMock()
    mock_trade_discovery.discover_trades = AsyncMock(return_value=_SAMPLE_TRADES)

    mock_trade_color = MagicMock()
    mock_trade_color.get_color = MagicMock(
        side_effect=lambda trade: {"hex": "#F48FB1", "rgb": [244, 143, 177]}
    )
    mock_trade_color.get_all_colors = MagicMock(
        return_value={
            t["trade"]: {"hex": "#F48FB1", "rgb": [244, 143, 177]}
            for t in _SAMPLE_TRADES
        }
    )

    mock_drawing_index = MagicMock()
    mock_drawing_index.build_categorized_tree = MagicMock(
        return_value={
            "ELECTRICAL": {
                "drawings": [
                    {"drawing_name": "E-101", "drawing_title": "Electrical Plan", "source_type": "drawing"}
                ],
                "specs": [],
            },
            "PLUMBING": {
                "drawings": [
                    {"drawing_name": "P-101", "drawing_title": "Plumbing Plan", "source_type": "drawing"}
                ],
                "specs": [
                    {"drawing_name": "SP-001", "drawing_title": "Plumbing Spec", "source_type": "specification"}
                ],
            },
        }
    )
    mock_drawing_index.build_drawing_metadata = MagicMock(
        return_value={
            "E-101": {
                "drawing_name": "E-101",
                "drawing_title": "Electrical Plan",
                "discipline": "ELECTRICAL",
                "source_type": "drawing",
                "set_name": "Set A",
                "set_trade": "Electrical",
                "record_count": 1,
            },
            "P-101": {
                "drawing_name": "P-101",
                "drawing_title": "Plumbing Plan",
                "discipline": "PLUMBING",
                "source_type": "drawing",
                "set_name": "Set A",
                "set_trade": "Plumbing",
                "record_count": 1,
            },
        }
    )

    mock_session_manager = MagicMock()
    mock_session_manager.get_by_project_id = MagicMock(return_value=None)

    mock_scope_data_fetcher = MagicMock()
    mock_scope_data_fetcher.fetch_records = AsyncMock(
        return_value={
            "records": _SAMPLE_RECORDS,
            "drawing_names": {"E-101", "P-101", "SP-001"},
            "csi_codes": set(),
        }
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.run_all_trades = AsyncMock(return_value=None)

    app.state.trade_discovery_service = mock_trade_discovery
    app.state.trade_color_service = mock_trade_color
    app.state.drawing_index_service = mock_drawing_index
    app.state.project_session_manager = mock_session_manager
    app.state.scope_data_fetcher = mock_scope_data_fetcher
    app.state.project_orchestrator = mock_orchestrator

    return (
        app,
        mock_trade_discovery,
        mock_trade_color,
        mock_drawing_index,
        mock_session_manager,
        mock_scope_data_fetcher,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client_and_mocks():
    """Async fixture: (client, discovery, color, drawing_index, session_mgr, fetcher)."""
    (
        app,
        mock_trade_discovery,
        mock_trade_color,
        mock_drawing_index,
        mock_session_manager,
        mock_scope_data_fetcher,
    ) = _build_test_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield (
            client,
            mock_trade_discovery,
            mock_trade_color,
            mock_drawing_index,
            mock_session_manager,
            mock_scope_data_fetcher,
        )


# ---------------------------------------------------------------------------
# test_get_trades
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_trades(client_and_mocks):
    """GET /{project_id}/trades returns trade list with status and color."""
    client, mock_discovery, mock_color, _, mock_session_mgr, _ = client_and_mocks

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/trades")

    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == _PROJECT_ID
    assert data["total_trades"] == 3
    assert data["total_records"] == 42 + 15 + 30

    trades = data["trades"]
    assert len(trades) == 3

    electrical = next(t for t in trades if t["trade"] == "Electrical")
    assert electrical["record_count"] == 42
    assert electrical["status"] == "pending"   # no session in mock
    assert "color" in electrical
    assert "hex" in electrical["color"]
    assert "rgb" in electrical["color"]

    mock_discovery.discover_trades.assert_awaited_once_with(
        project_id=_PROJECT_ID,
        set_id=None,
    )


@pytest.mark.asyncio
async def test_get_trades_with_set_id(client_and_mocks):
    """GET /{project_id}/trades?set_id=10 passes set_id to discover_trades."""
    client, mock_discovery, *_ = client_and_mocks

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/trades?set_id=10")

    assert resp.status_code == 200
    mock_discovery.discover_trades.assert_awaited_once_with(
        project_id=_PROJECT_ID,
        set_id=10,
    )


@pytest.mark.asyncio
async def test_get_trades_status_ready_when_session_has_result():
    """Trade status is 'ready' when the session has a latest_result for that trade."""
    (
        app,
        mock_trade_discovery,
        _,
        __,
        mock_session_mgr,
        ___,
    ) = _build_test_app()

    # Build a minimal ProjectSession with a result for Electrical
    session = ProjectSession(project_id=_PROJECT_ID)
    container = TradeResultContainer(trade="Electrical")
    fake_result = MagicMock()
    fake_result.items = []
    container = container.model_copy(update={"latest_result": fake_result})
    session.trade_results["electrical"] = container
    mock_session_mgr.get_by_project_id = MagicMock(return_value=session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/trades")

    assert resp.status_code == 200
    trades = resp.json()["trades"]
    electrical = next(t for t in trades if t["trade"] == "Electrical")
    assert electrical["status"] == "ready"


@pytest.mark.asyncio
async def test_get_trades_status_failed_when_last_run_failed():
    """Trade status is 'failed' when the last run record has status='failed'."""
    app, _, __, ___, mock_session_mgr, ____ = _build_test_app()

    session = ProjectSession(project_id=_PROJECT_ID)
    run_record = TradeRunRecord(status="failed")
    container = TradeResultContainer(trade="Plumbing")
    container = container.model_copy(update={"versions": [run_record], "latest_result": None})
    session.trade_results["plumbing"] = container
    mock_session_mgr.get_by_project_id = MagicMock(return_value=session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/trades")

    assert resp.status_code == 200
    trades = resp.json()["trades"]
    plumbing = next(t for t in trades if t["trade"] == "Plumbing")
    assert plumbing["status"] == "failed"


# ---------------------------------------------------------------------------
# test_get_trade_colors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_trade_colors(client_and_mocks):
    """GET /{project_id}/trade-colors returns color palette for all trades."""
    client, mock_discovery, mock_color, *_ = client_and_mocks

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/trade-colors")

    assert resp.status_code == 200
    data = resp.json()

    assert "colors" in data
    colors = data["colors"]
    assert "Electrical" in colors
    assert "Plumbing" in colors
    assert "hex" in colors["Electrical"]
    assert "rgb" in colors["Electrical"]

    mock_discovery.discover_trades.assert_awaited_once_with(project_id=_PROJECT_ID)
    mock_color.get_all_colors.assert_called_once()


# ---------------------------------------------------------------------------
# test_get_drawings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_drawings(client_and_mocks):
    """GET /{project_id}/drawings returns categorized drawing tree."""
    client, _, __, mock_drawing_index, ___, mock_fetcher = client_and_mocks

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/drawings")

    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == _PROJECT_ID
    assert data["total_drawings"] == 2    # E-101 + P-101
    assert data["total_specs"] == 1       # SP-001
    assert "ELECTRICAL" in data["categories"]
    assert "PLUMBING" in data["categories"]

    mock_fetcher.fetch_records.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_drawings_with_set_id(client_and_mocks):
    """GET /{project_id}/drawings?set_id=5 passes set_ids=[5] to fetch_records."""
    client, _, __, ___, ____, mock_fetcher = client_and_mocks

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/drawings?set_id=5")

    assert resp.status_code == 200
    call = mock_fetcher.fetch_records.call_args
    # set_ids may be positional or keyword — check both
    if call.kwargs:
        assert call.kwargs.get("set_ids") == [5]
    else:
        assert [5] in call.args


# ---------------------------------------------------------------------------
# test_get_drawings_meta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_drawings_meta(client_and_mocks):
    """GET /{project_id}/drawings/meta returns metadata for requested drawings."""
    client, *_ = client_and_mocks

    resp = await client.get(
        f"/api/scope-gap/projects/{_PROJECT_ID}/drawings/meta",
        params={"drawing_names": "E-101,P-101"},
    )

    assert resp.status_code == 200
    data = resp.json()

    assert "drawings" in data
    assert "E-101" in data["drawings"]
    assert "P-101" in data["drawings"]
    assert data["drawings"]["E-101"]["discipline"] == "ELECTRICAL"


@pytest.mark.asyncio
async def test_get_drawings_meta_filters_unknown(client_and_mocks):
    """Only known drawing names are returned; unknown ones are silently skipped."""
    client, *_ = client_and_mocks

    resp = await client.get(
        f"/api/scope-gap/projects/{_PROJECT_ID}/drawings/meta",
        params={"drawing_names": "E-101,UNKNOWN-999"},
    )

    assert resp.status_code == 200
    data = resp.json()["drawings"]
    assert "E-101" in data
    assert "UNKNOWN-999" not in data


@pytest.mark.asyncio
async def test_get_drawings_meta_empty_param_returns_400(client_and_mocks):
    """Empty drawing_names query param returns 400."""
    client, *_ = client_and_mocks

    resp = await client.get(
        f"/api/scope-gap/projects/{_PROJECT_ID}/drawings/meta",
        params={"drawing_names": "   "},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# test_get_status_no_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_no_session(client_and_mocks):
    """GET /{project_id}/status returns zero-state when no session exists."""
    client, _, __, ___, mock_session_mgr, ____ = client_and_mocks
    mock_session_mgr.get_by_project_id = MagicMock(return_value=None)

    resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/status")

    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == _PROJECT_ID
    assert data["session_id"] is None
    assert data["overall_progress"] == 0
    assert data["total_items"] == 0
    assert data["trades"] == []


@pytest.mark.asyncio
async def test_get_status_with_session():
    """GET /{project_id}/status reflects trade statuses from an existing session."""
    app, _, __, ___, mock_session_mgr, ____ = _build_test_app()

    session = ProjectSession(project_id=_PROJECT_ID)

    fake_result = MagicMock()
    fake_result.items = ["item1", "item2"]

    ready_container = TradeResultContainer(trade="Electrical")
    ready_container = ready_container.model_copy(update={"latest_result": fake_result})
    session.trade_results["electrical"] = ready_container

    failed_run = TradeRunRecord(status="failed")
    failed_container = TradeResultContainer(trade="Plumbing")
    failed_container = failed_container.model_copy(update={"versions": [failed_run]})
    session.trade_results["plumbing"] = failed_container

    mock_session_mgr.get_by_project_id = MagicMock(return_value=session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(f"/api/scope-gap/projects/{_PROJECT_ID}/status")

    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == _PROJECT_ID
    assert data["session_id"] == session.session_key
    # 1 of 2 trades ready → 50%
    assert data["overall_progress"] == 50

    trade_map = {t["trade"]: t for t in data["trades"]}
    assert trade_map["electrical"]["status"] == "ready"
    assert trade_map["plumbing"]["status"] == "failed"


# ---------------------------------------------------------------------------
# test_run_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_all_returns_202(client_and_mocks):
    """POST /{project_id}/run-all triggers pipeline and returns 202."""
    client, *_ = client_and_mocks

    resp = await client.post(
        f"/api/scope-gap/projects/{_PROJECT_ID}/run-all",
        json={"force_rerun": False},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] is True
    assert data["project_id"] == _PROJECT_ID


@pytest.mark.asyncio
async def test_run_all_with_trades_and_set_ids(client_and_mocks):
    """POST /{project_id}/run-all accepts optional trades and set_ids."""
    client, *_ = client_and_mocks

    resp = await client.post(
        f"/api/scope-gap/projects/{_PROJECT_ID}/run-all",
        json={"force_rerun": True, "set_ids": [1, 2], "trades": ["Electrical"]},
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["force_rerun"] is True
    assert data["set_ids"] == [1, 2]
    assert data["trades"] == ["Electrical"]


# ---------------------------------------------------------------------------
# test_router_metadata
# ---------------------------------------------------------------------------

def test_router_prefix():
    """Router uses the correct API prefix."""
    assert router.prefix == "/api/scope-gap/projects"


def test_router_tags():
    """Router is tagged correctly for OpenAPI docs."""
    assert "scope-gap-projects" in router.tags
