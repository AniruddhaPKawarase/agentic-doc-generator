"""
scope_pipeline/agents/extraction_agent.py — Agent 1: Extract scope items from drawing text.

Input: dict with drawing_records, trade, drawing_list
Output: list[ScopeItem]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.agents.base_agent import BaseAgent
from scope_pipeline.models import ScopeItem
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a construction scope extraction expert with 30+ years experience in AIA/CSI contract language.

TASK: Extract ALL actionable scope items from the drawing notes below for the trade: {trade}.

CONTRACTUAL LANGUAGE REQUIREMENTS:
- Every scope item text MUST begin with "Contractor shall"
- Use standard AIA/CSI contractual phrases where applicable:
  * "furnish and install" — for supply-and-install requirements
  * "provide" — for general supply or delivery obligations
  * "coordinate with" — for inter-trade or interface requirements
  * "provide allowance for" — for budget or contingency items
  * "verify in field" — for dimensions, conditions, or existing work to be confirmed
  * "as indicated on Drawing [drawing number]" — when referencing a specific drawing
  * "per Division [number] — [name]" — when referencing a CSI division spec (e.g. "per Division 26 — Electrical")
  * "in accordance with" — for code, standard, or specification compliance
  * "including but not limited to" — when listing non-exhaustive requirements
  * "prior to" — for sequencing or prerequisite conditions

EXTRACTION RULES:
1. Every item MUST include the exact drawing_name it came from (from the drawing header).
2. Every item MUST include a source_snippet: 5-15 words copied VERBATIM from the source text.
3. Every item MUST include the page number from the drawing header.
4. Every item MUST include drawing_refs: an array of ALL drawing numbers explicitly referenced or implied by this scope item (include the source drawing_name at minimum).
5. Do NOT invent items not present in the source text.
6. Do NOT merge items from different drawings into one item.
7. If a CSI MasterFormat code is obvious from the text, include it as csi_hint (format: XX XX XX).
8. Extract EVERY specific, actionable requirement — materials, equipment, installations, connections.

AUTHORITATIVE DRAWING LIST (only these drawings exist):
{drawing_list}

Any drawing_name or drawing_refs entry NOT in this list is a hallucination — do NOT reference it.

OUTPUT: Respond with ONLY a JSON array. No markdown fences. No explanation.
[{{"text":"Contractor shall furnish and install 200A panel board, 42-circuit, surface mounted, as indicated on Drawing E-103","drawing_name":"E-103","page":3,"source_snippet":"verbatim 5-15 words","confidence":0.95,"csi_hint":"26 24 16","drawing_refs":["E-103"]}}]"""


class ExtractionAgent(BaseAgent):
    name = "extraction"
    requires_llm = True
    max_retries = 2

    def __init__(self, api_key: str, model: str, max_tokens: int = 8000):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> list[ScopeItem]:
        records = input_data.get("drawing_records", [])
        trade = input_data.get("trade", "")
        drawing_list = input_data.get("drawing_list", [])

        context_blocks = []
        for rec in records:
            name = rec.get("drawing_name", "Unknown")
            title = rec.get("drawing_title", "")
            text = rec.get("text", "")
            header = f"=== DRAWING: {name}"
            if title:
                header += f" ({title})"
            header += " ==="
            context_blocks.append(f"{header}\n{text}")

        context = "\n\n".join(context_blocks)

        system = SYSTEM_PROMPT.format(
            trade=trade,
            drawing_list=", ".join(drawing_list),
        )

        emitter.emit("agent_progress", {
            "agent": self.name,
            "message": f"Extracting scope from {len(records)} drawing records for {trade}...",
        })

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Extract all {trade} scope items:\n\n{context}"},
            ],
            max_tokens=self._max_tokens,
            temperature=0.3,
        )

        raw = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            self._last_tokens_used = response.usage.total_tokens
        return self._parse_response(raw)

    def _parse_response(self, raw: str) -> list[ScopeItem]:
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
                    logger.error("Failed to parse extraction response: %s", cleaned[:200])
                    return []
            else:
                logger.error("No JSON array found in extraction response: %s", cleaned[:200])
                return []

        if not isinstance(parsed, list):
            return []

        items = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            dn = entry.get("drawing_name", "Unknown")
            items.append(ScopeItem(
                text=entry.get("text", ""),
                drawing_name=dn,
                drawing_title=entry.get("drawing_title"),
                page=entry.get("page", 1),
                source_snippet=entry.get("source_snippet", ""),
                confidence=float(entry.get("confidence", 0.5)),
                csi_hint=entry.get("csi_hint"),
                drawing_refs=entry.get("drawing_refs", [dn]),
            ))
        return items
