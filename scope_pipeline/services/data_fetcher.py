"""
scope_pipeline/services/data_fetcher.py — Adapter between existing APIClient and pipeline.

The orchestrator calls fetch_records(project_id, trade, set_ids).
This adapter calls the existing APIClient.get_summary_by_trade() and
extracts drawing names + CSI codes from the results.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DataFetcher:
    """Wraps the existing APIClient for scope gap pipeline use."""

    def __init__(self, api_client: Any):
        self._api = api_client

    async def fetch_records(
        self,
        project_id: int,
        trade: str,
        set_ids: Optional[list[int]] = None,
    ) -> dict[str, Any]:
        """
        Fetch drawing records and extract metadata.

        Returns:
            {
                "records": list[dict],       # raw records from API
                "drawing_names": set[str],   # unique drawing names
                "csi_codes": set[str],       # unique CSI codes
            }
        """
        if set_ids:
            # Fetch per set_id and merge
            all_records: list[dict] = []
            seen_ids: set[str] = set()
            for sid in set_ids:
                batch, _ = await self._api.get_summary_by_trade_and_set(
                    project_id, trade, [sid],
                )
                for rec in batch:
                    rec_id = rec.get("_id", "")
                    if rec_id and rec_id not in seen_ids:
                        all_records.append(rec)
                        seen_ids.add(rec_id)
            records = all_records
        else:
            records = await self._api.get_summary_by_trade(project_id, trade)

        # Extract metadata
        drawing_names: set[str] = set()
        csi_codes: set[str] = set()

        for rec in records:
            dn = rec.get("drawingName", "") or rec.get("drawing_name", "")
            if dn:
                drawing_names.add(dn)

            # CSI codes from csi_division field
            for csi in rec.get("csi_division", []):
                if csi:
                    csi_codes.add(csi.strip())

        # Extract S3 path mapping: drawing_name -> S3 path
        drawing_s3_urls: dict[str, str] = {}
        for rec in records:
            dn = rec.get("drawingName", "") or rec.get("drawing_name", "") or rec.get("pdfName", "")
            s3_path = rec.get("s3BucketPath", "")
            pdf_name = rec.get("pdfName", "")
            if dn and s3_path and pdf_name and dn not in drawing_s3_urls:
                drawing_s3_urls[dn] = f"{s3_path}/{pdf_name}"

        logger.info(
            "Fetched %d records for project=%d trade=%s (%d drawings, %d CSI codes)",
            len(records), project_id, trade,
            len(drawing_names), len(csi_codes),
        )

        return {
            "records": records,
            "drawing_names": drawing_names,
            "csi_codes": csi_codes,
            "drawing_s3_urls": drawing_s3_urls,
        }
