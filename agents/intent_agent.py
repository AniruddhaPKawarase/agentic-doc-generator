"""
Hybrid intent detection: fast keywords first, OpenAI fallback second.
"""

import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

from config import get_settings
from models.schemas import IntentResult

logger = logging.getLogger(__name__)
settings = get_settings()

TRADE_KEYWORDS: dict[str, list[str]] = {
    "Plumbing": ["plumbing", "pipe", "drain", "water supply", "sanitary", "wsfu", "valve"],
    "Electrical": ["electrical", "electric", "wiring", "panel", "breaker", "outlet", "circuit"],
    "HVAC": ["hvac", "heating", "cooling", "duct", "ventilation", "exhaust", "cfm"],
    "Structural": ["structural", "beam", "column", "steel", "framing", "joist", "rafter"],
    "Concrete": ["concrete", "slab", "footing", "psi", "rebar", "foundation"],
}

DOCUMENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "scope": ["scope", "scope of work", "sow", "work scope"],
    "exhibit": ["exhibit", "schedule", "breakdown"],
    "report": ["report", "full report", "detailed report"],
    "takeoff": ["takeoff", "take-off", "quantity", "quantities", "material list"],
    "specification": ["specification", "spec", "specifications"],
    "extract": ["extract", "list all", "find all", "pull out", "identify"],
    "generate": ["generate", "create", "produce", "write", "draft"],
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "generate": ["create", "generate", "produce", "write", "draft", "make"],
    "extract": ["extract", "list", "find", "pull", "identify", "show"],
    "summarize": ["summarize", "summary", "overview", "brief"],
    "analyze": ["analyze", "analyse", "review", "check"],
}


class IntentAgent:
    """Detects trade/document type from user query with low-latency fallback."""

    def __init__(self, available_trades: Optional[list[str]] = None, openai_client=None):
        self._available_trades = available_trades or []
        if openai_client is not None:
            self._client = openai_client
        else:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def update_trades(self, trades: list[str]) -> None:
        self._available_trades = trades

    def detect_sync(self, query: str, available_trades: Optional[list[str]] = None) -> IntentResult:
        """
        Keyword-only intent detection — synchronous, no I/O, completes in <1 ms.

        Used by GenerationAgent to obtain a preliminary trade immediately after
        metadata arrives so that context-fetch API calls can be fired concurrently
        with a possible LLM-fallback intent call in detect().  The result is
        identical to what detect() would return when keyword confidence is ≥ 0.7.
        """
        trades = available_trades or self._available_trades
        return self._keyword_match(query.lower(), trades)

    async def detect(self, query: str, available_trades: Optional[list[str]] = None) -> IntentResult:
        trades = available_trades or self._available_trades
        query_lower = query.lower()

        result = self._keyword_match(query_lower, trades)

        if result.confidence < 0.7 and self._client:
            try:
                result = await self._llm_detect(query, trades, result)
            except Exception as exc:
                logger.warning("OpenAI intent fallback failed: %s", exc)

        logger.info(
            "Intent trade=%s doc_type=%s intent=%s confidence=%.2f",
            result.trade,
            result.document_type,
            result.intent,
            result.confidence,
        )
        return result

    def _keyword_match(self, query_lower: str, available_trades: list[str]) -> IntentResult:
        matched_trade = ""
        matched_doc_type = "generate"
        matched_intent = "generate"
        keywords_found: list[str] = []
        confidence = 0.0

        available_lower = {trade.lower(): trade for trade in available_trades if trade}
        for trade_lc, trade_name in available_lower.items():
            if trade_lc and trade_lc in query_lower:
                matched_trade = trade_name
                keywords_found.append(trade_lc)
                confidence = 0.95
                break

        if not matched_trade:
            best_count = 0
            for trade_name, keywords in TRADE_KEYWORDS.items():
                count = sum(1 for keyword in keywords if keyword in query_lower)
                if count > best_count:
                    best_count = count
                    matched_trade = trade_name
                    keywords_found = [keyword for keyword in keywords if keyword in query_lower]
                    confidence = min(0.9, 0.5 + best_count * 0.15)

        if not matched_trade and available_trades:
            matched_trade = available_trades[0]
            confidence = max(confidence, 0.35)

        for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                matched_doc_type = doc_type
                break

        for intent, keywords in INTENT_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                matched_intent = intent
                break

        csi = self._trade_to_csi(matched_trade)
        return IntentResult(
            trade=matched_trade,
            csi_divisions=csi,
            document_type=matched_doc_type,
            intent=matched_intent,
            keywords=keywords_found,
            confidence=confidence,
            raw_query=query_lower,
        )

    async def _llm_detect(
        self,
        query: str,
        available_trades: list[str],
        keyword_result: Optional[IntentResult] = None,
    ) -> IntentResult:
        if keyword_result is None:
            keyword_result = self._keyword_match(query.lower(), available_trades)
        if not self._client:
            return keyword_result

        trades_preview = ", ".join(available_trades[:50]) if available_trades else "unknown"
        prompt = f"""Extract construction intent from the query.

Available trades: {trades_preview}
Query: "{query}"

Return only JSON:
{{
  "trade": "<best trade from available list>",
  "document_type": "<scope|exhibit|report|takeoff|specification|extract|generate>",
  "intent": "<generate|extract|summarize|analyze>",
  "confidence": <0.0-1.0>
}}"""

        response = await self._client.chat.completions.create(
            model=settings.intent_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.intent_max_tokens,
            response_format={"type": "json_object"},
        )

        raw = (response.choices[0].message.content or "").strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return keyword_result

        parsed = json.loads(json_match.group(0))
        trade = parsed.get("trade", keyword_result.trade) or keyword_result.trade
        csi = self._trade_to_csi(trade)

        return IntentResult(
            trade=trade,
            csi_divisions=csi,
            document_type=parsed.get("document_type", keyword_result.document_type),
            intent=parsed.get("intent", keyword_result.intent),
            keywords=keyword_result.keywords,
            confidence=float(parsed.get("confidence", 0.7)),
            raw_query=query,
        )

    @staticmethod
    def _extract_output_text(response: object) -> str:
        output_text = getattr(response, "output_text", "")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        chunks: list[str] = []
        output = getattr(response, "output", None)
        if isinstance(output, list):
            for item in output:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        text = getattr(part, "text", None)
                        if isinstance(text, str):
                            chunks.append(text)
        return "\n".join(chunks)

    @staticmethod
    def _trade_to_csi(trade: str) -> list[str]:
        csi_map: dict[str, list[str]] = {
            "Plumbing": ["22 - Plumbing"],
            "Electrical": ["26 - Electrical"],
            "HVAC": ["23 - Heating, Ventilating, and Air Conditioning (HVAC)"],
            "Concrete": ["03 - Concrete"],
            "Structural": ["05 - Metals", "06 - Wood, Plastics, and Composites"],
            "Roofing": ["07 - Thermal and Moisture Protection"],
            "Drywall": ["09 - Finishes"],
            "Painting": ["09 - Finishes"],
            "Masonry": ["04 - Masonry"],
            "Flooring": ["09 - Finishes"],
            "Carpentry": ["06 - Wood, Plastics, and Composites"],
            "Excavation": ["31 - Earthwork"],
            "Landscaping": ["32 - Exterior Improvements"],
            "Demolition": ["02 - Existing Conditions"],
            "Waterproofing": ["07 - Thermal and Moisture Protection"],
            "Glazing": ["08 - Openings"],
        }
        return csi_map.get(trade, [])
