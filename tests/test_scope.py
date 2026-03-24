"""
tests/test_scope.py — Standalone testing module for scope / exhibit generation.

Loads trade data from 'Scope Gap - Electrical.xlsx' (or any Excel file),
runs the full intent → context → LLM → Word pipeline, and saves a formatted
exhibit document closely matching the sample Word files:
  • Exhibit Electrical Scope of Work Lighting Drawing Number(s).docx
  • Exhibit Melrose Claremont 404 Project Summary BPP Scope of Work.docx

Reference document token sizes (measured):
  Doc1: 4 348 tokens  |  Doc2: 7 896 tokens
Target generated output: 8 000–10 000 tokens in the final Word file.
LLM max_output_tokens is set to 3 000 which produces ~2 300 words — enough
content to fill an exhibit within the 8k–10k token target when formatted.

Usage:
    python tests/test_scope.py                              # interactive
    python tests/test_scope.py --query "Generate exhibit for electrical"
    python tests/test_scope.py --batch                      # all trades
    python tests/test_scope.py --stream                     # streaming output
    python tests/test_scope.py --excel path/to/file.xlsx    # custom data

Environment:
    OPENAI_API_KEY must be set in .env or environment.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

# Allow imports from project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from openai import AsyncOpenAI

from tests.excel_loader import ExcelDataLoader
from services.exhibit_document_generator import ExhibitDocumentGenerator
from utils.token_counter import count_tokens

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "20000"))

# 14 000 output tokens ≈ 10 500 words → generates 15 000–20 000 token Word docs.
# gpt-4.1-mini supports up to 16 384 output tokens.
# Use --stream flag for best UX at this output size (tokens appear in real time).
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "14000"))

# Number of follow-up question suggestions to generate after each response.
FOLLOW_UP_QUESTIONS_COUNT = int(os.getenv("FOLLOW_UP_QUESTIONS_COUNT", "3"))

# ── System prompts ────────────────────────────────────────────────────
#
# EXHIBIT_SYSTEM_PROMPT mirrors the structure of the two sample Word files.
# Doc1 uses category-level sections (Lighting, Power, HVAC, …) each with
# Drawing Number(s), Material/Component, CSI Division, Trade Scope fields.
# Doc2 uses a list format: item name, Drawings, CSI, Scope statement.
# We target the Doc1 style as it is more information-dense.

EXHIBIT_SYSTEM_PROMPT = """You are a Construction Scope of Work Specialist.

You are given structured drawing notes for a specific trade from a construction project.
Produce a COMPREHENSIVE, professional "Exhibit — Scope of Work" document.

## Required Section Structure

Group ALL drawing notes into 12–20 logical categories (e.g. Lighting, Building Power &
Receptacles, Site / Garage Power, Elevator, HVAC & Mechanical Systems, Plumbing & Water
Systems, Fire & Security Systems, Communications & Low Voltage, Appliances & Equipment,
Labelling & Code Compliance, Architectural & General, Structural, etc.).

For EACH category write:

**[Category Name]**
Drawing Number(s): [ALL drawing numbers containing notes for this category]
Material / Component:
[A thorough paragraph (5–10 sentences). Name every specific material, equipment tag
(e.g. VRF-CU-C02, PTHP-1L-A, JP-1, SB-1), component, size, and installation detail
found in the drawing notes for this category. Use industry abbreviations: EMT, VFD, FSD,
PTHP, GFI, ATS, HPWH, VRF, EUH, EHC, RGS, NEMA, etc.]
CSI Division: [ALL relevant CSI codes with short descriptions, comma-separated]
Trade Scope: [ALL applicable trades, comma-separated]

After all primary-trade categories add a separator line then:

----------------------------------------------------------------------------------------------------------------------------
Scope Under Different Trades

For EACH other trade referenced in the notes:

[Trade Name]
Drawing Number(s): [drawings referencing this trade]
Material / Component:
[Full paragraph — every item in the notes belonging to this trade, with tags and specs]
CSI Division: [relevant CSI codes]
Trade Scope: [applicable trades]

## Target Output Size
- Include 12–20 primary-trade categories.
- Each Material/Component paragraph must be 5–10 sentences (no bullet points).
- Include 4–8 secondary-trade sections.
- Target: 8 000–12 000 words total (approximately 10 000–15 000 tokens).
- Every drawing note in the context must appear in at least one category.

## Strict Rules
- Use ONLY data from the provided drawing notes — never invent items.
- Every equipment tag, drawing number, and CSI code must come from the notes.
- Do NOT use bullet points inside Material/Component — write full paragraphs.
- Consolidate near-duplicate notes into one comprehensive description.
- Use construction industry language: "furnish and install", "provide", "coordinate with".
"""

TRADE_SYSTEM_PROMPT = """You are a Construction Scope of Work Specialist.

Trade: {trade}
Task: {task}
Project: {project_name}
Available CSI Divisions: {csi_list}

## Required Section Structure
Group ALL drawing notes into 12–20 logical categories. For each category:

**[Category Name]**
Drawing Number(s): [ALL relevant drawings]
Material / Component:
[Thorough paragraph (5–10 sentences) — every specific item, equipment tag,
 material, and specification from the notes. No bullet points.]
CSI Division: [ALL relevant CSI codes]
Trade Scope: [ALL applicable trades]

## Target Output Size
- 12–20 categories covering all scope areas.
- Target: 8 000–12 000 words (10 000–15 000 tokens).
- Every drawing note must appear somewhere.

## Rules
- Use ONLY the provided drawing notes — no invented items.
- Write full paragraphs, not bullet points, for Material/Component.
- Use construction industry language.
"""

FOLLOW_UP_SYSTEM_PROMPT = """You are a Construction Intelligence assistant.
Given the scope document just generated for a specific trade, produce exactly {count} follow-up questions
that would help the user explore the scope further, identify scope gaps, or generate related documents.

Rules:
- Questions must be specific to the trade and content of the generated scope.
- Mix types: scope clarification, gap analysis, additional exhibits, cross-trade coordination.
- Keep each question concise (one sentence).
- Return ONLY a JSON array of strings. Example: ["Q1?", "Q2?", "Q3?"]
- No extra text, no numbering, no markdown — ONLY the JSON array.
"""


# ── In-process session (no Redis needed for testing) ────────────────

class InMemorySession:
    """Lightweight conversation session for the test CLI."""

    def __init__(self):
        self.session_id = str(uuid.uuid4())[:8]
        self.messages: list[dict] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def history_for_llm(self, last_n: int = 6) -> list[dict]:
        """Return last N turns for LLM context (2 messages per turn)."""
        return self.messages[-(last_n * 2):]

    def token_report(self) -> str:
        total = self.total_input_tokens + self.total_output_tokens
        cost = (
            self.total_input_tokens / 1_000_000 * 0.40
            + self.total_output_tokens / 1_000_000 * 1.60
        )
        return (
            f"Session {self.session_id} | "
            f"Input: {self.total_input_tokens:,} | "
            f"Output: {self.total_output_tokens:,} | "
            f"Total: {total:,} tokens | "
            f"Est. cost: ${cost:.4f}"
        )


# ── Intent detection (keyword-only, <1 ms) ──────────────────────────

TRADE_ALIASES: dict[str, str] = {
    "electrical": "Electrical",
    "electric": "Electrical",
    "elec": "Electrical",
    "plumbing": "Plumbing",
    "plumb": "Plumbing",
    "hvac": "HVAC",
    "mechanical": "Mechanical",
    "mech": "Mechanical",
    "structural": "Structural",
    "structure": "Structural",
    "architecture": "Architecture",
    "arch": "Architecture",
    "sprinkler": "Sprinkler",
    "fire protection": "Fire Protection",
    "fire": "Fire Protection",
    "interior": "Interior Design",
    "civil": "Civil",
    "sitework": "Sitework",
    "specialty": "Specialty Trade",
}

DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "exhibit": ["exhibit", "schedule"],
    "scope": ["scope", "sow", "scope of work"],
    "report": ["report", "full report"],
    "takeoff": ["takeoff", "take-off", "quantities", "takeoffs"],
    "specification": ["specification", "spec"],
    "extract": ["extract", "list all", "pull out"],
}


def detect_intent(query: str, available_trades: list[str]) -> dict:
    """Fast keyword intent detection — no I/O, <1 ms."""
    q = query.lower()

    trade = ""
    # 1. Direct match against available trades (case-insensitive)
    for t in available_trades:
        if t.lower() in q:
            trade = t
            break
    # 2. Alias lookup
    if not trade:
        for alias, canonical in TRADE_ALIASES.items():
            if alias in q:
                trade = canonical
                break
    # 3. Fallback to first available trade
    if not trade and available_trades:
        trade = available_trades[0]

    doc_type = "scope"
    for dtype, keywords in DOC_TYPE_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            doc_type = dtype
            break

    return {"trade": trade, "document_type": doc_type}


# ── Token helpers ────────────────────────────────────────────────────

def _truncate_tokens(text: str, max_tokens: int) -> str:
    from utils.token_counter import truncate_to_token_budget
    result, _ = truncate_to_token_budget(text, max_tokens)
    return result


# ── LLM calls ────────────────────────────────────────────────────────

async def call_llm(
    client: AsyncOpenAI,
    system_prompt: str,
    user_message: str,
    history: list[dict],
    model: str = DEFAULT_MODEL,
) -> tuple[str, int, int]:
    """
    Non-streaming LLM call.
    Returns (answer, input_tokens, output_tokens).
    Trims context to MAX_CONTEXT_TOKENS before calling.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    # Token budget guard
    total_ctx = sum(count_tokens(m["content"]) for m in messages)
    if total_ctx > MAX_CONTEXT_TOKENS:
        overhead = sum(count_tokens(m["content"]) for m in messages[:-1])
        available = max(500, MAX_CONTEXT_TOKENS - overhead - 200)
        user_message = _truncate_tokens(user_message, available)
        messages[-1]["content"] = user_message
        logger.warning(
            "Context trimmed %d → %d tokens (budget=%d)",
            total_ctx, available + overhead, MAX_CONTEXT_TOKENS,
        )

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
    )

    answer = response.choices[0].message.content or ""
    input_tokens = response.usage.prompt_tokens if response.usage else count_tokens(str(messages))
    output_tokens = response.usage.completion_tokens if response.usage else count_tokens(answer)
    return answer, input_tokens, output_tokens


async def call_llm_stream(
    client: AsyncOpenAI,
    system_prompt: str,
    user_message: str,
    history: list[dict],
    model: str = DEFAULT_MODEL,
) -> tuple[str, int, int]:
    """
    Streaming LLM call — prints tokens as they arrive, returns full answer.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    total_ctx = sum(count_tokens(m["content"]) for m in messages)
    if total_ctx > MAX_CONTEXT_TOKENS:
        overhead = sum(count_tokens(m["content"]) for m in messages[:-1])
        available = max(500, MAX_CONTEXT_TOKENS - overhead - 200)
        user_message = _truncate_tokens(user_message, available)
        messages[-1]["content"] = user_message

    chunks: list[str] = []
    input_tokens = 0
    output_tokens = 0

    print("\n" + "=" * 60)
    print("AI Response (streaming):")
    print("=" * 60)

    async with client.chat.completions.stream(
        model=model,
        messages=messages,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
    ) as stream:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                print(delta, end="", flush=True)
                chunks.append(delta)

        final = await stream.get_final_completion()
        if final.usage:
            input_tokens = final.usage.prompt_tokens
            output_tokens = final.usage.completion_tokens

    print("\n" + "=" * 60)

    answer = "".join(chunks)
    if not input_tokens:
        input_tokens = count_tokens(str(messages))
    if not output_tokens:
        output_tokens = count_tokens(answer)

    return answer, input_tokens, output_tokens


# ── Groundedness check (informational only) ──────────────────────────
#
# Score is logged for visibility but NEVER blocks generation.
# Users want a complete scope on their first request.

def quick_groundedness_check(answer: str, context: str) -> float:
    """Broad token-overlap score 0.0–1.0 (informational only)."""
    if not answer or not context:
        return 0.75

    STOP_WORDS = {
        "this", "that", "with", "from", "have", "will", "shall", "should",
        "work", "each", "also", "been", "were", "they", "their", "project",
        "scope", "trade", "drawing", "include", "provide", "furnish", "install",
    }
    answer_tokens = set(
        w.lower() for w in re.findall(r"\b\w{4,}\b", answer)
        if w.lower() not in STOP_WORDS
    )
    if not answer_tokens:
        return 0.75

    context_lower = context.lower()
    matched = sum(1 for tok in answer_tokens if tok in context_lower)
    return max(matched / len(answer_tokens), 0.40)


# ── Follow-up question generation ────────────────────────────────────

async def generate_follow_up_questions(
    client: AsyncOpenAI,
    answer: str,
    query: str,
    trade: str,
    document_type: str,
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """
    Generate {FOLLOW_UP_QUESTIONS_COUNT} contextual follow-up questions.
    Rendered as clickable pill chips in the UI (matching .suggested-q in scopegap-agent_2.html).
    Returns a list of question strings, or safe defaults on failure.
    """
    import json as _json, re as _re

    system = FOLLOW_UP_SYSTEM_PROMPT.format(count=FOLLOW_UP_QUESTIONS_COUNT)
    user_msg = (
        f"Trade: {trade}\n"
        f"Document type: {document_type}\n"
        f"Original query: {query}\n\n"
        f"Generated scope preview:\n{answer[:2000]}"
    )

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=400,
            temperature=0.4,
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if match:
            questions = _json.loads(match.group())
            if isinstance(questions, list) and questions:
                return [str(q).strip() for q in questions[:FOLLOW_UP_QUESTIONS_COUNT] if q]
    except Exception as exc:
        logger.warning("Follow-up question generation failed: %s", exc)

    # Safe defaults
    return [
        f"Are there any scope gaps or unassigned items in the {trade} scope?",
        f"Which drawings have the most {trade} scope items requiring coordination?",
        f"Can you generate a {trade} quantity takeoff with sizes and specifications?",
    ]


# ── Document generation ───────────────────────────────────────────────

def generate_exhibit_document(
    answer: str,
    project_name: str,
    trade: str,
    document_type: str,
    drawing_summary: list[dict],
) -> str:
    """Generate a styled Word exhibit and return its file path."""
    gen = ExhibitDocumentGenerator()
    meta = gen.generate_sync(
        content=answer,
        project_name=project_name,
        trade=trade,
        document_type=document_type,
        drawing_summary=drawing_summary,
    )
    return meta.file_path


# ── Main test pipeline ────────────────────────────────────────────────

async def run_test_pipeline(
    loader: ExcelDataLoader,
    query: str,
    session: InMemorySession,
    client: AsyncOpenAI,
    stream: bool = False,
    generate_doc: bool = True,
) -> dict:
    """
    Full pipeline: intent → context → LLM → groundedness check → docgen.
    Returns a result dict with answer, doc_path, timings, tokens.
    """
    t0 = time.perf_counter()

    # 1. Intent detection (<1 ms, keyword-only)
    available_trades = loader.get_scope_trades()
    intent = detect_intent(query, available_trades)
    trade = intent["trade"]
    doc_type = intent["document_type"]
    logger.info("Intent → trade='%s' doc_type='%s'", trade, doc_type)

    # 2. Build context from Excel
    context_block = loader.build_context_block(scope_trade=trade, user_query=query)
    drawing_summary = loader.get_drawing_summary(scope_trade=trade)
    project_name = loader.get_project_name()
    csi_list = ", ".join(loader.get_unique_csi_divisions()[:20])
    t_ctx = int((time.perf_counter() - t0) * 1000)

    ctx_tokens = count_tokens(context_block)
    logger.info("Context built: %d tokens, %d drawings", ctx_tokens, len(drawing_summary))

    # 3. Build prompts
    task_map = {
        "exhibit": f"Create a professional Exhibit — Scope of Work for {trade}.",
        "scope": f"Create a detailed Scope of Work for {trade}.",
        "report": f"Create a comprehensive technical report for {trade}.",
        "takeoff": f"Create a quantity takeoff table for {trade}.",
        "specification": f"Create a technical specification document for {trade}.",
        "extract": f"Extract and list all {trade} items from the drawing notes.",
    }
    task = task_map.get(doc_type, f"Generate a {doc_type} document for {trade}.")

    system_prompt = TRADE_SYSTEM_PROMPT.format(
        trade=trade,
        task=task,
        project_name=project_name,
        csi_list=csi_list or "N/A",
    )
    user_message = (
        f"### Drawing Notes Context\n{context_block}\n\n"
        f"### User Request\n{query}"
    )

    history = session.history_for_llm(last_n=6)

    # 4. LLM call
    if stream:
        answer, input_tokens, output_tokens = await call_llm_stream(
            client, system_prompt, user_message, history
        )
    else:
        answer, input_tokens, output_tokens = await call_llm(
            client, system_prompt, user_message, history
        )
    t_llm = int((time.perf_counter() - t0) * 1000)

    # 5. Token tracking
    session.total_input_tokens += input_tokens
    session.total_output_tokens += output_tokens
    answer_tokens = count_tokens(answer)
    logger.info(
        "LLM done: input=%d output=%d answer_tokens=%d",
        input_tokens, output_tokens, answer_tokens,
    )

    # 6. Groundedness check (informational only — never blocks)
    groundedness = quick_groundedness_check(answer, context_block)
    logger.info("Groundedness: %.2f (informational — generation always proceeds)", groundedness)

    # 7. Document generation + follow-up questions — run in parallel
    import asyncio as _asyncio

    async def _gen_doc():
        if not generate_doc:
            return None
        try:
            return generate_exhibit_document(
                answer=answer,
                project_name=project_name,
                trade=trade,
                document_type=doc_type,
                drawing_summary=drawing_summary,
            )
        except Exception as exc:
            logger.error("Document generation failed: %s", exc)
            return None

    async def _gen_follow_up():
        return await generate_follow_up_questions(
            client=client,
            answer=answer,
            query=query,
            trade=trade,
            document_type=doc_type,
        )

    doc_path_result, follow_up_questions = await _asyncio.gather(
        _gen_doc(), _gen_follow_up(), return_exceptions=True
    )
    doc_path: Optional[str] = doc_path_result if not isinstance(doc_path_result, BaseException) else None
    if isinstance(doc_path_result, BaseException):
        logger.error("Document generation error: %s", doc_path_result)
    if isinstance(follow_up_questions, BaseException):
        logger.warning("Follow-up generation error: %s", follow_up_questions)
        follow_up_questions = []
    if doc_path:
        logger.info("Document saved: %s", doc_path)

    t_total = int((time.perf_counter() - t0) * 1000)

    # 8. Update session history
    session.add("user", query)
    session.add("assistant", answer)

    return {
        "session_id": session.session_id,
        "trade": trade,
        "document_type": doc_type,
        "answer": answer,
        "doc_path": doc_path,
        "groundedness_score": round(groundedness, 3),
        "needs_clarification": False,
        "clarification_questions": [],
        "follow_up_questions": follow_up_questions,
        "token_usage": {
            "input": input_tokens,
            "output": output_tokens,
            "answer_tokens": answer_tokens,
            "total": input_tokens + output_tokens,
        },
        "timings_ms": {
            "context_build": t_ctx,
            "llm": t_llm - t_ctx,
            "total": t_total,
        },
    }


# ── CLI helpers ───────────────────────────────────────────────────────

def print_result(result: dict) -> None:
    print("\n" + "=" * 70)
    print(f"Trade: {result['trade']}  |  Doc Type: {result['document_type']}")
    print(
        f"Groundedness: {result['groundedness_score']:.0%}  |  "
        f"Needs Clarification: {result['needs_clarification']}"
    )
    print(
        f"Tokens — In: {result['token_usage']['input']:,}  "
        f"Out: {result['token_usage']['output']:,}  "
        f"Answer: {result['token_usage']['answer_tokens']:,}  "
        f"Total: {result['token_usage']['total']:,}"
    )
    print(
        f"Latency — Context: {result['timings_ms']['context_build']} ms  "
        f"LLM: {result['timings_ms']['llm']} ms  "
        f"Total: {result['timings_ms']['total']} ms"
    )
    if result.get("doc_path"):
        print(f"\nDocument saved: {result['doc_path']}")

    # Follow-up questions — displayed as pill chips (matching .suggested-q in HTML)
    follow_up = result.get("follow_up_questions", [])
    if follow_up:
        print("\n" + "─" * 70)
        print("  Suggested follow-up questions:")
        for i, q in enumerate(follow_up, 1):
            print(f"  [{i}] {q}")
        print("  (Type the question number or paste the full question to continue)")
        print("─" * 70)

    print("\n--- ANSWER PREVIEW (first 800 chars) ---")
    print(result["answer"][:800])
    print("=" * 70)


async def interactive_cli(
    loader: ExcelDataLoader,
    client: AsyncOpenAI,
    stream: bool = False,
) -> None:
    """Interactive conversation loop with follow-up question shortcuts."""
    session = InMemorySession()
    available_trades = loader.get_scope_trades()
    last_follow_up: list[str] = []   # track last follow-up questions for number shortcuts

    print("\n" + "=" * 70)
    print("  Construction Intelligence — Scope Generator (Test Mode)")
    print(f"  Project: {loader.get_project_name()}")
    print(f"  Available Trades: {', '.join(available_trades)}")
    print(f"  Session: {session.session_id}")
    print("  Commands: 'quit' | 'tokens' | 'clear' (new session)")
    print("=" * 70)
    print("\nSample queries:")
    print("  - Generate exhibit for electrical")
    print("  - Create scope of work for plumbing")
    print("  - Generate full report on HVAC")
    print("  - Extract structural takeoff quantities")
    print()

    while True:
        try:
            raw_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not raw_input:
            continue
        if raw_input.lower() == "quit":
            break
        if raw_input.lower() == "tokens":
            print(session.token_report())
            continue
        if raw_input.lower() == "clear":
            session = InMemorySession()
            last_follow_up = []
            print(f"New session: {session.session_id}")
            continue

        # Allow the user to type "1", "2", "3" to pick a follow-up question
        query = raw_input
        if raw_input in ("1", "2", "3", "4", "5") and last_follow_up:
            idx = int(raw_input) - 1
            if 0 <= idx < len(last_follow_up):
                query = last_follow_up[idx]
                print(f"  → {query}")

        result = await run_test_pipeline(
            loader=loader, query=query, session=session,
            client=client, stream=stream,
        )
        print_result(result)
        last_follow_up = result.get("follow_up_questions", [])

    print(f"\nFinal token summary: {session.token_report()}")


async def batch_run(loader: ExcelDataLoader, client: AsyncOpenAI) -> None:
    """Run test queries for all available scope trades."""
    trades = loader.get_scope_trades()
    test_queries = [
        ("Electrical", "Generate exhibit for electrical scope of work"),
        ("Plumbing", "Create scope of work for plumbing"),
        ("Mechanical", "Generate full report on mechanical/HVAC"),
        ("Structural", "Extract structural scope items from drawings"),
        ("Fire Protection", "Generate exhibit for fire protection"),
    ]

    results = []
    for trade, query in test_queries:
        if trade not in trades:
            logger.info("Trade '%s' not in Excel data — skipping", trade)
            continue
        session = InMemorySession()
        print(f"\n{'─'*60}")
        print(f"Running: {query}")
        result = await run_test_pipeline(
            loader=loader, query=query, session=session,
            client=client, stream=False,
        )
        print_result(result)
        results.append(result)

    print("\n" + "=" * 70)
    print("BATCH SUMMARY")
    print("=" * 70)
    for r in results:
        print(
            f"  {r['trade']:<25} "
            f"Groundedness: {r['groundedness_score']:.0%}  "
            f"Tokens(out): {r['token_usage']['output']:,}  "
            f"Doc: {'YES' if r.get('doc_path') else 'NO'}"
        )


# ── Entry point ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test scope/exhibit generation using Excel trade data"
    )
    parser.add_argument(
        "--excel", default=None,
        help="Path to Excel file (default: Scope Gap - Electrical.xlsx)",
    )
    parser.add_argument("--query", default=None, help="Single query (non-interactive)")
    parser.add_argument("--trade", default=None, help="Override trade detection")
    parser.add_argument("--stream", action="store_true", help="Enable streaming output")
    parser.add_argument("--batch", action="store_true", help="Run batch tests for all trades")
    parser.add_argument("--no-doc", action="store_true", help="Skip Word document generation")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"OpenAI model (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set. Add it to .env or environment.")
        sys.exit(1)

    # Load Excel data
    loader = ExcelDataLoader(args.excel)
    try:
        loader.load()
    except Exception as e:
        print(f"ERROR loading Excel: {e}")
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key)

    if args.batch:
        asyncio.run(batch_run(loader, client))
    elif args.query:
        session = InMemorySession()
        query = args.query
        if args.trade:
            query = f"{args.trade}: {query}"
        result = asyncio.run(
            run_test_pipeline(
                loader=loader, query=query, session=session,
                client=client, stream=args.stream,
                generate_doc=not args.no_doc,
            )
        )
        print_result(result)
        print(f"\nToken summary: {session.token_report()}")
    else:
        asyncio.run(interactive_cli(loader, client, stream=args.stream))


if __name__ == "__main__":
    main()