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
from typing import Any, Optional

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
        """Add usage to running session total stored in cache + S3."""
        key = CacheService.token_key(session_id)
        current = await self._cache.get(key)
        if not current:
            # Try S3 fallback
            current = await self._load_tokens_s3(session_id)
        if not current:
            current = {
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
        # Persist to S3 in background
        import asyncio
        asyncio.create_task(self._save_tokens_s3(session_id, current))
        return current

    async def get_session_totals(self, session_id: str) -> dict[str, Any]:
        """Retrieve accumulated token stats for a session (cache → S3)."""
        key = CacheService.token_key(session_id)
        data = await self._cache.get(key)
        if not data:
            data = await self._load_tokens_s3(session_id)
            if data:
                await self._cache.set(key, data, ttl=settings.session_ttl)
        return data or {}

    # -- S3 token persistence -------------------------------------------

    async def _save_tokens_s3(self, session_id: str, data: dict) -> None:
        if settings.storage_backend != "s3":
            return
        import asyncio, json, sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        try:
            from s3_utils.operations import upload_bytes
            s3_key = f"{settings.s3_agent_prefix}/conversation_memory/tokens_{session_id}.json"
            payload = json.dumps(data, default=str).encode("utf-8")
            await asyncio.to_thread(upload_bytes, payload, s3_key, "application/json")
        except Exception as e:
            logger.debug("S3 token save failed for %s: %s", session_id, e)

    async def _load_tokens_s3(self, session_id: str) -> Optional[dict]:
        if settings.storage_backend != "s3":
            return None
        import asyncio, json, sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        try:
            from s3_utils.operations import download_bytes
            s3_key = f"{settings.s3_agent_prefix}/conversation_memory/tokens_{session_id}.json"
            raw = await asyncio.to_thread(download_bytes, s3_key)
            if raw:
                logger.info("Token data for %s loaded from S3 (cache miss)", session_id)
                return json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.debug("S3 token load failed for %s: %s", session_id, e)
        return None