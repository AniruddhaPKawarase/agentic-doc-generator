"""
scope_pipeline/services/trade_discovery_service.py — Dynamic trade discovery.

Discovers available trades for a project using a two-strategy approach:
  1. Primary: Fetch all records via summaryByTrade with empty trade string.
  2. Fallback: Probe common construction trades via byTrade endpoint (page 1 only).

The fallback is needed because many MongoDB API deployments require a non-empty
trade parameter and return 0 records when trade="".

Cache strategy:
  Key:  sg_trades:{project_id}           (no set filter)
        sg_trades:{project_id}_{set_id}  (with set filter)
  TTL:  3600 seconds (1 hour)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "sg_trades"
_CACHE_TTL = 3600

# Common construction trades to probe when empty-trade discovery returns nothing.
# Covers CSI MasterFormat divisions 01-33 and common sub-trade names.
_KNOWN_TRADES = [
    "Electrical", "Plumbing", "HVAC", "Structural", "Concrete",
    "Fire Sprinkler", "Fire Protection", "Roofing", "Roofing & Waterproofing",
    "Framing", "Framing Drywall & Insulation", "Drywall",
    "Glass & Glazing", "Glazing", "Painting", "Painting & Coatings",
    "Mechanical", "Architecture", "Civil", "Sitework", "Site Work",
    "Masonry", "Steel", "Metals", "Wood", "Carpentry",
    "Waterproofing", "Insulation", "Doors", "Windows",
    "Finishes", "Flooring", "Ceiling", "Specialties",
    "Equipment", "Furnishings", "Conveying", "Elevator",
    "Fire Alarm", "Communications", "Earthwork", "Demolition",
    "Landscaping", "Utilities", "Paving",
]


class TradeDiscoveryService:
    """Discovers unique trades available for a project via the drawing API."""

    def __init__(self, api_client: Any, cache_service: Any) -> None:
        self._api = api_client
        self._cache = cache_service

    async def discover_trades(
        self,
        project_id: int,
        set_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Return unique trades and record counts for a project.

        Strategy (in priority order):
          1. uniqueTrades API — single fast call, returns all trade names.
          2. summaryByTrade with empty trade (works on some API deployments).
          3. Probe known trades via byTrade page 1 (slowest fallback).

        Args:
            project_id: Integer project identifier.
            set_id:     Optional set filter.

        Returns:
            Sorted list of dicts: [{"trade": "Electrical", "record_count": 107}, ...]
        """
        cache_key = _build_cache_key(project_id, set_id)

        # -- L2 cache lookup ------------------------------------------------
        cached_raw = await self._cache.get(cache_key)
        if cached_raw is not None:
            deserialized = _deserialize(cached_raw)
            if deserialized:
                logger.debug(
                    "Cache hit trades project=%s set_id=%s (%d trades)",
                    project_id, set_id, len(deserialized),
                )
                return deserialized

        trade_counts: dict[str, int] = {}

        # -- Strategy 1: uniqueTrades API (fast, single call) ---------------
        if set_id is None:
            try:
                unique_trades = await self._api.get_unique_trades(project_id)
                if unique_trades:
                    # uniqueTrades doesn't return counts — use 1 as placeholder
                    trade_counts = {t: 1 for t in unique_trades}
                    logger.info(
                        "discover_trades: uniqueTrades API returned %d trades for project=%s",
                        len(trade_counts), project_id,
                    )
            except Exception as exc:
                logger.warning(
                    "discover_trades: uniqueTrades failed for project=%s: %s",
                    project_id, exc,
                )

        # -- Strategy 2: empty-trade fetch ----------------------------------
        if not trade_counts:
            records = await _fetch_all_records(self._api, project_id, set_id)
            for rec in records:
                trade_names = _extract_trade_names(rec)
                for name in trade_names:
                    trade_counts[name] = trade_counts.get(name, 0) + 1

        # -- Strategy 3: probe known trades (slowest fallback) --------------
        if not trade_counts:
            logger.info(
                "discover_trades: falling back to trade probing for project=%s",
                project_id,
            )
            trade_counts = await self._probe_known_trades(project_id, set_id)

        result = [
            {"trade": trade, "record_count": count}
            for trade, count in sorted(trade_counts.items())
        ]

        # -- Persist to cache ------------------------------------------------
        if result:
            await self._cache.set(cache_key, json.dumps(result), ttl=_CACHE_TTL)

        logger.info(
            "discover_trades project=%s set_id=%s → %d trades",
            project_id, set_id, len(result),
        )
        return result

    async def _probe_known_trades(
        self,
        project_id: int,
        set_id: Optional[int] = None,
    ) -> dict[str, int]:
        """Probe common trades by checking page 1 of byTrade endpoint.

        Runs all probes in parallel for speed (~5-8 seconds total).
        Returns dict of trade_name -> record_count for trades with data.
        """
        async def _check_one(trade: str) -> tuple[str, int]:
            count = await self._api.probe_trade_exists(project_id, trade, set_id)
            return trade, count

        results = await asyncio.gather(
            *[_check_one(t) for t in _KNOWN_TRADES],
            return_exceptions=True,
        )

        trade_counts: dict[str, int] = {}
        for item in results:
            if isinstance(item, Exception):
                continue
            trade_name, count = item
            if count > 0:
                trade_counts[trade_name] = count

        logger.info(
            "Trade probing for project=%s: found %d trades with data out of %d probed",
            project_id, len(trade_counts), len(_KNOWN_TRADES),
        )
        return trade_counts


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_cache_key(project_id: int, set_id: Optional[int]) -> str:
    if set_id is not None:
        return f"{_CACHE_KEY_PREFIX}:{project_id}_{set_id}"
    return f"{_CACHE_KEY_PREFIX}:{project_id}"


async def _fetch_all_records(
    api_client: Any,
    project_id: int,
    set_id: Optional[int],
) -> list[dict]:
    """
    Fetch records using the empty-trade trick.

    When trade="" the API returns records across all trades on some deployments.
    Falls back gracefully to an empty list on any exception.
    """
    try:
        if set_id is not None:
            records, _ = await api_client.get_summary_by_trade_and_set(
                project_id, "", [set_id]
            )
        else:
            records = await api_client.get_summary_by_trade(project_id, "")
        return records if isinstance(records, list) else []
    except Exception as exc:
        logger.warning(
            "discover_trades: empty-trade fetch failed for project=%s set_id=%s: %s",
            project_id, set_id, exc,
        )
        return []


def _extract_trade_names(record: dict) -> list[str]:
    """
    Extract all trade name strings from a single record.

    Resolution order:
    1. `setTrade` scalar field (single trade string).
    2. `trades` list field (multi-value trade list).

    Returns a deduplicated list of non-empty, stripped trade strings.
    """
    names: list[str] = []
    seen: set[str] = set()

    # Primary: setTrade scalar
    set_trade = (record.get("setTrade") or "").strip()
    if set_trade and set_trade not in seen:
        names.append(set_trade)
        seen.add(set_trade)

    # Secondary: trades list
    trades_list = record.get("trades")
    if isinstance(trades_list, list):
        for item in trades_list:
            name = (item or "").strip() if isinstance(item, str) else ""
            if name and name not in seen:
                names.append(name)
                seen.add(name)

    return names


def _deserialize(value: Any) -> list[dict]:
    """Safely deserialize a cached value to list[dict]."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return []
