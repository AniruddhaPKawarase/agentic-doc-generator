"""Integration tests for API client endpoint migration with fallback."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from services.api_client import APIClient


@pytest.fixture
def api_client():
    client = APIClient.__new__(APIClient)
    client._http = AsyncMock(spec=httpx.AsyncClient)
    client._cache = AsyncMock()
    client._cache.get = AsyncMock(return_value=None)
    client._cache.set = AsyncMock()
    return client


class TestFetchWithFallback:
    @pytest.mark.asyncio
    async def test_primary_success(self, api_client):
        fake_records = [{"_id": "1", "drawingName": "A1"}]
        with patch.object(api_client, "_fetch_all_pages", new_callable=AsyncMock, return_value=fake_records):
            records, label = await api_client._fetch_with_fallback(
                7292, "Civil",
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade", fallback_label="summaryByTrade",
            )
        assert records == fake_records
        assert label == "byTrade"

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self, api_client):
        fallback_records = [{"_id": "2", "drawingName": "B1"}]
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status_code = 500
                raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
            return fallback_records
        with patch.object(api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect):
            records, label = await api_client._fetch_with_fallback(
                7292, "Civil",
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade", fallback_label="summaryByTrade",
            )
        assert records == fallback_records
        assert label == "summaryByTrade"

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(self, api_client):
        fallback_records = [{"_id": "3"}]
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timed out")
            return fallback_records
        with patch.object(api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect):
            records, label = await api_client._fetch_with_fallback(
                7292, "Civil",
                primary_path="/api/drawingText/byTrade",
                fallback_path="/api/drawingText/summaryByTrade",
                primary_label="byTrade", fallback_label="summaryByTrade",
            )
        assert records == fallback_records
        assert label == "summaryByTrade"

    @pytest.mark.asyncio
    async def test_correct_labels_for_set_variant(self, api_client):
        fallback_records = [{"_id": "4"}]
        call_count = 0
        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            return fallback_records
        with patch.object(api_client, "_fetch_all_pages", new_callable=AsyncMock, side_effect=side_effect):
            records, label = await api_client._fetch_with_fallback(
                7292, "Civil",
                primary_path="/api/drawingText/byTradeAndSet",
                fallback_path="/api/drawingText/summaryByTradeAndSet",
                primary_label="byTradeAndSet", fallback_label="summaryByTradeAndSet",
                set_id=4720,
            )
        assert label == "summaryByTradeAndSet"


class TestGetByTrade:
    @pytest.mark.asyncio
    async def test_feature_flag_true(self, api_client):
        fake_records = [{"_id": "1"}]
        with patch.object(api_client, "_fetch_with_fallback", new_callable=AsyncMock, return_value=(fake_records, "byTrade")):
            with patch("services.api_client.settings") as mock_s:
                mock_s.use_new_api = True
                mock_s.by_trade_path = "/api/drawingText/byTrade"
                mock_s.summary_by_trade_path = "/api/drawingText/summaryByTrade"
                records, metadata = await api_client.get_by_trade(7292, "Civil")
        assert records == fake_records
        assert metadata["endpoint_used"] == "byTrade"
        assert metadata["fallback"] is False

    @pytest.mark.asyncio
    async def test_feature_flag_false(self, api_client):
        fake_records = [{"_id": "1"}]
        with patch.object(api_client, "get_summary_by_trade", new_callable=AsyncMock, return_value=fake_records):
            with patch("services.api_client.settings") as mock_s:
                mock_s.use_new_api = False
                records, metadata = await api_client.get_by_trade(7292, "Civil")
        assert records == fake_records
        assert metadata["endpoint_used"] == "summaryByTrade"
