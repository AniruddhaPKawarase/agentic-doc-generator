"""
scope_pipeline/agents/quality_agent.py — Agent 6: Quality review via LLM.

Input: MergedResults (items + classified_items + ambiguities + gotchas)
Output: QualityReport with accuracy_score, corrections, validated_items, removed_items, summary.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import (
    ClassifiedItem,
    MergedResults,
    QualityCorrection,
    QualityReport,
)
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior construction QA reviewer with 30+ years experience.

TASK: Review the extracted scope items below for quality and accuracy.

CHECK FOR:
1. Duplicate items (same scope described differently)
2. Misclassifications (wrong trade or CSI code assigned)
3. Incorrect CSI codes (code does not match the scope description)
4. Vague items (too generic to be actionable — e.g. "misc electrical")
5. Hallucinated items (items that do not correspond to any source text)

FOR EACH CORRECTION provide:
- item_id: the ID of the item to correct
- field: which field is wrong (e.g. "csi_code", "trade", "text")
- old_value: current value
- new_value: corrected value
- reason: why this correction is needed

OUTPUT: Respond with ONLY a JSON object. No markdown fences. No explanation.
{{"accuracy_score": 0.95, "corrections": [...], "removed_item_ids": ["itm_xxx"], "summary": "brief summary"}}

If all items look correct, return:
{{"accuracy_score": 1.0, "corrections": [], "removed_item_ids": [], "summary": "All items verified."}}"""

MAX_ITEMS_IN_PROMPT = 50


class QualityAgent(BaseAgent):
    name = "quality"
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
    ) -> QualityReport:
        merged: MergedResults = input_data
        classified = merged.classified_items

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Reviewing {len(classified)} items for quality...",
        })

        items_summary = self._serialize_items_for_prompt(classified)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Review these scope items:\n\n{items_summary}"},
            ],
            max_tokens=self._max_tokens,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            self._last_tokens_used = response.usage.total_tokens
        return self._parse_response(raw, classified)

    def _serialize_items_for_prompt(self, items: list[ClassifiedItem]) -> str:
        """Build a JSON summary of items (capped at MAX_ITEMS_IN_PROMPT) for the LLM."""
        capped = items[:MAX_ITEMS_IN_PROMPT]
        summary = []
        for item in capped:
            summary.append({
                "id": item.id,
                "text": item.text,
                "drawing_name": item.drawing_name,
                "trade": item.trade,
                "csi_code": item.csi_code,
                "csi_division": item.csi_division,
                "confidence": item.confidence,
                "source_snippet": item.source_snippet,
            })
        return json.dumps(summary, indent=2)

    def _parse_response(
        self,
        raw: str,
        classified: list[ClassifiedItem],
    ) -> QualityReport:
        """Parse LLM JSON response into a QualityReport. Falls back to default on failure."""
        all_ids = [item.id for item in classified]

        parsed = self._try_parse_json(raw)
        if parsed is None:
            logger.error(
                "Quality agent: LLM returned unparseable response (%d chars). "
                "Marking accuracy as 0.0 and flagging for manual review.",
                len(raw),
            )
            return QualityReport(
                accuracy_score=0.0,
                corrections=[],
                validated_items=all_ids,
                removed_items=[],
                summary="Quality review failed: LLM response could not be parsed. Manual review required.",
            )

        accuracy = float(parsed.get("accuracy_score", 1.0))
        raw_corrections = parsed.get("corrections", [])
        removed_ids = parsed.get("removed_item_ids", [])
        summary = parsed.get("summary", "Quality review complete.")

        corrections = []
        for entry in raw_corrections:
            if not isinstance(entry, dict):
                continue
            corrections.append(QualityCorrection(
                item_id=entry.get("item_id", ""),
                field=entry.get("field", ""),
                old_value=str(entry.get("old_value", "")),
                new_value=str(entry.get("new_value", "")),
                reason=entry.get("reason", ""),
            ))

        validated_ids = [iid for iid in all_ids if iid not in removed_ids]

        return QualityReport(
            accuracy_score=accuracy,
            corrections=corrections,
            validated_items=validated_ids,
            removed_items=list(removed_ids),
            summary=summary,
        )

    @staticmethod
    def _try_parse_json(raw: str) -> dict | None:
        """Attempt to parse JSON from LLM output, handling markdown fences."""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
            return None
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    result = json.loads(match.group(0))
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    pass
            return None
