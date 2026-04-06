"""tests/scope_pipeline/test_highlight_endpoints.py — Tests for highlight CRUD endpoints.

Uses httpx.AsyncClient + ASGITransport with a minimal FastAPI app and a
mocked highlight_service bound to app.state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from scope_pipeline.models_v2 import Highlight
from scope_pipeline.routers.highlight_endpoints import router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_highlight(drawing_name: str = "E-101") -> Highlight:
    return Highlight(
        drawing_name=drawing_name,
        page=1,
        x=0.1,
        y=0.2,
        width=0.3,
        height=0.1,
        color="#FFEB3B",
        label="Test highlight",
    )


def _make_service(
    create_return: Highlight | None = None,
    list_return: list | None = None,
    delete_return: bool = True,
    update_return: dict | None = None,
) -> MagicMock:
    svc = MagicMock()
    svc.create = AsyncMock(return_value=create_return)
    svc.list_for_drawing = AsyncMock(return_value=list_return if list_return is not None else [])
    svc.delete_one = AsyncMock(return_value=delete_return)
    svc.update_one = AsyncMock(return_value=update_return)
    return svc


def _build_app(highlight_service: MagicMock) -> FastAPI:
    """Return a minimal FastAPI app with the highlight router and mocked service."""
    app = FastAPI()
    app.include_router(router)
    app.state.highlight_service = highlight_service
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client_with_hl():
    """Fixture: (AsyncClient, Highlight, mock_service) for create/list tests."""
    hl = _make_highlight("E-101")
    svc = _make_service(
        create_return=hl,
        list_return=[hl.model_dump(mode="json")],
    )
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, hl, svc


# ---------------------------------------------------------------------------
# test_create_highlight
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_highlight(client_with_hl):
    """POST / returns 201 with the created highlight JSON."""
    client, hl, svc = client_with_hl

    resp = await client.post(
        "/api/scope-gap/highlights",
        params={"project_id": 7166},
        headers={"X-User-Id": "user_abc"},
        json={
            "drawing_name": "E-101",
            "page": 1,
            "x": 0.1,
            "y": 0.2,
            "width": 0.3,
            "height": 0.1,
            "color": "#FFEB3B",
            "label": "Test highlight",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == hl.id
    assert data["drawing_name"] == "E-101"
    assert data["label"] == "Test highlight"
    svc.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_highlight_missing_user_id():
    """POST / without X-User-Id header returns 422."""
    svc = _make_service()
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/scope-gap/highlights",
            params={"project_id": 7166},
            json={"drawing_name": "E-101"},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# test_list_highlights
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_highlights(client_with_hl):
    """GET / returns 200 with a list of highlight dicts."""
    client, hl, svc = client_with_hl

    resp = await client.get(
        "/api/scope-gap/highlights",
        params={"project_id": 7166, "drawing_name": "E-101"},
        headers={"X-User-Id": "user_abc"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == hl.id
    svc.list_for_drawing.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_highlights_empty():
    """GET / returns 200 with empty list when no highlights exist."""
    svc = _make_service(list_return=[])
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/scope-gap/highlights",
            params={"project_id": 7166, "drawing_name": "E-999"},
            headers={"X-User-Id": "user_abc"},
        )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_highlights_missing_params():
    """GET / without required drawing_name returns 422."""
    svc = _make_service()
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Missing drawing_name
        resp = await client.get(
            "/api/scope-gap/highlights",
            params={"project_id": 7166},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# test_delete_not_found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_not_found():
    """DELETE /{id} returns 404 when highlight does not exist."""
    svc = _make_service(delete_return=False)
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(
            "/api/scope-gap/highlights/hl_nonexistent",
            params={"project_id": 7166, "drawing_name": "E-101"},
            headers={"X-User-Id": "user_abc"},
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_success():
    """DELETE /{id} returns {"deleted": true} when highlight exists."""
    svc = _make_service(delete_return=True)
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(
            "/api/scope-gap/highlights/hl_abc123",
            params={"project_id": 7166, "drawing_name": "E-101"},
            headers={"X-User-Id": "user_abc"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}


# ---------------------------------------------------------------------------
# test_update_highlight
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_highlight_success():
    """PATCH /{id} returns the updated highlight dict on success."""
    hl = _make_highlight("E-101")
    updated_dict = {**hl.model_dump(mode="json"), "label": "Updated label"}
    svc = _make_service(update_return=updated_dict)
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.patch(
            f"/api/scope-gap/highlights/{hl.id}",
            params={"project_id": 7166, "drawing_name": "E-101"},
            headers={"X-User-Id": "user_abc"},
            json={"label": "Updated label"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "Updated label"
    assert data["id"] == hl.id


@pytest.mark.asyncio
async def test_update_highlight_not_found():
    """PATCH /{id} returns 404 when highlight does not exist."""
    svc = _make_service(update_return=None)
    app = _build_app(svc)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.patch(
            "/api/scope-gap/highlights/hl_nonexistent",
            params={"project_id": 7166, "drawing_name": "E-101"},
            headers={"X-User-Id": "user_abc"},
            json={"label": "Whatever"},
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
