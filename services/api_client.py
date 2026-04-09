"""
Async HTTP client — summaryByTrade + summaryByTradeAndSet endpoints with PARALLEL pagination.

Drawing-note data is retrieved through one of two endpoints:
  GET /api/drawingText/summaryByTrade?projectId={id}&trade={trade}
  GET /api/drawingText/summaryByTradeAndSet?projectId={id}&trade={trade}&setId={setId}

Response shape (identical for both):
  { "success": true, "data": { "list": [ {_id, projectId, setName, setTrade,
    drawingName, drawingTitle, text, csi_division, trades}, ... ] } }

OPTIMIZATION v2 (2026-03-18):
  Root cause of 20-min latency: API hard-caps at 50 records/page (ignores limit param).
  Each page round-trip to mongo.ifieldsmart.com = ~5.8s.
  11,360 Electrical records = 228 pages × 5.8s = 22 minutes sequential.

  Fix: dispatch ALL pages concurrently using asyncio.gather + Semaphore.
    228 pages / 30 concurrent = 8 rounds × 5.8s ≈ 50s (v3: concurrency raised 15→30).

  Retry logic: exponential backoff (1s, 2s) on HTTP 429/503 or timeout, 3 attempts max.

RECORD COMPLETENESS FIX v3 (2026-03-18):
  Root cause of 50 vs 154 records bug:
    The API returns {"data": {"list": [...50 items...], "count": 50}} where "count" is the
    PAGE count, not the total record count.  _extract_total() read this as total=50, then
    len(first_page)=50 >= total=50 triggered an early exit — returning only page 1.

  Fix: termination is now based solely on EMPTY PAGE detection, never on "total":
    - A partial first page (len < api_page_size) → guaranteed single page, done immediately.
    - A full first page → fetch further pages in parallel batches until a batch returns
      zero new records (empty pages = definitive end of data).
    - "total" is used only for informational logging, never for stopping.
"""

import asyncio
import logging
import math
import time
from typing import Any, Optional, Union

import httpx

from config import get_settings
from services.cache_service import CacheService

logger = logging.getLogger(__name__)
settings = get_settings()


class APIClient:
    """Wraps the summaryByTrade API with caching and PARALLEL full pagination."""

    def __init__(self, cache: CacheService):
        self._cache = cache
        self._base_url = settings.api_base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.api_auth_token:
            self._headers["Authorization"] = f"Bearer {settings.api_auth_token}"
        self._http: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=httpx.Timeout(settings.api_timeout_seconds, connect=5.0),
            # Allow enough connections for parallel page fetching
            limits=httpx.Limits(
                max_connections=settings.parallel_fetch_concurrency + 5,
                max_keepalive_connections=settings.parallel_fetch_concurrency,
            ),
            follow_redirects=True,
        )

    async def disconnect(self) -> None:
        if self._http:
            await self._http.aclose()

    async def get_summary_by_trade(
        self,
        project_id: int,
        trade: str,
        bypass_cache: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Fetch ALL drawing-note summaries for (project_id, trade).

        Page 1 fetched serially to discover total count, then ALL remaining
        pages dispatched in parallel with asyncio.gather + Semaphore.
        Results cached for cache_ttl_summary_data seconds (default 5 min).
        """
        cache_key = CacheService.api_key("summary", project_id, trade.lower())
        if not bypass_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    "Cache hit summary project=%s trade=%s (%d records)",
                    project_id, trade, len(cached),
                )
                return cached

        records = await self._fetch_all_pages(project_id, trade)

        cap = settings.max_summary_records
        if cap and len(records) > cap:
            logger.info(
                "Capping %d records to %d for project=%s trade=%s",
                len(records), cap, project_id, trade,
            )
            records = records[:cap]

        await self._cache.set(cache_key, records, ttl=settings.cache_ttl_summary_data)
        return records

    async def get_summary_by_trade_and_set(
        self,
        project_id: int,
        trade: str,
        set_ids: list[Union[int, str]],
        bypass_cache: bool = False,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Fetch drawing-note summaries filtered by trade AND setId(s).

        For multiple set_ids, fires parallel API calls (one per setId) and
        merges results with _id deduplication.

        Returns:
          (records, set_names) — records is the merged list; set_names is the
          list of unique setName values extracted from the response data.
        """
        set_ids_key = "_".join(str(s) for s in sorted(str(s) for s in set_ids))
        cache_key = CacheService.api_key("summary_set", project_id, f"{trade.lower()}:{set_ids_key}")
        if not bypass_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                records = cached.get("records", [])
                set_names = cached.get("set_names", [])
                logger.debug(
                    "Cache hit summary_set project=%s trade=%s set_ids=%s (%d records)",
                    project_id, trade, set_ids, len(records),
                )
                return records, set_names

        # Fire parallel fetches — one per setId
        async def fetch_one_set(set_id: Union[int, str]) -> list[dict[str, Any]]:
            return await self._fetch_all_pages(
                project_id,
                trade,
                set_id=set_id,
            )

        results = await asyncio.gather(*[fetch_one_set(sid) for sid in set_ids])

        # Merge and dedup by _id
        seen_ids: set[str] = set()
        merged: list[dict[str, Any]] = []
        set_names_set: set[str] = set()

        for result_batch in results:
            for rec in result_batch:
                rid = rec.get("_id", "")
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                merged.append(rec)
                sn = (rec.get("setName") or "").strip()
                if sn:
                    set_names_set.add(sn)

        set_names = sorted(set_names_set)

        cap = settings.max_summary_records
        if cap and len(merged) > cap:
            logger.info(
                "Capping %d records to %d for project=%s trade=%s set_ids=%s",
                len(merged), cap, project_id, trade, set_ids,
            )
            merged = merged[:cap]

        await self._cache.set(
            cache_key,
            {"records": merged, "set_names": set_names},
            ttl=settings.cache_ttl_summary_data,
        )

        logger.info(
            "summaryByTradeAndSet project=%s trade=%s set_ids=%s → %d records, sets=%s",
            project_id, trade, set_ids, len(merged), set_names,
        )
        return merged, set_names

    async def fetch_project_metadata(self, project_id: int) -> dict[str, Any]:
        """Fetch actual trade list via the uniqueTrades API.

        Falls back to empty list if the endpoint fails — intent agent will
        then rely on keyword matching only.
        """
        trades = await self.get_unique_trades(project_id)
        return {"trades": trades, "csi_divisions": []}

    async def get_unique_trades(
        self,
        project_id: int,
        bypass_cache: bool = False,
    ) -> list[str]:
        """Fetch unique trade names for a project via the uniqueTrades endpoint.

        GET /api/drawingText/uniqueTrades?projectId={id}
        Response: {"success": true, "data": {"list": ["Electrical", ...], "count": N}}

        Returns a sorted list of non-empty trade name strings.
        Cached for 1 hour.
        """
        cache_key = CacheService.api_key("unique_trades", project_id)
        if not bypass_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit unique_trades project=%s (%d trades)", project_id, len(cached))
                return cached

        if not self._http:
            logger.error("HTTP client not initialized — call connect() first.")
            return []

        path = settings.unique_trades_path
        if not path.startswith("/"):
            path = f"/{path}"

        try:
            resp = await self._http.get(path, params={"projectId": project_id})
            resp.raise_for_status()
            body = resp.json()
            raw_list = body.get("data", {}).get("list", [])
            trades = sorted({t.strip() for t in raw_list if t and isinstance(t, str) and t.strip()})

            logger.info("uniqueTrades project=%s → %d trades", project_id, len(trades))
            await self._cache.set(cache_key, trades, ttl=3600)
            return trades
        except Exception as exc:
            logger.warning("get_unique_trades failed project=%s: %s", project_id, exc)
            return []

    async def fetch_page1(
        self,
        project_id: int,
        trade: str,
        set_id: Optional[Union[int, str]] = None,
    ) -> list[dict[str, Any]]:
        """Fetch ONLY page 1 of records for a trade — lightweight, fast.

        Used by the drawings endpoint to discover drawing names without
        exhaustively paginating thousands of records.

        Strategy: try summaryByTrade first (has drawingName if available),
        then fall back to byTrade (has pdfName, drawingId — richer for
        projects where summaryByTrade lacks drawing fields).

        Returns list of record dicts (may be empty).
        """
        if not self._http:
            return []

        # Try summaryByTrade first (preferred — contains drawingName/setTrade)
        summary_path = (
            settings.summary_by_trade_and_set_path if set_id
            else settings.summary_by_trade_path
        )
        if not summary_path.startswith("/"):
            summary_path = f"/{summary_path}"
        params: dict[str, Any] = {"projectId": project_id, "trade": trade}
        if set_id is not None:
            params["setId"] = set_id

        try:
            resp = await self._http.get(summary_path, params=params)
            resp.raise_for_status()
            records = self._extract_list(resp.json())
            # Check if records have drawingName (some projects don't)
            if records and records[0].get("drawingName"):
                return records
        except Exception:
            pass

        # Fallback: byTrade endpoint (has pdfName, drawingId, trade)
        raw_path = (
            settings.by_trade_and_set_path if set_id
            else settings.by_trade_path
        )
        if not raw_path.startswith("/"):
            raw_path = f"/{raw_path}"

        try:
            resp = await self._http.get(raw_path, params=params)
            resp.raise_for_status()
            records = self._extract_list(resp.json())
            # Normalize: inject setTrade from trade field for downstream
            for rec in records:
                if not rec.get("setTrade") and rec.get("trade"):
                    rec["setTrade"] = rec["trade"]
            return records
        except Exception as exc:
            logger.debug("fetch_page1 failed project=%s trade=%s: %s", project_id, trade, exc)
            return []

    async def probe_trade_exists(
        self,
        project_id: int,
        trade: str,
        set_id: Optional[Union[int, str]] = None,
    ) -> int:
        """Quickly check if a trade has records by fetching page 1 only.

        Uses the raw byTrade endpoint (faster, lighter than summaryByTrade)
        to check record existence without full pagination.

        Returns record count from page 1 (0 if empty or error).
        """
        if not self._http:
            return 0

        path = settings.by_trade_and_set_path if set_id else settings.by_trade_path
        if not path.startswith("/"):
            path = f"/{path}"
        params: dict[str, Any] = {"projectId": project_id, "trade": trade}
        if set_id is not None:
            params["setId"] = set_id

        try:
            resp = await self._http.get(path, params=params)
            resp.raise_for_status()
            body = resp.json()
            records = body.get("data", {}).get("list", [])
            return len(records)
        except Exception:
            return 0

    # ── Internal helpers ──────────────────────────────────────────────

    async def _fetch_all_pages(
        self,
        project_id: int,
        trade: str,
        set_id: Optional[Union[int, str]] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch ALL records using parallel batch pagination.

        When set_id is None, uses summaryByTrade endpoint.
        When set_id is provided, uses summaryByTradeAndSet endpoint.

        Algorithm (v3 — empty-page termination, immune to wrong API total):
          1. Fetch page 1 serially → discover API page size.
          2. If page 1 is partial (len < page_size) → guaranteed single page, done.
          3. Otherwise: fetch pages in parallel batches of `concurrency` pages each.
             Continue batching until a complete batch returns 0 new records (empty = done).
          4. Merge with _id deduplication, preserving insertion order.
          5. Exponential-backoff retry (1s, 2s) per page, 3 attempts max.

        This replaces the previous "compute pages from total" approach which silently
        returned only page 1 when the API's "count" field held the page count (50)
        rather than the true total record count.
        """
        if not self._http:
            logger.error("HTTP client not initialized — call connect() first.")
            return []

        if set_id is not None:
            path = settings.summary_by_trade_and_set_path
        else:
            path = settings.summary_by_trade_path
        if not path.startswith("/"):
            path = f"/{path}"

        t0 = time.perf_counter()
        base_params: dict[str, Any] = {"projectId": project_id, "trade": trade}
        if set_id is not None:
            base_params["setId"] = set_id

        # ── Page 1: serial — discover API's actual page size ────────────
        try:
            resp = await self._http.get(path, params=base_params)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "summaryByTrade failed project=%s trade=%s status=%s body=%s",
                project_id, trade,
                exc.response.status_code, exc.response.text[:300],
            )
            return []
        except Exception as exc:
            logger.error(
                "summaryByTrade failed project=%s trade=%s error=%s",
                project_id, trade, exc,
            )
            return []

        first_page = self._extract_list(body)
        # "total" used ONLY for informational logging — never for stopping.
        reported_total = self._extract_total(body)
        api_page_size = len(first_page) if first_page else 50

        if not first_page:
            logger.info("summaryByTrade project=%s trade=%s → 0 records", project_id, trade)
            return []

        # ── Reliable single-page termination: partial page = last page ───
        # This is the ONLY correct stop condition. A partial page guarantees
        # there are no further records regardless of what "total" says.
        if len(first_page) < api_page_size:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "summaryByTrade project=%s trade=%s → %d records (%d ms, 1 page, partial)",
                project_id, trade, len(first_page), elapsed,
            )
            return first_page

        # ── Full page 1 — there are likely more pages ────────────────────
        logger.info(
            "summaryByTrade project=%s trade=%s: page 1 full (%d records, page_size=%d, "
            "reported_total=%s). Starting parallel batch fetch (concurrency=%d)...",
            project_id, trade, len(first_page), api_page_size,
            reported_total if reported_total else "unknown",
            settings.parallel_fetch_concurrency,
        )

        all_records: list[dict[str, Any]] = list(first_page)
        seen_ids: set[str] = {r.get("_id", "") for r in all_records if r.get("_id")}
        concurrency = settings.parallel_fetch_concurrency
        pages_fetched = 1
        current_skip = api_page_size
        pages_failed = 0

        async def fetch_one_page(skip: int) -> tuple[int, list[dict[str, Any]]]:
            """Fetch a single page with exponential-backoff retry. Returns (skip, records)."""
            page_num = skip // api_page_size + 1
            page_params: dict[str, Any] = {
                **base_params,
                "skip": skip,
                "limit": api_page_size,
                "page": page_num,
                "pageSize": api_page_size,
            }
            for attempt in range(3):
                try:
                    r = await self._http.get(path, params=page_params)
                    r.raise_for_status()
                    records = self._extract_list(r.json())
                    logger.debug("Page skip=%d → %d records", skip, len(records))
                    return skip, records
                except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                    status = getattr(getattr(exc, "response", None), "status_code", "timeout")
                    if attempt < 2:
                        wait = 2 ** attempt
                        logger.debug(
                            "Page skip=%d attempt %d/3 failed (status=%s) — retry in %ds",
                            skip, attempt + 1, status, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.warning(
                            "PAGE SKIP WARNING: skip=%d failed after 3 attempts (status=%s) "
                            "— records on this page may be missing",
                            skip, status,
                        )
                        return skip, []
                except Exception as exc:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.warning(
                            "PAGE SKIP WARNING: skip=%d error after 3 attempts: %s "
                            "— records on this page may be missing",
                            skip, exc,
                        )
                        return skip, []
            return skip, []

        # ── Parallel batch loop — continue until a batch returns nothing ─
        while pages_fetched < settings.max_pagination_pages:
            remaining_budget = settings.max_pagination_pages - pages_fetched
            batch_size = min(concurrency, remaining_budget)
            batch_skips = [
                current_skip + i * api_page_size
                for i in range(batch_size)
            ]

            # Dispatch this batch concurrently (no semaphore needed — batch size = concurrency)
            batch_results: list[tuple[int, list[dict[str, Any]]]] = await asyncio.gather(
                *[fetch_one_page(s) for s in batch_skips]
            )
            batch_results.sort(key=lambda x: x[0])

            new_records_in_batch = 0
            last_full_page_seen = False

            for skip, page_records in batch_results:
                pages_fetched += 1
                if not page_records:
                    continue

                new_records_in_batch += len(page_records)
                for r in page_records:
                    rid = r.get("_id", "")
                    if rid and rid in seen_ids:
                        continue
                    if rid:
                        seen_ids.add(rid)
                    all_records.append(r)

                # Track whether we saw any failed (empty after retry) pages
                if len(page_records) == 0:
                    pages_failed += 1

                # Partial page within batch = last page of data
                if 0 < len(page_records) < api_page_size:
                    last_full_page_seen = False
                    logger.debug(
                        "Partial page at skip=%d (%d records) — this is the last page",
                        skip, len(page_records),
                    )
                    # Break out of inner loop; outer loop will terminate below
                    break
            else:
                # No break in inner loop → all pages in batch were full or empty
                last_full_page_seen = (new_records_in_batch > 0)

            if new_records_in_batch == 0:
                # Entire batch returned nothing — we've gone past the end of data
                logger.debug(
                    "Batch at skip=%d..%d returned 0 records — pagination complete",
                    current_skip, current_skip + (batch_size - 1) * api_page_size,
                )
                break

            if not last_full_page_seen:
                # We hit a partial page — done
                break

            current_skip += batch_size * api_page_size

        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "FETCH COMPLETE: project=%s trade=%s → %d records total "
            "(%d ms, %d pages fetched, %d pages failed, concurrency=%d"
            "%s)",
            project_id, trade, len(all_records),
            elapsed, pages_fetched, pages_failed, concurrency,
            f", reported_total={reported_total}" if reported_total else "",
        )

        if pages_failed:
            logger.warning(
                "summaryByTrade project=%s trade=%s: %d page(s) failed after retries — "
                "result set may be missing up to %d records",
                project_id, trade, pages_failed, pages_failed * api_page_size,
            )

        return all_records

    @staticmethod
    def _extract_total(payload: Any) -> Optional[int]:
        """Extract total record count from API response for pagination planning."""
        if not isinstance(payload, dict):
            return None

        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("count", "total", "totalCount", "totalRecords"):
                val = data.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return int(val)

        for key in ("count", "total", "totalCount", "totalRecords"):
            val = payload.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return int(val)

        return None

    @staticmethod
    def _extract_list(payload: Any) -> list[dict[str, Any]]:
        """Tolerant extraction of the record list from the API response."""
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]

        if not isinstance(payload, dict):
            return []

        # { "data": { "list": [...] } }  — primary shape
        data = payload.get("data")
        if isinstance(data, dict):
            lst = data.get("list")
            if isinstance(lst, list):
                return [r for r in lst if isinstance(r, dict)]
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]

        # Flat { "list": [...] }
        lst = payload.get("list")
        if isinstance(lst, list):
            return [r for r in lst if isinstance(r, dict)]

        # Other common wrappers
        for key in ("items", "rows", "records", "result", "results"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]

        return []
