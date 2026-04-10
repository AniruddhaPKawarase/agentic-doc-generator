"""
routers/projects.py  —  Project context endpoints.

GET /api/projects/{project_id}/context
  Returns available trades + CSI divisions for a project.
  Used by the frontend to populate the sidebar and chip filters.
"""

from typing import Optional

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


@router.get("/{project_id}/raw-data")
async def get_raw_data(
    project_id: int,
    trade: str,
    set_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 500,
    request: Request = None,
) -> dict:
    """
    Fetch raw API records for UI display.
    Full path: GET /api/projects/{project_id}/raw-data?trade=Civil&set_id=4720
    """
    api_client = request.app.state.api_client
    cache_service = request.app.state.cache

    if set_id:
        records, _, _ = await api_client.get_by_trade_and_set(
            project_id, trade, [set_id], cache_service=cache_service
        )
    else:
        records, _ = await api_client.get_by_trade(
            project_id, trade, cache_service=cache_service
        )

    total = len(records)
    page = records[skip : skip + limit]
    return {
        "success": True,
        "data": {
            "records": page,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + limit) < total,
        },
    }
