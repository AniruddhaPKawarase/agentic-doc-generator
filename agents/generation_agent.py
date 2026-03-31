"""
Master orchestrator for query -> intent -> retrieval -> generation pipeline.

Features:
  - Full pagination: fetches ALL records from MongoDB (no more 50-record limit)
  - Hallucination guard: informational groundedness score (never blocks output)
  - Granular token tracking: every pipeline step logs input/output/cost
  - Session memory: sliding window + anti-hallucination summary prefix
  - Semantic caching: normalized query keys catch repetitive similar questions
  - Streaming: SSE endpoint with token-by-token delivery
  - Scalable: handles 100k+ records via chunked context building

Latency optimisation:
  Phase 1 -- session load, pre-intent cache check, metadata: parallel gather()
  Phase 2 -- keyword intent (sync <1ms) then context + full intent + cache: parallel
  Doc-gen -- python-docx in thread-pool via asyncio.to_thread()
"""

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from agents.data_agent import DataAgent
from agents.intent_agent import IntentAgent
from config import get_settings
from models.schemas import (
    ChatRequest,
    ChatResponse,
    GeneratedDocument,
    HallucinationCheckResult,
    TokenUsage,
)
from services.cache_service import CacheService
from services.document_generator import DocumentGenerator
from services.hallucination_guard import HallucinationGuard
from services.session_service import SessionService
from services.sql_service import SQLService
from services.token_tracker import TokenTracker
from utils.token_counter import count_tokens

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT_TEMPLATE = """You are a Construction Intelligence AI specializing in comprehensive, professional scope of work documents.

Trade: {trade}
Task: {task_description}

## Required Output Format

Produce a COMPREHENSIVE exhibit document. Group ALL drawing notes into logical categories.
Include EVERY item found in the context -- do not summarise or truncate.

For EACH category write this EXACT block:

**[Category Name]**
Drawing Number(s): [ALL drawing numbers that contain notes for this category, comma-separated]
Material / Component:
[A thorough paragraph (5-10 sentences) listing every specific material, equipment tag,
 component, and installation detail found in the notes for this category.
 Name every piece of equipment by its tag (e.g. VRF-CU-C02, PTHP-1L-A, JP-1, SB-1).
 Include sizes, ratings, types, and specifications where mentioned.
 Use industry abbreviations: EMT, VFD, FSD, PTHP, GFI, ATS, HPWH, VRF, EUH, EHC, etc.]
CSI Division: [ALL relevant CSI codes with descriptions, comma-separated]
Trade Scope: [ALL applicable trades, comma-separated]

After ALL primary-trade categories, add:

----------------------------------------------------------------------------------------------------------------------------
Scope Under Different Trades

For EACH non-primary trade referenced in the drawing notes:

[Trade Name]
Drawing Number(s): [relevant drawings]
Material / Component:
[Full paragraph listing every item in the notes belonging to this trade -- tags, specs, sizes]
CSI Division: [relevant CSI codes]
Trade Scope: [applicable trades]

## Target Output Size
- This is a COMPREHENSIVE construction exhibit document.
- Include 12-20 primary-trade categories covering all scope areas.
- Each Material/Component paragraph must be 5-10 sentences (not bullet points).
- Include 4-8 secondary-trade sections under "Scope Under Different Trades".
- Target: 8 000-12 000 words total (approximately 10 000-15 000 tokens).
- Every drawing note in the context must appear in at least one category.

## Strict Rules
- Use ONLY data from the provided drawing notes context -- do NOT invent items.
- Every equipment tag, drawing number, and CSI code must come from the context.
- Use construction industry language: "furnish and install", "provide", "coordinate with".
- Do NOT use bullet points inside Material/Component -- write full paragraphs.
- Consolidate notes for the same component into one comprehensive description.
- CRITICAL: Only use drawing numbers that appear in the "Drawing Number Index" at the top
  of the context. Do NOT invent or abbreviate drawing numbers.

{metadata_block}
{drawing_anchor}"""

FOLLOW_UP_SYSTEM_PROMPT = """You are a Construction Intelligence assistant.
Given the scope document just generated for a specific trade, produce exactly {count} follow-up questions
that would help the user explore the scope further, clarify scope gaps, or generate related documents.

Rules:
- Questions must be specific to the trade and content of the generated scope.
- Mix question types: scope clarification, gap analysis, additional exhibits, cross-trade coordination.
- Keep each question concise (one sentence).
- Return ONLY a JSON array of strings. Example: ["Q1?", "Q2?", "Q3?"]
- No extra text, no numbering, no markdown -- ONLY the JSON array.
"""

TASK_DESCRIPTIONS: dict[str, str] = {
    "scope": "Create a comprehensive, detailed Scope of Work exhibit for {trade}. Cover every item, system, and component found in the drawing notes.",
    "exhibit": "Create a professional, comprehensive Exhibit -- Scope of Work for {trade}. Include all materials, equipment, CSI codes, and trade scopes from the drawing notes.",
    "report": "Create a comprehensive technical report for {trade} covering all systems, components, and specifications found in the drawing notes.",
    "takeoff": "Extract all quantities, sizes, and specifications as a detailed takeoff table for {trade}. List every tagged component with its specifications.",
    "specification": "Compile a comprehensive technical specification document for {trade}. Include every material, standard, and installation requirement from the drawing notes.",
    "extract": "Extract and list ALL {trade} items from the drawing notes. Every drawing number, component tag, and specification must be included.",
    "generate": "Generate a comprehensive, structured Scope of Work document for {trade}. Include all components, systems, and cross-trade references.",
}


class GenerationAgent:
    """Orchestrates the complete response pipeline."""

    def __init__(
        self,
        intent_agent: IntentAgent,
        data_agent: DataAgent,
        session_service: SessionService,
        token_tracker: TokenTracker,
        cache: CacheService,
        document_generator: DocumentGenerator,
        hallucination_guard: HallucinationGuard,
        sql_service: SQLService,
    ):
        self._intent = intent_agent
        self._data = data_agent
        self._sessions = session_service
        self._tokens = token_tracker
        self._cache = cache
        self._docgen = document_generator
        self._guard = hallucination_guard
        self._sql = sql_service
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def process(self, request: ChatRequest) -> ChatResponse:
        t_start = time.perf_counter()
        t: dict[str, int] = {}
        pipeline_log = self._tokens.create_pipeline_log()
        set_ids = request.set_ids or None

        # -- Phase 1: session + pre-intent cache + project metadata -- all parallel
        set_ids_suffix = ""
        if set_ids:
            set_ids_suffix = ":sets:" + "_".join(str(s) for s in sorted(str(s) for s in set_ids))
        pre_cache_key = CacheService.query_key(request.project_id, "" + set_ids_suffix, request.query)
        session, cached_raw, metadata, _name_result = await asyncio.gather(
            self._sessions.get_or_create(request.session_id, request.project_id),
            self._cache.get(pre_cache_key),
            self._data.get_project_metadata(request.project_id),
            self._sql.get_project_name(request.project_id),
        )
        project_display_name, _name_error = _name_result
        if _name_error:
            logger.info("Project name lookup failed project_id=%s: %s", request.project_id, _name_error)
        t["phase1"] = int((time.perf_counter() - t_start) * 1000)
        pipeline_log.record_step("phase1_parallel")

        if cached_raw:
            return await self._response_from_cache(cached_raw, session, request.query, t_start, project_display_name)

        available_trades = metadata.get("trades", [])
        project_csi = metadata.get("csi_divisions", [])
        self._intent.update_trades(available_trades)

        # -- Phase 2: keyword intent (sync) -> context + full intent + cache -- parallel
        prelim_intent = self._intent.detect_sync(request.query, available_trades)
        prelim_cache_key = CacheService.query_key(
            request.project_id, prelim_intent.trade + set_ids_suffix, request.query
        )

        (context_block, _ctx_stats), intent, prelim_cached = await asyncio.gather(
            self._data.prepare_context(
                request.project_id,
                prelim_intent,
                available_trades=available_trades,
                project_csi=project_csi,
                set_ids=set_ids,
            ),
            self._intent.detect(request.query, available_trades),
            self._cache.get(prelim_cache_key),
        )
        t["phase2"] = int((time.perf_counter() - t_start) * 1000)
        pipeline_log.record_step(
            "phase2_context_intent",
            input_tokens=_ctx_stats.get("raw_tokens", 0),
        )

        if prelim_cached:
            return await self._response_from_cache(prelim_cached, session, request.query, t_start, project_display_name)

        cache_key = CacheService.query_key(request.project_id, intent.trade + set_ids_suffix, request.query)

        if intent.trade != prelim_intent.trade:
            trade_cached = await self._cache.get(cache_key)
            if trade_cached:
                return await self._response_from_cache(trade_cached, session, request.query, t_start, project_display_name)
            context_block, _ctx_stats = await self._data.prepare_context(
                request.project_id,
                intent,
                available_trades=available_trades,
                project_csi=project_csi,
                set_ids=set_ids,
            )
            t["context_rebuild"] = int((time.perf_counter() - t_start) * 1000)
            logger.info(
                "Context rebuilt for corrected trade=%s drawings=%d",
                intent.trade, _ctx_stats.get("unique_drawings", 0),
            )

        # -- Empty-result check for set_ids filter -------------------------
        set_names: list[str] = _ctx_stats.get("set_names", [])
        if set_ids and _ctx_stats.get("total_records", 0) == 0:
            pipeline_ms = int((time.perf_counter() - t_start) * 1000)
            return ChatResponse(
                session_id=session.session_id,
                project_name=project_display_name,
                answer=(
                    f"No records found for trade **{intent.trade}** with "
                    f"set ID(s) **{', '.join(str(s) for s in set_ids)}** "
                    f"in project {request.project_id}. "
                    "Please verify the trade name and set ID(s) are correct."
                ),
                set_ids=set_ids,
                set_names=[],
                intent=intent,
                pipeline_ms=pipeline_ms,
                cached=False,
            )

        # -- Build system prompt and user message -------------------------
        task_template = TASK_DESCRIPTIONS.get(intent.document_type, TASK_DESCRIPTIONS["generate"])
        task_description = task_template.format(trade=intent.trade or "General")

        # Include set metadata in the metadata block when filtering by set
        set_metadata = ""
        if set_ids and set_names:
            set_metadata = (
                f"\nSet Filter: {', '.join(set_names)} "
                f"(IDs: {', '.join(str(s) for s in set_ids)})\n"
            )

        metadata_block = self._data._builder.build_metadata_summary_sync(
            request.project_id,
            available_trades,
            project_csi,
        )
        if set_metadata:
            metadata_block += set_metadata

        # Inject authoritative drawing-number anchor to prevent hallucination.
        # All drawing numbers are extracted programmatically from the fetched
        # records BEFORE the LLM call — the LLM is explicitly told to use only these.
        drawing_anchor = self._build_drawing_anchor(_ctx_stats.get("all_drawing_numbers", []))

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            trade=intent.trade or "General",
            task_description=task_description,
            metadata_block=metadata_block,
            drawing_anchor=drawing_anchor,
        )

        history_summary = self._sessions.build_summary_prefix(session)
        history_messages = self._sessions.build_history_messages(session, last_n=8)

        user_message = (
            (f"[Conversation summary]\n{history_summary}\n\n" if history_summary else "")
            + f"### Context\n{context_block}\n\n"
            + f"### User Request\n{request.query}"
        )

        trimmed_context, estimated_input = self._tokens.enforce_context_budget(
            system_prompt=system_prompt,
            context_block=user_message,
            history_messages=history_messages,
            user_query="",
        )
        final_user_message = trimmed_context or user_message
        t["pre_llm"] = int((time.perf_counter() - t_start) * 1000)
        pipeline_log.record_step("pre_llm_budget", input_tokens=estimated_input)

        # -- LLM generation (critical path) --------------------------------
        answer, usage = await self._generate_with_openai(
            system_prompt=system_prompt,
            history_messages=history_messages,
            user_message=final_user_message,
            estimated_input_tokens=estimated_input,
        )
        t["llm"] = int((time.perf_counter() - t_start) * 1000)
        pipeline_log.record_step(
            "llm_generation",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )

        # -- Hallucination guard (informational — never blocks generation) --
        guard_result = self._run_guard(answer, context_block, intent)
        # Validate drawing numbers against authoritative list (diagnostic log only)
        self._validate_drawing_numbers(answer, _ctx_stats.get("all_drawing_numbers", []))
        needs_clarification = False
        clarification_questions: list[str] = []

        # -- Document generation + follow-up questions -- parallel ----------
        docgen_coro = asyncio.to_thread(
            self._docgen.generate_sync,
            content=answer,
            project_id=request.project_id,
            project_name=project_display_name,
            trade=intent.trade or "General",
            document_type=intent.document_type,
            set_ids=set_ids,
            set_names=set_names,
        ) if request.generate_document else _noop_coro()

        followup_coro = self._generate_follow_up_questions(
            answer=answer,
            query=request.query,
            trade=intent.trade or "General",
            document_type=intent.document_type,
        )

        doc_result, follow_up_questions = await asyncio.gather(
            docgen_coro, followup_coro, return_exceptions=True
        )

        generated_doc: Optional[GeneratedDocument] = None
        if request.generate_document and not isinstance(doc_result, BaseException):
            generated_doc = doc_result
        elif isinstance(doc_result, BaseException):
            logger.error("Document generation failed: %s", doc_result)

        if isinstance(follow_up_questions, BaseException):
            logger.warning("Follow-up question generation failed: %s", follow_up_questions)
            follow_up_questions = []

        pipeline_ms = int((time.perf_counter() - t_start) * 1000)
        t["total"] = pipeline_ms
        pipeline_log.record_step("total_pipeline")

        token_log_summary = pipeline_log.summary()

        response = ChatResponse(
            session_id=session.session_id,
            project_name=project_display_name,
            answer=answer,
            set_ids=set_ids,
            set_names=set_names,
            document=generated_doc,
            intent=intent,
            token_usage=usage,
            groundedness_score=guard_result.confidence_score,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions,
            follow_up_questions=follow_up_questions,
            pipeline_ms=pipeline_ms,
            cached=False,
            token_log=token_log_summary,
        )

        # Persist session + tokens + cache -- parallel
        assistant_metadata = {
            "trade": intent.trade,
            "doc_type": intent.document_type,
            "groundedness_score": guard_result.confidence_score,
        }
        persist_tasks: list = [
            self._sessions.add_turn(
                session,
                user_content=request.query,
                assistant_content=answer,
                assistant_metadata=assistant_metadata,
                usage=usage,
            ),
            self._tokens.accumulate_session_tokens(session.session_id, usage),
            self._cache.set(
                cache_key,
                response.model_dump(mode="json"),
                ttl=settings.cache_ttl_query,
            ),
        ]
        await asyncio.gather(*persist_tasks)

        logger.info(
            "Pipeline complete trade=%s type=%s total_tokens=%d ms=%d "
            "groundedness=%.2f "
            "[phase1=%d phase2=%d pre_llm=%d llm=%d]",
            intent.trade,
            intent.document_type,
            usage.total_tokens,
            t["total"],
            guard_result.confidence_score,
            t["phase1"],
            t["phase2"] - t["phase1"],
            t["pre_llm"] - t["phase2"],
            t["llm"] - t["pre_llm"],
        )
        return response

    async def process_stream(self, request: ChatRequest) -> AsyncIterator[dict]:
        """
        Streaming variant of process().

        Yields Server-Sent Event dicts:
          {"type": "token",    "delta": "..."}
          {"type": "metadata", "intent": {...}, ...}
          {"type": "done",     "response": <ChatResponse dict>}
        """
        t_start = time.perf_counter()
        pipeline_log = self._tokens.create_pipeline_log()
        set_ids = request.set_ids or None

        # -- Phase 1: parallel session + cache + metadata ------------------
        set_ids_suffix = ""
        if set_ids:
            set_ids_suffix = ":sets:" + "_".join(str(s) for s in sorted(str(s) for s in set_ids))
        pre_cache_key = CacheService.query_key(request.project_id, "" + set_ids_suffix, request.query)
        session, cached_raw, metadata, _name_result = await asyncio.gather(
            self._sessions.get_or_create(request.session_id, request.project_id),
            self._cache.get(pre_cache_key),
            self._data.get_project_metadata(request.project_id),
            self._sql.get_project_name(request.project_id),
        )
        project_display_name, _name_error = _name_result
        if _name_error:
            logger.info("Project name lookup failed project_id=%s: %s", request.project_id, _name_error)
        pipeline_log.record_step("phase1_parallel")

        if cached_raw:
            response = ChatResponse(**cached_raw)
            response.session_id = session.session_id
            response.project_name = project_display_name
            response.cached = True
            response.pipeline_ms = int((time.perf_counter() - t_start) * 1000)
            await self._sessions.add_message(session, "user", request.query)
            await self._sessions.add_message(session, "assistant", response.answer)
            chunk_size = 80
            for i in range(0, len(response.answer), chunk_size):
                yield {"type": "token", "delta": response.answer[i:i + chunk_size]}
            yield {"type": "done", "response": response.model_dump(mode="json")}
            return

        available_trades = metadata.get("trades", [])
        project_csi = metadata.get("csi_divisions", [])
        self._intent.update_trades(available_trades)

        # -- Phase 2: keyword intent + context + cache -- parallel ---------
        prelim_intent = self._intent.detect_sync(request.query, available_trades)
        prelim_cache_key = CacheService.query_key(
            request.project_id, prelim_intent.trade + set_ids_suffix, request.query
        )

        (context_block, _ctx_stats), intent, prelim_cached = await asyncio.gather(
            self._data.prepare_context(
                request.project_id,
                prelim_intent,
                available_trades=available_trades,
                project_csi=project_csi,
                set_ids=set_ids,
            ),
            self._intent.detect(request.query, available_trades),
            self._cache.get(prelim_cache_key),
        )
        pipeline_log.record_step(
            "phase2_context_intent",
            input_tokens=_ctx_stats.get("raw_tokens", 0),
        )

        if prelim_cached:
            response = ChatResponse(**prelim_cached)
            response.session_id = session.session_id
            response.project_name = project_display_name
            response.cached = True
            response.pipeline_ms = int((time.perf_counter() - t_start) * 1000)
            await self._sessions.add_message(session, "user", request.query)
            await self._sessions.add_message(session, "assistant", response.answer)
            chunk_size = 80
            for i in range(0, len(response.answer), chunk_size):
                yield {"type": "token", "delta": response.answer[i:i + chunk_size]}
            yield {"type": "done", "response": response.model_dump(mode="json")}
            return

        if intent.trade != prelim_intent.trade:
            cache_key_final = CacheService.query_key(request.project_id, intent.trade + set_ids_suffix, request.query)
            trade_cached = await self._cache.get(cache_key_final)
            if trade_cached:
                response = ChatResponse(**trade_cached)
                response.session_id = session.session_id
                response.project_name = project_display_name
                response.cached = True
                response.pipeline_ms = int((time.perf_counter() - t_start) * 1000)
                await self._sessions.add_message(session, "user", request.query)
                await self._sessions.add_message(session, "assistant", response.answer)
                chunk_size = 80
                for i in range(0, len(response.answer), chunk_size):
                    yield {"type": "token", "delta": response.answer[i:i + chunk_size]}
                yield {"type": "done", "response": response.model_dump(mode="json")}
                return
            context_block, _ctx_stats = await self._data.prepare_context(
                request.project_id,
                intent,
                available_trades=available_trades,
                project_csi=project_csi,
                set_ids=set_ids,
            )

        cache_key = CacheService.query_key(request.project_id, intent.trade + set_ids_suffix, request.query)

        # -- Empty-result check for set_ids filter (streaming) ----------------
        set_names_stream: list[str] = _ctx_stats.get("set_names", [])
        if set_ids and _ctx_stats.get("total_records", 0) == 0:
            error_msg = (
                f"No records found for trade **{intent.trade}** with "
                f"set ID(s) **{', '.join(str(s) for s in set_ids)}** "
                f"in project {request.project_id}. "
                "Please verify the trade name and set ID(s) are correct."
            )
            yield {"type": "token", "delta": error_msg}
            response = ChatResponse(
                session_id=session.session_id,
                project_name=project_display_name,
                answer=error_msg,
                set_ids=set_ids,
                set_names=[],
                intent=intent,
                pipeline_ms=int((time.perf_counter() - t_start) * 1000),
                cached=False,
            )
            yield {"type": "done", "response": response.model_dump(mode="json")}
            return

        # Emit metadata event
        yield {"type": "metadata", "intent": intent.model_dump(), "trade": intent.trade}

        # -- Build prompts -------------------------------------------------
        task_template = TASK_DESCRIPTIONS.get(intent.document_type, TASK_DESCRIPTIONS["generate"])
        task_description = task_template.format(trade=intent.trade or "General")

        set_metadata_stream = ""
        if set_ids and set_names_stream:
            set_metadata_stream = (
                f"\nSet Filter: {', '.join(set_names_stream)} "
                f"(IDs: {', '.join(str(s) for s in set_ids)})\n"
            )

        metadata_block = self._data._builder.build_metadata_summary_sync(
            request.project_id, available_trades, project_csi
        )
        if set_metadata_stream:
            metadata_block += set_metadata_stream

        drawing_anchor = self._build_drawing_anchor(_ctx_stats.get("all_drawing_numbers", []))
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            trade=intent.trade or "General",
            task_description=task_description,
            metadata_block=metadata_block,
            drawing_anchor=drawing_anchor,
        )
        history_summary = self._sessions.build_summary_prefix(session)
        history_messages = self._sessions.build_history_messages(session, last_n=8)
        user_message = (
            (f"[Conversation summary]\n{history_summary}\n\n" if history_summary else "")
            + f"### Context\n{context_block}\n\n"
            + f"### User Request\n{request.query}"
        )
        trimmed_context, estimated_input = self._tokens.enforce_context_budget(
            system_prompt=system_prompt,
            context_block=user_message,
            history_messages=history_messages,
            user_query="",
        )
        final_user_message = trimmed_context or user_message
        pipeline_log.record_step("pre_llm_budget", input_tokens=estimated_input)

        # -- Streaming LLM call --------------------------------------------
        answer_chunks: list[str] = []
        input_tokens = estimated_input
        output_tokens = 0

        if self._client:
            try:
                input_messages: list[dict] = [{"role": "system", "content": system_prompt}]
                for msg in history_messages:
                    role = msg.get("role", "user")
                    if role in {"user", "assistant"}:
                        input_messages.append({"role": role, "content": str(msg.get("content", ""))})
                input_messages.append({"role": "user", "content": final_user_message})

                stream = await self._client.chat.completions.create(
                    model=settings.openai_model,
                    messages=input_messages,
                    max_tokens=settings.max_output_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        delta = chunk.choices[0].delta.content
                        answer_chunks.append(delta)
                        yield {"type": "token", "delta": delta}
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens

            except Exception as exc:
                logger.error("Streaming generation failed: %s", exc)
                fallback = "Generation error. Please retry."
                yield {"type": "token", "delta": fallback}
                answer_chunks = [fallback]
        else:
            msg = "OpenAI not configured. Set OPENAI_API_KEY in .env."
            yield {"type": "token", "delta": msg}
            answer_chunks = [msg]

        answer = "".join(answer_chunks)
        if not output_tokens:
            output_tokens = count_tokens(answer)
        usage = self._tokens.record_usage(int(input_tokens), int(output_tokens))
        pipeline_log.record_step(
            "llm_generation",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
        )

        # -- Hallucination guard (informational — never blocks generation) --
        guard_result = self._run_guard(answer, context_block, intent)
        self._validate_drawing_numbers(answer, _ctx_stats.get("all_drawing_numbers", []))
        needs_clarification = False

        # -- Document generation + follow-up questions -- parallel ----------
        docgen_coro = asyncio.to_thread(
            self._docgen.generate_sync,
            content=answer,
            project_id=request.project_id,
            project_name=project_display_name,
            trade=intent.trade or "General",
            document_type=intent.document_type,
            set_ids=set_ids,
            set_names=set_names_stream,
        ) if request.generate_document else _noop_coro()

        followup_coro = self._generate_follow_up_questions(
            answer=answer,
            query=request.query,
            trade=intent.trade or "General",
            document_type=intent.document_type,
        )

        doc_result, follow_up_questions = await asyncio.gather(
            docgen_coro, followup_coro, return_exceptions=True
        )

        generated_doc: Optional[GeneratedDocument] = None
        if request.generate_document and not isinstance(doc_result, BaseException):
            generated_doc = doc_result
        elif isinstance(doc_result, BaseException):
            logger.error("Document generation failed: %s", doc_result)

        if isinstance(follow_up_questions, BaseException):
            logger.warning("Follow-up question generation failed: %s", follow_up_questions)
            follow_up_questions = []

        pipeline_ms = int((time.perf_counter() - t_start) * 1000)
        pipeline_log.record_step("total_pipeline")
        token_log_summary = pipeline_log.summary()

        response = ChatResponse(
            session_id=session.session_id,
            project_name=project_display_name,
            answer=answer,
            set_ids=set_ids,
            set_names=set_names_stream,
            document=generated_doc,
            intent=intent,
            token_usage=usage,
            groundedness_score=guard_result.confidence_score,
            needs_clarification=needs_clarification,
            clarification_questions=[],
            follow_up_questions=follow_up_questions,
            pipeline_ms=pipeline_ms,
            cached=False,
            token_log=token_log_summary,
        )

        # Persist
        assistant_metadata = {
            "trade": intent.trade,
            "doc_type": intent.document_type,
            "groundedness_score": guard_result.confidence_score,
        }
        persist_tasks = [
            self._sessions.add_turn(
                session,
                user_content=request.query,
                assistant_content=answer,
                assistant_metadata=assistant_metadata,
                usage=usage,
            ),
            self._tokens.accumulate_session_tokens(session.session_id, usage),
            self._cache.set(
                cache_key,
                response.model_dump(mode="json"),
                ttl=settings.cache_ttl_query,
            ),
        ]
        await asyncio.gather(*persist_tasks)

        yield {"type": "done", "response": response.model_dump(mode="json")}

    # -- Shared helpers ---------------------------------------------------

    @staticmethod
    def _build_drawing_anchor(drawing_numbers: list[str]) -> str:
        """
        Build the authoritative drawing-number anchor injected into the system prompt.

        This is the primary mechanism preventing drawing-number hallucination:
        the LLM receives an explicit, exhaustive list of valid drawing numbers
        extracted programmatically from the fetched data, and is instructed to
        use ONLY numbers from this list.

        Capped at 600 entries to avoid bloating the system prompt excessively
        (600 × ~6 chars avg = ~3,600 chars ≈ ~900 tokens overhead).
        """
        # Strip any sentinel values — they must never appear in the LLM anchor.
        drawing_numbers = [
            dn for dn in drawing_numbers
            if dn and dn not in ("__NO_DRAWING__", "Unknown", "unknown")
        ]
        if not drawing_numbers:
            return ""

        cap = 600
        shown = drawing_numbers[:cap]
        omitted = len(drawing_numbers) - len(shown)

        dn_str = ", ".join(shown)
        if omitted:
            dn_str += f" (+ {omitted} more — all listed in Drawing Number Index above)"

        return (
            f"\n## AUTHORITATIVE DRAWING NUMBER LIST\n"
            f"Total drawings in this project/trade: {len(drawing_numbers)}\n"
            f"Valid drawing numbers: {dn_str}\n"
            f"MANDATORY RULE: You MUST use ONLY drawing numbers from the list above "
            f"when filling in 'Drawing Number(s)' fields. "
            f"Do NOT invent, abbreviate, or modify drawing numbers.\n"
        )

    @staticmethod
    def _validate_drawing_numbers(answer: str, valid_numbers: list[str]) -> None:
        """
        Post-generation informational check: log any drawing numbers in the LLM
        response that are not in the authoritative list.

        This is diagnostic only — it never blocks or modifies the response.
        """
        if not valid_numbers:
            return
        import re
        valid_set = {dn.strip().upper() for dn in valid_numbers}
        # Match patterns like E-101, P-101A, S-101.1, A1.01, G-001, etc.
        found = re.findall(r'\b([A-Z]{1,3}-?\d{2,4}[A-Z0-9.]*)\b', answer.upper())
        invented = [f for f in set(found) if f not in valid_set]
        if invented:
            logger.warning(
                "Drawing-number validation: %d potentially invented numbers found: %s",
                len(invented), ", ".join(sorted(invented)[:20]),
            )
        else:
            logger.debug("Drawing-number validation: all drawing numbers match source data.")

    def _run_guard(
        self,
        answer: str,
        context_block: str,
        intent,
    ) -> HallucinationCheckResult:
        """Run hallucination guard — informational only, never blocks."""
        if not self._client:
            return HallucinationCheckResult(
                is_reliable=True,
                confidence_score=0.0,
                unsupported_claims=[],
                clarification_questions=[],
                recommendation="proceed",
            )
        return self._guard.check(
            llm_response=answer,
            source_context=context_block,
            trade=intent.trade or "General",
            document_type=intent.document_type,
        )

    async def _generate_follow_up_questions(
        self,
        answer: str,
        query: str,
        trade: str,
        document_type: str,
    ) -> list[str]:
        """
        Generate contextual follow-up question suggestions using a fast secondary
        LLM call (max 400 tokens).
        """
        if not self._client or not settings.follow_up_questions_enabled:
            return self._default_follow_up_questions(trade, document_type)

        count = settings.follow_up_questions_count
        scope_preview = answer[:2000]

        system = FOLLOW_UP_SYSTEM_PROMPT.format(count=count)
        user_msg = (
            f"Trade: {trade}\n"
            f"Document type: {document_type}\n"
            f"Original query: {query}\n\n"
            f"Generated scope preview:\n{scope_preview}"
        )

        try:
            resp = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=settings.follow_up_max_tokens,
                temperature=0.4,
            )
            raw = (resp.choices[0].message.content or "").strip()

            import json, re
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                questions = json.loads(match.group())
                if isinstance(questions, list) and questions:
                    return [str(q).strip() for q in questions[:count] if q]

        except Exception as exc:
            logger.warning("Follow-up question LLM call failed: %s", exc)

        return self._default_follow_up_questions(trade, document_type)

    @staticmethod
    def _default_follow_up_questions(trade: str, document_type: str) -> list[str]:
        """Safe fallback follow-up questions when the LLM call fails."""
        return [
            f"Are there any scope gaps or unassigned items in the {trade} scope?",
            f"Which drawings have the most {trade} scope items that need coordination?",
            f"Can you generate a {trade} takeoff with quantities and specifications?",
        ]

    async def _response_from_cache(
        self,
        cached_raw: dict,
        session: object,
        query: str,
        start_time: float,
        project_display_name: str = "",
    ) -> ChatResponse:
        response = ChatResponse(**cached_raw)
        response.session_id = session.session_id
        response.project_name = project_display_name or response.project_name
        response.cached = True
        response.pipeline_ms = int((time.perf_counter() - start_time) * 1000)
        await self._sessions.add_message(session, "user", query)
        await self._sessions.add_message(session, "assistant", response.answer)
        return response

    async def _generate_with_openai(
        self,
        system_prompt: str,
        history_messages: list[dict],
        user_message: str,
        estimated_input_tokens: int,
    ) -> tuple[str, TokenUsage]:
        if not self._client:
            fallback = (
                "OpenAI is not configured. Please set OPENAI_API_KEY in .env "
                "and restart the service."
            )
            usage = self._tokens.record_usage(0, count_tokens(fallback))
            return fallback, usage

        try:
            input_messages: list[dict] = [{"role": "system", "content": system_prompt}]
            for message in history_messages:
                role = message.get("role", "user")
                if role not in {"user", "assistant"}:
                    continue
                input_messages.append({"role": role, "content": str(message.get("content", ""))})
            input_messages.append({"role": "user", "content": user_message})

            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=input_messages,
                max_tokens=settings.max_output_tokens,
                temperature=0.2,
            )

            answer = (response.choices[0].message.content or "").strip()
            if not answer:
                answer = "I could not generate a response from the current context."

            usage_obj = response.usage
            input_tokens = getattr(usage_obj, "prompt_tokens", None) if usage_obj else None
            output_tokens = getattr(usage_obj, "completion_tokens", None) if usage_obj else None
            if input_tokens is None:
                input_tokens = estimated_input_tokens
            if output_tokens is None:
                output_tokens = count_tokens(answer)

            usage = self._tokens.record_usage(int(input_tokens), int(output_tokens))
            return answer, usage

        except Exception as exc:
            logger.error("OpenAI generation failed: %s", exc)
            fallback = (
                "I hit an error while generating the response. "
                "Please retry with a more specific trade or document request."
            )
            usage = self._tokens.record_usage(estimated_input_tokens, count_tokens(fallback))
            return fallback, usage

async def _noop_coro():
    """No-op coroutine to replace disabled doc-gen."""
    return None