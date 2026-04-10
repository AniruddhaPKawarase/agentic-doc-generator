"""
agents/data_agent.py — Orchestrates data retrieval and context assembly.

Responsibilities:
  1. Call summaryByTrade API for the detected trade
  2. Build a compressed context block via ContextBuilder
  3. Return the context string + fetch stats

Trade validation has been removed — trade detection is now keyword-only
in IntentAgent, so no separate uniqueTrades pre-fetch is needed.
"""

import logging
from typing import Optional

from config import get_settings
from models.schemas import IntentResult
from services.api_client import APIClient
from services.cache_service import CacheService
from services.context_builder import ContextBuilder

logger = logging.getLogger(__name__)
settings = get_settings()


class DataAgent:
    """
    Fetches and compresses project drawing notes for a given trade.
    """

    def __init__(self, api_client: APIClient, cache: CacheService):
        self._api = api_client
        self._cache = cache
        self._builder = ContextBuilder(api_client)

    async def prepare_context(
        self,
        project_id: int,
        intent: IntentResult,
        token_budget: int = None,
        *,
        available_trades: Optional[list[str]] = None,   # kept for interface compat
        project_csi: Optional[list[str]] = None,        # kept for interface compat
        set_ids: Optional[list] = None,
    ) -> tuple[str, dict]:
        """
        Build the compressed context block for (project_id, trade).

        available_trades and project_csi are accepted but ignored —
        they are kept so GenerationAgent needs no changes to its call sites.

        When set_ids is provided, uses summaryByTradeAndSet API per setId.

        Returns:
          context_str  — text block for the LLM prompt
          stats        — dict with record counts and token metrics
        """
        budget = token_budget or settings.max_context_tokens

        context, stats = await self._builder.build(
            project_id=project_id,
            trade=intent.trade,
            csi_divisions=intent.csi_divisions,
            user_query=intent.raw_query,
            token_budget=budget,
            set_ids=set_ids,
        )

        stats["trade"] = intent.trade

        # Expose raw records and API metadata for source index building.
        # ContextBuilder.build() now always populates these — provide safe
        # defaults in case an older or patched version doesn't.
        if "raw_records" not in stats:
            stats["raw_records"] = []
        if "api_metadata" not in stats:
            stats["api_metadata"] = {}

        return context, stats

    async def get_project_metadata(self, project_id: int) -> dict:
        """
        Returns a lightweight metadata stub — no API call required.

        Trade detection is keyword-only; the empty trades/csi_divisions
        lists are safe defaults that GenerationAgent handles gracefully.
        """
        return await self._api.fetch_project_metadata(project_id)