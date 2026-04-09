"""
scope_pipeline/routers/project_endpoints.py — Project-level API endpoints.

Endpoints:
  - GET  /{project_id}/trades         — List trades with status + color
  - GET  /{project_id}/trade-colors   — Trade color palette
  - GET  /{project_id}/drawings       — Categorized drawing tree
  - GET  /{project_id}/drawings/meta  — Batch drawing metadata
  - GET  /{project_id}/status         — Pipeline status dashboard
  - POST /{project_id}/run-all        — Trigger all-trades pipeline (202 Accepted)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/scope-gap/projects",
    tags=["scope-gap-projects"],
)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class RunAllBody(BaseModel):
    set_ids: Optional[List[int]] = None
    force_rerun: bool = False
    trades: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Dependency helpers — access services via request.app.state
# ---------------------------------------------------------------------------

def _get_trade_discovery(request: Request):
    return request.app.state.trade_discovery_service


def _get_trade_color(request: Request):
    return request.app.state.trade_color_service


def _get_drawing_index(request: Request):
    return request.app.state.drawing_index_service


def _get_project_session_manager(request: Request):
    return request.app.state.project_session_manager


def _get_scope_data_fetcher(request: Request):
    return request.app.state.scope_data_fetcher


def _get_project_orchestrator(request: Request):
    return request.app.state.project_orchestrator


def _get_api_client(request: Request):
    return request.app.state.api_client


# ---------------------------------------------------------------------------
# GET /{project_id}/trades
# ---------------------------------------------------------------------------

@router.get("/{project_id}/trades")
async def get_trades(
    project_id: int,
    request: Request,
    set_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """List trades with status and color for a project.

    Status resolution per trade:
      - "ready"   — trade has a latest_result in the project session
      - "failed"  — last run for that trade failed
      - "pending" — default, no result yet
    """
    trade_discovery = _get_trade_discovery(request)
    trade_color = _get_trade_color(request)
    session_mgr = _get_project_session_manager(request)

    try:
        raw_trades: list[dict] = await trade_discovery.discover_trades(
            project_id=project_id,
            set_id=set_id,
        )
    except Exception as exc:
        logger.exception("discover_trades failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Load existing session for status information (may be None)
    session = session_mgr.get_by_project_id(project_id)

    trades_out: list[dict] = []
    total_records = 0

    for entry in raw_trades:
        trade_name: str = entry.get("trade", "")
        record_count: int = entry.get("record_count", 0)
        total_records += record_count

        # Determine status from session
        status = _resolve_trade_status(session, trade_name)

        color_info = trade_color.get_color(trade_name)
        trades_out.append(
            {
                "trade": trade_name,
                "record_count": record_count,
                "status": status,
                "color": color_info,
            }
        )

    return {
        "project_id": project_id,
        "trades": trades_out,
        "total_trades": len(trades_out),
        "total_records": total_records,
    }


# ---------------------------------------------------------------------------
# GET /{project_id}/trade-colors
# ---------------------------------------------------------------------------

@router.get("/{project_id}/trade-colors")
async def get_trade_colors(
    project_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return the full color palette for all trades in the project."""
    trade_discovery = _get_trade_discovery(request)
    trade_color = _get_trade_color(request)

    try:
        raw_trades: list[dict] = await trade_discovery.discover_trades(
            project_id=project_id,
        )
    except Exception as exc:
        logger.exception("discover_trades failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    trade_names = [entry.get("trade", "") for entry in raw_trades if entry.get("trade")]
    colors = trade_color.get_all_colors(trade_names)

    return {"colors": colors}


# ---------------------------------------------------------------------------
# GET /{project_id}/drawings
# ---------------------------------------------------------------------------

@router.get("/{project_id}/drawings")
async def get_drawings(
    project_id: int,
    request: Request,
    set_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """Return a categorized drawing tree grouped by discipline.

    Strategy: try empty-trade fetch first (returns all records on some APIs).
    If that returns nothing, fall back to fetching per discovered trade and
    merging — mirrors the fallback in TradeDiscoveryService.
    """
    scope_data_fetcher = _get_scope_data_fetcher(request)
    drawing_index = _get_drawing_index(request)
    trade_discovery = _get_trade_discovery(request)

    set_ids = [set_id] if set_id is not None else None

    try:
        fetch_result = await scope_data_fetcher.fetch_records(
            project_id=project_id,
            trade="",
            set_ids=set_ids,
        )
    except Exception as exc:
        logger.exception("fetch_records failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    records: list[dict] = fetch_result.get("records", [])
    seen_ids: set[str] = {r.get("_id", "") for r in records if r.get("_id")}

    # Always supplement with per-trade page1 fetches.  The empty-trade path
    # may return a partial dataset (e.g. 621 of 2707 records), and some API
    # deployments return 0 records for trade="".  Page 1 per trade adds
    # ~50 records × N trades, giving broad drawing-name coverage without
    # exhaustively paginating all records.
    try:
        api_client = _get_api_client(request)
        raw_trades = await trade_discovery.discover_trades(
            project_id=project_id, set_id=set_id,
        )
        trade_names = [t.get("trade", "") for t in raw_trades if t.get("trade")]

        if trade_names:
            logger.info(
                "get_drawings: supplementing with page-1-per-trade for %d trades, project=%s",
                len(trade_names), project_id,
            )
            batches = await asyncio.gather(*[
                api_client.fetch_page1(project_id, t, set_id)
                for t in trade_names
            ])

            for batch in batches:
                for rec in batch:
                    rec_id = rec.get("_id", "")
                    if rec_id and rec_id not in seen_ids:
                        records.append(rec)
                        seen_ids.add(rec_id)
                    elif not rec_id:
                        records.append(rec)
    except Exception as exc:
        logger.warning(
            "get_drawings: per-trade supplement failed for project=%s: %s",
            project_id, exc,
        )

    categories = drawing_index.build_categorized_tree(records)

    total_drawings = 0
    total_specs = 0
    for discipline_data in categories.values():
        total_drawings += len(discipline_data.get("drawings", []))
        total_specs += len(discipline_data.get("specs", []))

    return {
        "project_id": project_id,
        "total_drawings": total_drawings,
        "total_specs": total_specs,
        "categories": categories,
    }


# ---------------------------------------------------------------------------
# GET /{project_id}/drawings/meta
# ---------------------------------------------------------------------------

@router.get("/{project_id}/drawings/meta")
async def get_drawings_meta(
    project_id: int,
    request: Request,
    drawing_names: str = Query(..., description="Comma-separated drawing names"),
) -> dict[str, Any]:
    """Return metadata for a batch of drawing names."""
    scope_data_fetcher = _get_scope_data_fetcher(request)
    drawing_index = _get_drawing_index(request)

    name_list = [n.strip() for n in drawing_names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(status_code=400, detail="drawing_names query param is empty")

    try:
        fetch_result = await scope_data_fetcher.fetch_records(
            project_id=project_id,
            trade="",
            set_ids=None,
        )
    except Exception as exc:
        logger.exception("fetch_records failed for project=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    records: list[dict] = fetch_result.get("records", [])
    full_metadata = drawing_index.build_drawing_metadata(records)

    # Filter to only the requested drawing names
    result_meta = {
        name: full_metadata[name]
        for name in name_list
        if name in full_metadata
    }

    return {"drawings": result_meta}


# ---------------------------------------------------------------------------
# GET /{project_id}/status
# ---------------------------------------------------------------------------

@router.get("/{project_id}/status")
async def get_status(
    project_id: int,
    request: Request,
) -> dict[str, Any]:
    """Return the pipeline status dashboard for a project."""
    session_mgr = _get_project_session_manager(request)
    session = session_mgr.get_by_project_id(project_id)

    if session is None:
        return {
            "project_id": project_id,
            "session_id": None,
            "overall_progress": 0,
            "total_items": 0,
            "trades": [],
        }

    trade_statuses: list[dict] = []
    total_items = 0

    for trade_name, container in session.trade_results.items():
        versions = container.versions
        latest_run = versions[-1] if versions else None

        if container.latest_result is not None:
            status = "ready"
        elif latest_run and latest_run.status == "failed":
            status = "failed"
        else:
            status = "pending"

        latest = container.latest_result
        result_items = getattr(latest, "items", None) if latest else None
        items_count = len(result_items) if result_items is not None else 0
        total_items += items_count

        trade_statuses.append(
            {
                "trade": trade_name,
                "status": status,
                "items_count": items_count,
                "run_id": latest_run.run_id if latest_run else None,
            }
        )

    ready_count = sum(1 for t in trade_statuses if t["status"] == "ready")
    overall_progress = (
        round(ready_count / len(trade_statuses) * 100)
        if trade_statuses
        else 0
    )

    return {
        "project_id": project_id,
        "session_id": session.session_key,
        "overall_progress": overall_progress,
        "total_items": total_items,
        "trades": trade_statuses,
    }


# ---------------------------------------------------------------------------
# POST /{project_id}/run-all
# ---------------------------------------------------------------------------

@router.post("/{project_id}/run-all")
async def run_all(
    project_id: int,
    body: RunAllBody,
    request: Request,
) -> JSONResponse:
    """Trigger the full scope-gap pipeline for all (or selected) trades.

    Returns 202 Accepted immediately; the orchestrator runs in the background.
    """
    orchestrator = _get_project_orchestrator(request)

    try:
        from scope_pipeline.services.progress_emitter import ProgressEmitter

        emitter = ProgressEmitter()

        import asyncio

        asyncio.create_task(
            orchestrator.run_all_trades(
                project_id=project_id,
                emitter=emitter,
                set_ids=body.set_ids,
                force_rerun=body.force_rerun,
                specific_trades=body.trades,
                project_name="",
            )
        )
    except Exception as exc:
        logger.exception("run_all failed to launch for project=%s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "project_id": project_id,
            "force_rerun": body.force_rerun,
            "set_ids": body.set_ids,
            "trades": body.trades,
            "message": "Pipeline triggered for all trades. Poll /status for progress.",
        },
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_trade_status(session: Any, trade_name: str) -> str:
    """Derive trade pipeline status from the project session.

    Returns:
        "ready"   — trade has a latest_result
        "failed"  — last run for trade has status 'failed'
        "pending" — default fallback
    """
    if session is None:
        return "pending"

    key = trade_name.lower()
    container = session.trade_results.get(key)
    if container is None:
        return "pending"

    if container.latest_result is not None:
        return "ready"

    versions = container.versions
    if versions and versions[-1].status == "failed":
        return "failed"

    return "pending"
