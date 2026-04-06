"""scope_pipeline/routers/highlight_endpoints.py — CRUD endpoints for drawing highlights.

Endpoints:
  POST   /api/scope-gap/highlights          — Create a highlight
  GET    /api/scope-gap/highlights          — List highlights for a drawing
  DELETE /api/scope-gap/highlights/{id}     — Delete a highlight
  PATCH  /api/scope-gap/highlights/{id}     — Update a highlight
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scope_pipeline.models_v2 import Highlight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scope-gap/highlights", tags=["scope-gap-highlights"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class CreateHighlightBody(BaseModel):
    drawing_name: str
    page: int = 1
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    color: str = "#FFEB3B"
    opacity: float = 0.3
    label: str = ""
    trade: Optional[str] = None
    critical: bool = False
    comment: str = ""
    scope_item_id: Optional[str] = None
    scope_item_ids: list[str] = []
    project_id: Any = None  # also accepted in body for flexibility


class UpdateHighlightBody(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    label: Optional[str] = None
    critical: Optional[bool] = None
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_highlight_service(request: Request):
    return request.app.state.highlight_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def create_highlight(
    body: CreateHighlightBody,
    request: Request,
    x_user_id: str = Header(..., alias="X-User-Id"),
    project_id: Optional[Any] = Query(None),
) -> Any:
    """Create a new drawing highlight for the authenticated user."""
    resolved_project_id = project_id or body.project_id
    if resolved_project_id is None:
        raise HTTPException(status_code=422, detail="project_id is required")

    highlight = Highlight(
        drawing_name=body.drawing_name,
        page=body.page,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
        color=body.color,
        opacity=body.opacity,
        label=body.label,
        trade=body.trade,
        critical=body.critical,
        comment=body.comment,
        scope_item_id=body.scope_item_id,
        scope_item_ids=body.scope_item_ids,
    )

    svc = _get_highlight_service(request)
    try:
        result = await svc.create(
            project_id=resolved_project_id,
            user_id=x_user_id,
            highlight=highlight,
        )
        return JSONResponse(status_code=201, content=result.model_dump(mode="json"))
    except Exception as exc:
        logger.exception(
            "create_highlight failed for project=%s user=%s drawing=%s",
            resolved_project_id,
            x_user_id,
            body.drawing_name,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("")
async def list_highlights(
    request: Request,
    project_id: Any = Query(...),
    drawing_name: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> list[dict[str, Any]]:
    """List all highlights for a specific drawing."""
    user_id = x_user_id or "anonymous"
    svc = _get_highlight_service(request)
    try:
        return await svc.list_for_drawing(
            project_id=project_id,
            user_id=user_id,
            drawing_name=drawing_name,
        )
    except Exception as exc:
        logger.exception(
            "list_highlights failed for project=%s user=%s drawing=%s",
            project_id,
            user_id,
            drawing_name,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{highlight_id}")
async def delete_highlight(
    highlight_id: str,
    request: Request,
    project_id: Any = Query(...),
    drawing_name: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Delete a single highlight by id."""
    user_id = x_user_id or "anonymous"
    svc = _get_highlight_service(request)
    try:
        removed = await svc.delete_one(
            project_id=project_id,
            user_id=user_id,
            drawing_name=drawing_name,
            highlight_id=highlight_id,
        )
    except Exception as exc:
        logger.exception(
            "delete_highlight failed for project=%s user=%s drawing=%s id=%s",
            project_id,
            user_id,
            drawing_name,
            highlight_id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Highlight {highlight_id} not found",
        )
    return {"deleted": True}


@router.patch("/{highlight_id}")
async def update_highlight(
    highlight_id: str,
    body: UpdateHighlightBody,
    request: Request,
    project_id: Any = Query(...),
    drawing_name: str = Query(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Apply partial updates to a highlight."""
    user_id = x_user_id or "anonymous"

    # Build the updates dict — only include fields that were explicitly set
    updates = body.model_dump(exclude_none=True)

    svc = _get_highlight_service(request)
    try:
        result = await svc.update_one(
            project_id=project_id,
            user_id=user_id,
            drawing_name=drawing_name,
            highlight_id=highlight_id,
            updates=updates,
        )
    except Exception as exc:
        logger.exception(
            "update_highlight failed for project=%s user=%s drawing=%s id=%s",
            project_id,
            user_id,
            drawing_name,
            highlight_id,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Highlight {highlight_id} not found",
        )
    return result
