"""
scope_pipeline/agents/base_agent.py — Abstract base for all pipeline agents.

Provides:
  - Automatic timing measurement
  - Per-agent retry with backoff
  - SSE progress emission
  - Token tracking placeholder
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from scope_pipeline.models import AgentError, AgentResult
from scope_pipeline.services.progress_emitter import ProgressEmitter

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for pipeline agents."""

    name: str = "base"
    requires_llm: bool = True
    max_retries: int = 2
    _last_tokens_used: int = 0

    async def run(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> AgentResult:
        emitter.emit("agent_start", {
            "agent": self.name,
            "message": f"Starting {self.name} agent...",
        })
        start = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result_data = await self._execute(input_data, emitter, **kwargs)
                elapsed = int((time.monotonic() - start) * 1000)

                emitter.emit("agent_complete", {
                    "agent": self.name,
                    "elapsed_ms": elapsed,
                    "attempt": attempt,
                })
                logger.info(
                    "Agent %s completed in %dms (attempt %d)",
                    self.name, elapsed, attempt,
                )
                tokens = self._last_tokens_used
                self._last_tokens_used = 0
                return AgentResult(
                    agent=self.name,
                    data=result_data,
                    elapsed_ms=elapsed,
                    tokens_used=tokens,
                    attempt=attempt,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Agent %s attempt %d failed: %s",
                    self.name, attempt, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(min(attempt, 3))

        emitter.emit("agent_failed", {
            "agent": self.name,
            "error": str(last_error),
        })
        raise AgentError(self.name, str(last_error))

    @abstractmethod
    async def _execute(
        self,
        input_data: Any,
        emitter: ProgressEmitter,
        **kwargs: Any,
    ) -> Any:
        ...
