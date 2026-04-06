"""
scope_pipeline/agents/ambiguity_agent.py — Agent 3: Detect trade-overlap ambiguities.

Input: list[ScopeItem]
Output: list[AmbiguityItem]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import AmbiguityItem, ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a construction scope ambiguity specialist with 30+ years experience resolving trade overlaps.

TASK: Analyze the scope items below and identify ANY trade-overlap ambiguities.

COMMON AMBIGUITIES to watch for:
- Flashing / waterproofing ownership between trades
- Fire stopping responsibility
- Backing / blocking for wall-mounted equipment
- Electrical connections for mechanical equipment
- Pipe insulation vs mechanical insulation
- Structural steel vs miscellaneous metals
- Controls wiring vs electrical wiring

RULES:
1. For each ambiguity, identify the exact scope text causing the overlap.
2. List ALL competing trades that could claim ownership.
3. Rate severity: "high" (cost/schedule risk), "medium" (coordination needed), "low" (minor clarification).
4. Provide a clear recommendation for resolution.
5. Reference the source item IDs and drawing references.
6. If no ambiguities exist, return an empty array [].

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"scope_text":"description","competing_trades":["Trade A","Trade B"],"severity":"high","recommendation":"resolution guidance","source_items":["itm_xxx"],"drawing_refs":["A-201"]}}]"""


class AmbiguityAgent(BaseAgent):
    name = "ambiguity"
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
    ) -> list[AmbiguityItem]:
        scope_items: list[ScopeItem] = input_data

        items_for_llm = [
            {
                "item_id": item.id,
                "text": item.text,
                "drawing_name": item.drawing_name,
                "page": item.page,
                "csi_hint": item.csi_hint,
            }
            for item in scope_items
        ]

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Analyzing {len(scope_items)} items for trade-overlap ambiguities...",
        })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(items_for_llm)},
            ],
            max_tokens=self._max_tokens,
            temperature=0.3,
        )

        raw = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            self._last_tokens_used = response.usage.total_tokens
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> list[AmbiguityItem]:
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
                    logger.error("Failed to parse ambiguity response: %s", cleaned[:200])
                    return []
            else:
                logger.error("No JSON array found in ambiguity response: %s", cleaned[:200])
                return []

        if not isinstance(parsed, list):
            return []

        items: list[AmbiguityItem] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            items.append(AmbiguityItem(
                scope_text=entry.get("scope_text", ""),
                competing_trades=entry.get("competing_trades", []),
                severity=entry.get("severity", "low"),
                recommendation=entry.get("recommendation", ""),
                source_items=entry.get("source_items", []),
                drawing_refs=entry.get("drawing_refs", []),
            ))

        return items
