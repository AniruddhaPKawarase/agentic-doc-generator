"""
scope_pipeline/services/chat_handler.py — Follow-up chat on scope gap reports.

Uses the session's latest_result as LLM context to answer questions
about the generated scope gap analysis.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from scope_pipeline.models import ScopeGapSession, SessionMessage

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 10
_MAX_STORED_MESSAGES = 20

_SYSTEM_PROMPT = (
    "You are a construction scope gap analysis assistant. "
    "Answer questions about the scope gap report using ONLY the provided context. "
    "Be specific, cite drawing names and CSI codes when relevant. "
    "If you cannot answer from the context, say so."
)


def _build_context(session: ScopeGapSession) -> str:
    """Build LLM context string from the session's latest result."""
    r = session.latest_result
    if r is None:
        return ""

    parts = [
        f"Project: {r.project_name} (ID: {r.project_id})",
        f"Trade: {r.trade}",
        f"Items extracted: {len(r.items)}",
        f"Ambiguities found: {len(r.ambiguities)}",
        f"Gotchas found: {len(r.gotchas)}",
        f"Completeness: {r.completeness.overall_pct:.1f}%",
        f"Quality score: {r.quality.accuracy_score:.2f}",
        f"Quality summary: {r.quality.summary}",
    ]

    if r.items:
        parts.append("\n--- Scope Items ---")
        for item in r.items[:50]:  # Cap to avoid token overflow
            parts.append(
                f"- [{item.csi_code}] {item.text} "
                f"(drawing: {item.drawing_name}, confidence: {item.confidence:.2f})"
            )

    if r.ambiguities:
        parts.append("\n--- Ambiguities ---")
        for amb in r.ambiguities:
            parts.append(
                f"- {amb.scope_text} | trades: {', '.join(amb.competing_trades)} "
                f"| severity: {amb.severity}"
            )

    if r.gotchas:
        parts.append("\n--- Gotchas / Hidden Risks ---")
        for g in r.gotchas:
            parts.append(
                f"- [{g.risk_type}] {g.description} | severity: {g.severity}"
            )

    return "\n".join(parts)


class ScopeGapChatHandler:
    """Answers follow-up questions about a scope gap report."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def handle(self, session: ScopeGapSession, message: str) -> dict[str, Any]:
        """
        Process a follow-up question.

        Returns {"answer": str, "source_refs": list[str]}.
        """
        if session.latest_result is None:
            return {
                "answer": "No scope gap report available yet. Please run the pipeline first.",
                "source_refs": [],
            }

        context = _build_context(session)

        # Build conversation history (last N messages)
        history_messages = [{"role": "system", "content": f"{_SYSTEM_PROMPT}\n\nReport context:\n{context}"}]

        recent = session.messages[-_MAX_HISTORY_MESSAGES:]
        for msg in recent:
            history_messages.append({"role": msg.role, "content": msg.content})

        history_messages.append({"role": "user", "content": message})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=history_messages,
                max_tokens=1000,
                temperature=0.3,
            )
            answer = response.choices[0].message.content or ""
        except Exception:
            logger.exception("Chat LLM call failed")
            return {
                "answer": "Error processing your question. Please try again.",
                "source_refs": [],
            }

        # Append to session message history
        session.messages.append(SessionMessage(role="user", content=message))
        session.messages.append(SessionMessage(role="assistant", content=answer))

        # Cap message history
        if len(session.messages) > _MAX_STORED_MESSAGES:
            session.messages = list(session.messages[-_MAX_STORED_MESSAGES:])

        return {
            "answer": answer,
            "source_refs": [],
        }
