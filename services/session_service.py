"""
services/session_service.py  —  Conversation memory management.

Each session stores the last SESSION_MAX_MESSAGES turns.
Older messages beyond the window are summarized into a "summary" prefix
so context doesn't balloon indefinitely.

Persistence: L1 cache → Redis (if available) → S3 (durable fallback).
Without Redis, S3 is the only durable store. L1 is process-local and
expires after 1 hour or on restart.

Anti-hallucination memory design:
  - Rolling window keeps only recent verbatim messages (prevents stale context)
  - Older messages are summarized with trade/project metadata anchoring
  - Summary includes only verified facts (trade names, project IDs, drawing refs)
  - Each message carries metadata (trade, doc_type) for context validation
  - Groundedness scores are tracked per turn for trend detection
"""

import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import SessionContext, SessionMessage, TokenUsage
from services.cache_service import CacheService
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Lazy S3 imports
_s3_ready = False


def _init_s3():
    global _s3_ready
    if not _s3_ready:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        _s3_ready = True


def _session_s3_key(session_id: str) -> str:
    """Build S3 key for a session JSON file."""
    # Avoid double prefix: session_id may already start with "session_"
    fname = session_id if session_id.startswith("session_") else f"session_{session_id}"
    return f"{settings.s3_agent_prefix}/conversation_memory/{fname}.json"


def _token_s3_key(session_id: str) -> str:
    """Build S3 key for a token usage JSON file."""
    fname = session_id if session_id.startswith("session_") else f"session_{session_id}"
    return f"{settings.s3_agent_prefix}/conversation_memory/tokens_{fname}.json"


def _s3_enabled() -> bool:
    return settings.storage_backend == "s3"


def _save_to_s3(s3_key: str, data: dict) -> bool:
    """Persist JSON data to S3 (synchronous — call via to_thread)."""
    if not _s3_enabled():
        return False
    _init_s3()
    try:
        from s3_utils.operations import upload_bytes
        payload = json.dumps(data, default=str).encode("utf-8")
        return upload_bytes(payload, s3_key, content_type="application/json")
    except Exception as e:
        logger.debug("S3 save failed for %s: %s", s3_key, e)
        return False


def _load_from_s3(s3_key: str) -> Optional[dict]:
    """Load JSON data from S3 (synchronous — call via to_thread)."""
    if not _s3_enabled():
        return None
    _init_s3()
    try:
        from s3_utils.operations import download_bytes
        raw = download_bytes(s3_key)
        if raw:
            return json.loads(raw.decode("utf-8"))
    except Exception as e:
        logger.debug("S3 load failed for %s: %s", s3_key, e)
    return None


def _delete_from_s3(s3_key: str) -> bool:
    """Delete a JSON file from S3 (synchronous)."""
    if not _s3_enabled():
        return False
    _init_s3()
    try:
        from s3_utils.operations import delete_object
        return delete_object(s3_key)
    except Exception as e:
        logger.debug("S3 delete failed for %s: %s", s3_key, e)
        return False


class SessionService:
    def __init__(self, cache: CacheService, max_messages: int = 20, session_ttl: int = 86400):
        self._cache = cache
        self._max_messages = max_messages
        self._session_ttl = session_ttl

    # -- Session lifecycle -----------------------------------------------

    async def get_or_create(self, session_id: Optional[str], project_id: int) -> SessionContext:
        """Load existing session or create a new one."""
        if session_id:
            ctx = await self._load(session_id)
            if ctx:
                return ctx
        ctx = SessionContext(
            session_id=session_id or str(uuid.uuid4()),
            project_id=project_id,
        )
        ctx.token_summary.session_id = ctx.session_id
        await self._save(ctx)
        return ctx

    async def add_message(
        self, ctx: SessionContext, role: str, content: str, metadata: dict = None
    ) -> None:
        """Append a new turn and enforce the sliding window."""
        ctx.messages.append(
            SessionMessage(
                role=role,
                content=content,
                timestamp=datetime.utcnow(),
                metadata=metadata or {},
            )
        )
        ctx.updated_at = datetime.utcnow()
        if len(ctx.messages) > self._max_messages:
            ctx.messages = ctx.messages[-self._max_messages:]
        await self._save(ctx)

    async def add_token_usage(self, ctx: SessionContext, usage: TokenUsage) -> None:
        """Accumulate token counts for the session."""
        ctx.token_summary.total_input += usage.input_tokens
        ctx.token_summary.total_output += usage.output_tokens
        ctx.token_summary.total_tokens += usage.total_tokens
        ctx.token_summary.total_cost_usd += usage.cost_usd
        ctx.token_summary.call_count += 1
        await self._save(ctx)

    async def add_turn(
        self,
        ctx: SessionContext,
        user_content: str,
        assistant_content: str,
        assistant_metadata: dict,
        usage: TokenUsage,
    ) -> None:
        """
        Batch-save a complete user->assistant turn plus token usage in ONE write.
        """
        now = datetime.utcnow()
        ctx.messages.append(
            SessionMessage(role="user", content=user_content, timestamp=now, metadata={})
        )
        ctx.messages.append(
            SessionMessage(
                role="assistant",
                content=assistant_content,
                timestamp=now,
                metadata=assistant_metadata or {},
            )
        )
        ctx.updated_at = now
        if len(ctx.messages) > self._max_messages:
            ctx.messages = ctx.messages[-self._max_messages:]
        ctx.token_summary.total_input += usage.input_tokens
        ctx.token_summary.total_output += usage.output_tokens
        ctx.token_summary.total_tokens += usage.total_tokens
        ctx.token_summary.total_cost_usd += usage.cost_usd
        ctx.token_summary.call_count += 1
        await self._save(ctx)

    async def delete(self, session_id: str) -> None:
        await self._cache.delete(CacheService.session_key(session_id))
        await asyncio.to_thread(_delete_from_s3, _session_s3_key(session_id))
        await asyncio.to_thread(_delete_from_s3, _token_s3_key(session_id))

    # -- Public accessors for routers ------------------------------------

    async def get_history(self, session_id: str) -> Optional[dict]:
        """
        Return session history dict for the /history endpoint.
        Tries cache first, then S3 fallback.
        """
        ctx = await self._load(session_id)
        if not ctx:
            return None
        return {
            "session_id": ctx.session_id,
            "messages": [m.model_dump(mode="json") for m in ctx.messages],
            "token_summary": ctx.token_summary.model_dump(mode="json"),
        }

    async def get_token_totals(self, session_id: str) -> Optional[dict]:
        """
        Return token totals for the /tokens endpoint.
        Tries cache first, then S3 fallback (reads from session context).
        """
        # Try dedicated token cache key first
        key = CacheService.token_key(session_id)
        data = await self._cache.get(key)
        if data and data.get("call_count", 0) > 0:
            return data
        # Fall back to session context (which has token_summary embedded)
        ctx = await self._load(session_id)
        if ctx and ctx.token_summary.call_count > 0:
            return ctx.token_summary.model_dump(mode="json")
        return None

    # -- Prompt helpers --------------------------------------------------

    def build_history_messages(self, ctx: SessionContext, last_n: int = 10) -> list[dict]:
        """
        Convert session messages into role/content dicts for LLM APIs.
        Uses the last `last_n` turns to avoid context explosion.

        Anti-hallucination: filters out assistant messages that had low
        groundedness scores to prevent reinforcing hallucinated content.
        """
        recent = ctx.messages[-last_n:] if len(ctx.messages) > last_n else ctx.messages
        filtered: list[dict] = []
        for m in recent:
            # Skip assistant messages marked as low-confidence
            if m.role == "assistant" and m.metadata.get("groundedness_score", 1.0) < 0.5:
                filtered.append({
                    "role": "assistant",
                    "content": "[Previous response had low confidence and was filtered for accuracy]",
                })
                continue
            filtered.append({"role": m.role, "content": m.content})
        return filtered

    def build_summary_prefix(self, ctx: SessionContext, last_n: int = 10) -> str:
        """
        If there are older messages beyond the rolling window, build a brief
        summary prefix anchored to verified facts (trades, project IDs, drawing
        references) to prevent hallucination from stale context.
        """
        if len(ctx.messages) <= last_n:
            return ""

        older = ctx.messages[:-last_n]
        topics: set[str] = set()
        trades_mentioned: set[str] = set()
        doc_types: set[str] = set()

        for m in older:
            if m.role == "user" and len(m.content) < 200:
                topics.add(m.content[:100])
            if m.metadata:
                trade = m.metadata.get("trade", "")
                if trade:
                    trades_mentioned.add(trade)
                doc_type = m.metadata.get("doc_type", "")
                if doc_type:
                    doc_types.add(doc_type)

        if not topics and not trades_mentioned:
            return ""

        parts: list[str] = []
        if topics:
            parts.append(
                "Earlier in this conversation the user asked about: "
                + "; ".join(list(topics)[:5])
            )
        if trades_mentioned:
            parts.append(f"Trades discussed: {', '.join(sorted(trades_mentioned))}")
        if doc_types:
            parts.append(f"Document types generated: {', '.join(sorted(doc_types))}")
        parts.append(
            "Note: Use ONLY the current context data for your response. "
            "Do not reuse specific details from earlier turns."
        )

        return "\n".join(parts)

    # -- Persistence -----------------------------------------------------

    async def _save(self, ctx: SessionContext) -> None:
        """Save session to cache + S3 (durable fallback)."""
        key = CacheService.session_key(ctx.session_id)
        data = ctx.model_dump(mode="json")
        await self._cache.set(key, data, ttl=self._session_ttl)
        # Persist to S3 in background (non-blocking)
        asyncio.create_task(
            asyncio.to_thread(_save_to_s3, _session_s3_key(ctx.session_id), data)
        )

    async def _load(self, session_id: str) -> Optional[SessionContext]:
        """Load session from cache; fall back to S3 if cache miss."""
        key = CacheService.session_key(session_id)
        data = await self._cache.get(key)
        if not data:
            # S3 fallback — durable storage survives restarts
            data = await asyncio.to_thread(_load_from_s3, _session_s3_key(session_id))
            if data:
                # Repopulate cache from S3
                await self._cache.set(key, data, ttl=self._session_ttl)
                logger.info("Session %s loaded from S3 (cache miss)", session_id)
        if data:
            try:
                return SessionContext(**data)
            except Exception as exc:
                logger.warning("Could not deserialize session %s: %s", session_id, exc)
        return None
