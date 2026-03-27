"""
routers/projects.py  —  Project context endpoints.

GET /api/projects/{project_id}/context
  Returns available trades + CSI divisions for a project.
  Used by the frontend to populate the sidebar and chip filters.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request

from models.schemas import ProjectContextResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_api_client(request: Request):
    return request.app.state.api_client


def get_cache(request: Request):
    return request.app.state.cache


@router.get("/{project_id}/context", response_model=ProjectContextResponse)
async def get_project_context(
    project_id: int,
    api_client=Depends(get_api_client),
    cache=Depends(get_cache),
):
    """
    Load available trades, CSI divisions, and text count for a project.
    Fully cached — safe to call on every project switch.
    """
    # Note: get_unique_trades/csi_divisions/text_count_hint methods were removed
    # in the Single-API Refactor (2026-03-09). This endpoint now returns a stub
    # response. The frontend should derive trades from the summaryByTrade API.
    return ProjectContextResponse(
        project_id=project_id,
        trades=[],
        csi_divisions=[],
        total_text_items=0,
        cached=False,
    )
