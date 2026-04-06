"""
scope_pipeline/agents/classification_agent.py — Agent 2: Classify scope items by trade and CSI code.

Input: list[ScopeItem] + trade + available_trades (via kwargs)
Output: list[ClassifiedItem]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import ClassifiedItem, ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a CSI MasterFormat classification expert with 30+ years experience.

TASK: Classify each scope item below by trade and CSI MasterFormat code for the target trade: {trade}.

AVAILABLE TRADES: {available_trades}

RULES:
1. For each item, determine the most appropriate trade from the available trades list.
2. Assign a CSI MasterFormat code in XX XX XX format (e.g., 26 24 16).
3. Assign the CSI division (e.g., "26 - Electrical").
4. Provide a classification_confidence between 0.0 and 1.0.
5. Provide a brief classification_reason explaining why this classification was chosen.
6. Preserve the original item_id exactly as given.

INPUT: JSON array of scope items, each with an "item_id" field.

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"item_id":"itm_xxx","trade":"Electrical","csi_code":"26 24 16","csi_division":"26 - Electrical","classification_confidence":0.92,"classification_reason":"Panel boards under Division 26"}}]"""


class ClassificationAgent(BaseAgent):
    name = "classification"
    requires_llm = True
    max_retries = 2

    def __init__(self, api_key: str, model: str, max_tokens: int = 4000) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> list[ClassifiedItem]:
        scope_items: list[ScopeItem] = input_data
        trade: str = kwargs.get("trade", "")
        available_trades: list[str] = kwargs.get("available_trades", [])

        # Build item list for LLM with item_id for mapping back
        items_for_llm = [
            {
                "item_id": item.id,
                "text": item.text,
                "drawing_name": item.drawing_name,
                "csi_hint": item.csi_hint,
            }
            for item in scope_items
        ]

        system = SYSTEM_PROMPT.format(
            trade=trade,
            available_trades=", ".join(available_trades),
        )

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Classifying {len(scope_items)} scope items for {trade}...",
        })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(items_for_llm)},
            ],
            max_tokens=self._max_tokens,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            self._last_tokens_used = response.usage.total_tokens
        return self._parse_response(raw, scope_items, trade)

    def _parse_response(
        self,
        raw: str,
        scope_items: list[ScopeItem],
        trade: str,
    ) -> list[ClassifiedItem]:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", cleaned)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.error("Failed to parse classification response: %s", cleaned[:200])
                    parsed = []
            else:
                logger.error("No JSON array found in classification response: %s", cleaned[:200])
                parsed = []

        if not isinstance(parsed, list):
            parsed = []

        # Build lookup by item_id for LLM classifications
        classification_map: dict[str, dict[str, Any]] = {}
        for entry in parsed:
            if isinstance(entry, dict) and "item_id" in entry:
                classification_map[entry["item_id"]] = entry

        # Map classifications back to original scope items
        results: list[ClassifiedItem] = []
        for item in scope_items:
            classification = classification_map.get(item.id, {})
            results.append(ClassifiedItem(
                id=item.id,
                text=item.text,
                drawing_name=item.drawing_name,
                drawing_title=item.drawing_title,
                page=item.page,
                source_snippet=item.source_snippet,
                confidence=item.confidence,
                csi_hint=item.csi_hint,
                source_record_id=item.source_record_id,
                trade=classification.get("trade", trade),
                csi_code=classification.get("csi_code", ""),
                csi_division=classification.get("csi_division", ""),
                classification_confidence=float(classification.get("classification_confidence", 0.0)),
                classification_reason=classification.get("classification_reason", ""),
            ))

        return results
