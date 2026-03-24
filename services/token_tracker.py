"""
services/token_tracker.py  —  Token budget enforcement and per-session accounting.

Responsibilities:
  1. Count tokens BEFORE sending to LLM (prevent over-limit errors)
  2. Record actual tokens used AFTER LLM responds
  3. Enforce a hard budget (trim context if needed)
  4. Persist per-session cumulative totals in CacheService
  5. Track per-step token usage for granular pipeline diagnostics
"""

import logging
import time
from typing import Any

from config import get_settings
from models.schemas import TokenUsage
from services.cache_service import CacheService
from utils.token_counter import (
    count_tokens,
    count_messages_tokens,
    estimate_cost,
    truncate_to_token_budget,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class PipelineTokenLog:
    """Accumulates per-step token counts for a single pipeline run."""

    def __init__(self):
        self.steps: dict[str, dict[str, Any]] = {}
        self._t0 = time.perf_counter()

    def record_step(
        self,
        step_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        elapsed_ms = int((time.perf_counter() - self._t0) * 1000)
        self.steps[step_name] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost_usd, 6),
            "elapsed_ms": elapsed_ms,
        }

    def summary(self) -> dict[str, Any]:
        total_input = sum(s["input_tokens"] for s in self.steps.values())
        total_output = sum(s["output_tokens"] for s in self.steps.values())
        total_cost = sum(s["cost_usd"] for s in self.steps.values())
        return {
            "steps": self.steps,
            "totals": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "cost_usd": round(total_cost, 6),
            },
        }


class TokenTracker:
    def __init__(self, cache: CacheService):
        self._cache = cache

    def create_pipeline_log(self) -> PipelineTokenLog:
        """Create a new per-pipeline token log for granular tracking."""
        return PipelineTokenLog()

    # -- Pre-call budget enforcement ------------------------------------

    def enforce_context_budget(
        self,
        system_prompt: str,
        context_block: str,
        history_messages: list[dict],
        user_query: str,
        max_context_tokens: int = None,
    ) -> tuple[str, int]:
        """
        Trim context_block so that the total prompt fits within budget.
        Returns (trimmed_context_block, estimated_total_input_tokens).
        """
        budget = max_context_tokens or settings.max_context_tokens

        # Fixed-size portions
        fixed_tokens = (
            count_tokens(system_prompt)
            + count_messages_tokens(history_messages)
            + count_tokens(user_query)
            + 50  # safety margin
        )
        context_budget = budget - fixed_tokens

        if context_budget <= 0:
            logger.warning("No token budget left for context! Fixed tokens: %d", fixed_tokens)
            return "", fixed_tokens

        original_ctx_tokens = count_tokens(context_block)
        if original_ctx_tokens <= context_budget:
            total_input = fixed_tokens + original_ctx_tokens
            return context_block, total_input

        trimmed_context, actual_ctx_tokens = truncate_to_token_budget(
            context_block, context_budget
        )
        logger.info(
            "Context trimmed: %d -> %d tokens (budget: %d)",
            original_ctx_tokens,
            actual_ctx_tokens,
            context_budget,
        )
        total_input = fixed_tokens + actual_ctx_tokens
        return trimmed_context, total_input

    def estimate_input_tokens(
        self,
        system_prompt: str,
        context_block: str,
        history_messages: list[dict],
        user_query: str,
    ) -> int:
        """Quick pre-call token estimate (no truncation)."""
        return (
            count_tokens(system_prompt)
            + count_tokens(context_block)
            + count_messages_tokens(history_messages)
            + count_tokens(user_query)
        )

    # -- Post-call recording --------------------------------------------

    def record_usage(self, input_tokens: int, output_tokens: int) -> TokenUsage:
        """Build a TokenUsage from actual API response counts."""
        total = input_tokens + output_tokens
        cost = estimate_cost(input_tokens, output_tokens)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=round(cost, 6),
        )
        logger.info(
            "Token usage -- input: %d  output: %d  total: %d  cost: $%.4f",
            input_tokens, output_tokens, total, cost,
        )
        return usage

    # -- Session totals -------------------------------------------------

    async def accumulate_session_tokens(
        self, session_id: str, usage: TokenUsage
    ) -> dict[str, Any]:
        """Add usage to running session total stored in cache."""
        key = CacheService.token_key(session_id)
        current = await self._cache.get(key) or {
            "session_id": session_id,
            "total_input": 0,
            "total_output": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "call_count": 0,
        }
        current["total_input"] += usage.input_tokens
        current["total_output"] += usage.output_tokens
        current["total_tokens"] += usage.total_tokens
        current["total_cost_usd"] = round(current["total_cost_usd"] + usage.cost_usd, 6)
        current["call_count"] += 1
        await self._cache.set(key, current, ttl=settings.session_ttl)
        return current

    async def get_session_totals(self, session_id: str) -> dict[str, Any]:
        """Retrieve accumulated token stats for a session."""
        key = CacheService.token_key(session_id)
        return await self._cache.get(key) or {}