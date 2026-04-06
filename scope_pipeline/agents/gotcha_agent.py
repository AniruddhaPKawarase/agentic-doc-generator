"""
scope_pipeline/agents/gotcha_agent.py — Agent 4: Detect hidden risks and commonly-missed scope items.

Input: list[ScopeItem] + trade (via kwargs)
Output: list[GotchaItem]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import GotchaItem, ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a construction preconstruction risk analyst with 30+ years experience.

TASK: Analyze the scope items below for hidden risks and commonly-missed items for the trade: {trade}.

RISK TYPES to check:
- hidden_cost: Items that appear minor but carry significant cost implications
- coordination: Multi-trade coordination requirements not explicitly addressed
- missing_scope: Standard items commonly required but not present in the scope
- spec_conflict: Contradictory requirements between drawings or specifications

CHECK FOR:
1. Temporary items not explicitly scoped (temp power, temp protection, hoisting)
2. Multi-trade coordination needs (penetrations, sleeves, backing, supports)
3. Standard items commonly missing (testing, commissioning, closeout docs, warranties)
4. Contradictory requirements between different drawings
5. Code-required items not called out in drawings

RULES:
1. Reference exact drawing names and item text from the input.
2. Rate severity: "high" (budget/schedule impact), "medium" (coordination risk), "low" (minor oversight).
3. Provide actionable recommendations for each risk.
4. If no risks are found, return an empty array [].

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"risk_type":"hidden_cost","description":"clear description","severity":"high","affected_trades":["Trade A","Trade B"],"recommendation":"actionable guidance","drawing_refs":["E-101"]}}]"""


class GotchaAgent(BaseAgent):
    name = "gotcha"
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
    ) -> list[GotchaItem]:
        scope_items: list[ScopeItem] = input_data
        trade: str = kwargs.get("trade", "")

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

        system = SYSTEM_PROMPT.format(trade=trade)

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Analyzing {len(scope_items)} items for hidden risks in {trade}...",
        })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(items_for_llm)},
            ],
            max_tokens=self._max_tokens,
            temperature=0.3,
        )

        raw = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            self._last_tokens_used = response.usage.total_tokens
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> list[GotchaItem]:
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
                    logger.error("Failed to parse gotcha response: %s", cleaned[:200])
                    return []
            else:
                logger.error("No JSON array found in gotcha response: %s", cleaned[:200])
                return []

        if not isinstance(parsed, list):
            return []

        items: list[GotchaItem] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            items.append(GotchaItem(
                risk_type=entry.get("risk_type", ""),
                description=entry.get("description", ""),
                severity=entry.get("severity", "low"),
                affected_trades=entry.get("affected_trades", []),
                recommendation=entry.get("recommendation", ""),
                drawing_refs=entry.get("drawing_refs", []),
            ))

        return items
