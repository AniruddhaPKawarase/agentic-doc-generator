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
    try:
        from services.cache_service import CacheService

        cache_key = CacheService.api_key("project_context", project_id)
        cached = await cache.get(cache_key)
        if cached:
            return ProjectContextResponse(**cached, cached=True)

        # Parallel fetch
        import asyncio
        trades_task = api_client.get_unique_trades(project_id)
        csi_task = api_client.get_unique_csi_divisions(project_id)
        text_count_task = api_client.get_unique_text_count_hint(project_id)

        trades, csi_divisions, text_count = await asyncio.gather(
            trades_task, csi_task, text_count_task
        )

        result = ProjectContextResponse(
            project_id=project_id,
            trades=[t for t in trades if t],
            csi_divisions=[c for c in csi_divisions if c],
            total_text_items=int(text_count),
            cached=False,
        )

        await cache.set(cache_key, result.model_dump(), ttl=1800)
        return result

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
