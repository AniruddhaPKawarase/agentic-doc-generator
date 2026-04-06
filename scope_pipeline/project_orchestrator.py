"""scope_pipeline/project_orchestrator.py — Multi-trade project orchestrator.

Wraps ScopeGapPipeline to run all (or selected) trades for a project in
parallel, with adaptive scheduling via asyncio.Semaphore, freshness-based
skipping, and per-trade + project-level SSE events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from scope_pipeline.models import ScopeGapRequest, ScopeGapResult
from scope_pipeline.models_v2 import ProjectSession, TradeResultContainer, TradeRunRecord
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)


class ProjectOrchestrator:
    """Run the full scope-gap pipeline across all trades for a project.

    Wraps ScopeGapPipeline (single-trade) and executes trades in parallel,
    bounded by *trade_concurrency*.  Results are stored into a ProjectSession
    via ProjectSessionManager with 3-layer persistence.

    Args:
        pipeline:               ScopeGapPipeline instance (single-trade runner).
        session_manager:        ProjectSessionManager for loading / saving sessions.
        trade_discovery:        Any object with async ``discover_trades(project_id) -> list[str]``.
        color_service:          TradeColorService (or compatible) for color metadata.
        trade_concurrency:      Maximum number of trades running simultaneously.
        result_freshness_ttl:   Seconds before a cached trade result is considered stale.
        trade_pipeline_timeout: Per-trade hard timeout in seconds.
    """

    def __init__(
        self,
        pipeline: Any,
        session_manager: Any,
        trade_discovery: Any,
        color_service: Any,
        trade_concurrency: int = 10,
        result_freshness_ttl: int = 86400,
        trade_pipeline_timeout: int = 600,
    ) -> None:
        self._pipeline = pipeline
        self._session_mgr = session_manager
        self._trade_discovery = trade_discovery
        self._color_service = color_service
        self._trade_concurrency = trade_concurrency
        self._freshness_ttl = result_freshness_ttl
        self._trade_timeout = trade_pipeline_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_all_trades(
        self,
        project_id: int,
        emitter: ProgressEmitter,
        set_ids: Optional[list[Union[int, str]]] = None,
        force_rerun: bool = False,
        specific_trades: Optional[list[str]] = None,
        project_name: str = "",
    ) -> ProjectSession:
        """Run the pipeline for every applicable trade in the project.

        Steps:
        1. Load or create the ProjectSession.
        2. Discover trades via trade_discovery.
        3. Filter out fresh trades (unless force_rerun=True).
        4. Emit ``session_loaded`` SSE event with counts.
        5. Run remaining trades in parallel (bounded by Semaphore).
        6. Persist the updated session.
        7. Emit ``all_complete`` SSE event.

        Returns:
            The updated ProjectSession.
        """
        # Step 1: Load / create project session
        session = await self._session_mgr.get_or_create(
            project_id=project_id,
            set_ids=set_ids,
            project_name=project_name,
        )

        # Step 2: Discover trades (returns list[dict] with "trade" + "record_count")
        raw_trades = await self._trade_discovery.discover_trades(project_id)
        all_trades: list[str] = [
            entry["trade"] if isinstance(entry, dict) else str(entry)
            for entry in raw_trades
            if (entry.get("trade") if isinstance(entry, dict) else entry)
        ]

        # Apply specific_trades filter if requested
        if specific_trades:
            lower_specific = {t.lower() for t in specific_trades}
            all_trades = [t for t in all_trades if t.lower() in lower_specific]

        # Step 3: Determine which trades need to run
        now = datetime.now(timezone.utc)
        fresh_trades: list[str] = []
        stale_trades: list[str] = []

        for trade in all_trades:
            if force_rerun:
                stale_trades.append(trade)
                continue

            container = session.trade_results.get(trade.lower())
            if container and container.versions:
                last_run = container.versions[-1]
                if last_run.completed_at is not None:
                    age_seconds = (now - last_run.completed_at).total_seconds()
                    if age_seconds < self._freshness_ttl:
                        fresh_trades.append(trade)
                        continue
            stale_trades.append(trade)

        # Step 4: Emit session_loaded event
        emitter.emit("session_loaded", {
            "project_id": project_id,
            "total_trades": len(all_trades),
            "cached_count": len(fresh_trades),
            "to_run_count": len(stale_trades),
            "fresh_trades": fresh_trades,
            "pending_trades": stale_trades,
        })

        # Step 5: Run stale trades in parallel with bounded concurrency
        if stale_trades:
            semaphore = asyncio.Semaphore(self._trade_concurrency)
            tasks = [
                self._run_single_trade(
                    session=session,
                    project_id=project_id,
                    trade=trade,
                    set_ids=set_ids,
                    project_name=project_name,
                    parent_emitter=emitter,
                    semaphore=semaphore,
                )
                for trade in stale_trades
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Step 6: Persist session
        await self._session_mgr.update(session)

        # Step 7: Emit all_complete event
        emitter.emit("all_complete", {
            "project_id": project_id,
            "total_trades": len(all_trades),
            "completed_trades": [
                t for t in all_trades
                if session.trade_results.get(t.lower()) is not None
                and session.trade_results[t.lower()].versions
                and session.trade_results[t.lower()].versions[-1].status == "complete"
            ],
            "failed_trades": [
                t for t in all_trades
                if session.trade_results.get(t.lower()) is not None
                and session.trade_results[t.lower()].versions
                and session.trade_results[t.lower()].versions[-1].status == "failed"
            ],
        })

        return session

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_single_trade(
        self,
        session: ProjectSession,
        project_id: int,
        trade: str,
        set_ids: Optional[list[Union[int, str]]],
        project_name: str,
        parent_emitter: ProgressEmitter,
        semaphore: asyncio.Semaphore,
    ) -> None:
        """Acquire semaphore slot and run the pipeline for a single trade."""
        async with semaphore:
            trade_emitter = ProgressEmitter()
            request = ScopeGapRequest(
                project_id=project_id,
                trade=trade,
                set_ids=set_ids,
            )

            try:
                result: ScopeGapResult = await asyncio.wait_for(
                    self._pipeline.run(request, trade_emitter, project_name),
                    timeout=self._trade_timeout,
                )

                # Build successful run record
                record = TradeRunRecord(
                    status="complete",
                    completed_at=datetime.now(timezone.utc),
                    items_count=len(result.items),
                    ambiguities_count=len(result.ambiguities),
                    gotchas_count=len(result.gotchas),
                    completeness_pct=result.completeness.overall_pct,
                    token_usage=result.pipeline_stats.tokens_used,
                    cost_usd=result.pipeline_stats.estimated_cost_usd,
                    documents=result.documents,
                    result=result,
                )

                trade_key = trade.lower()
                container = session.trade_results.get(trade_key) or TradeResultContainer(trade=trade_key)
                session.trade_results[trade_key] = container.add_run(record)

                parent_emitter.emit("trade_complete", {
                    "project_id": project_id,
                    "trade": trade,
                    "items_count": record.items_count,
                    "completeness_pct": record.completeness_pct,
                })

            except Exception as exc:
                logger.exception(
                    "Trade pipeline failed for project=%s trade=%s",
                    project_id, trade,
                )
                self._record_failure(session, trade, exc)
                parent_emitter.emit("trade_failed", {
                    "project_id": project_id,
                    "trade": trade,
                    "error": str(exc),
                })

    def _record_failure(
        self,
        session: ProjectSession,
        trade: str,
        error: Exception,
    ) -> None:
        """Record a failed trade run in the session (creates container if needed)."""
        record = TradeRunRecord(
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error=str(error),
        )
        trade_key = trade.lower()
        container = session.trade_results.get(trade_key) or TradeResultContainer(trade=trade_key)
        session.trade_results[trade_key] = container.add_run(record)
