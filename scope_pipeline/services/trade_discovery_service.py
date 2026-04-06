"""
scope_pipeline/services/trade_discovery_service.py — Dynamic trade discovery.

Discovers available trades for a project by fetching all drawing records
and extracting unique trade names from the `setTrade` or `trades` fields.

Cache strategy:
  Key:  sg_trades:{project_id}           (no set filter)
        sg_trades:{project_id}_{set_id}  (with set filter)
  TTL:  3600 seconds (1 hour)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "sg_trades"
_CACHE_TTL = 3600


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

        Args:
            project_id: Integer project identifier.
            set_id:     Optional set filter. When provided, only records for
                        that set are considered.

        Returns:
            Sorted list of dicts: [{"trade": "Electrical", "record_count": 107}, ...]
            Empty list if the API returns no records or the call fails.
        """
        cache_key = _build_cache_key(project_id, set_id)

        # -- L2 cache lookup ------------------------------------------------
        cached_raw = await self._cache.get(cache_key)
        if cached_raw is not None:
            logger.debug(
                "Cache hit trades project=%s set_id=%s", project_id, set_id
            )
            return _deserialize(cached_raw)

        # -- Fetch all records with empty trade string (returns everything) --
        records = await _fetch_all_records(self._api, project_id, set_id)

        # -- Extract unique trades and count records per trade ---------------
        trade_counts: dict[str, int] = {}
        for rec in records:
            trade_names = _extract_trade_names(rec)
            for name in trade_names:
                trade_counts[name] = trade_counts.get(name, 0) + 1

        result = [
            {"trade": trade, "record_count": count}
            for trade, count in sorted(trade_counts.items())
        ]

        # -- Persist to cache ------------------------------------------------
        await self._cache.set(cache_key, json.dumps(result), ttl=_CACHE_TTL)

        logger.info(
            "discover_trades project=%s set_id=%s → %d trades from %d records",
            project_id, set_id, len(result), len(records),
        )
        return result


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

    When trade="" the API returns records across all trades.
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
            "discover_trades: API call failed for project=%s set_id=%s: %s",
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
