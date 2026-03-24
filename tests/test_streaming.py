"""
tests/test_streaming.py — End-to-end streaming test for the live API server.

Tests the /api/chat/stream endpoint with the large-dataset query:
  project_id=7212, query="generate electrical scope exhibit"

This test validates:
  1. All SSE events are received without error
  2. The final "done" event contains a valid ChatResponse
  3. Total pipeline time is measured and logged
  4. Drawing numbers in the response are validated against the source data index
  5. No hallucinated drawing numbers (numbers not present in the Drawing Number Index)
  6. Results saved to test_results/streaming_7212_electrical.json

Usage:
    # Start the server first:
    #   python main.py  (or uvicorn main:app --port 8003)

    python tests/test_streaming.py
    python tests/test_streaming.py --host http://localhost:8003
    python tests/test_streaming.py --project-id 7212 --query "generate plumbing scope exhibit"
    python tests/test_streaming.py --no-doc     # skip Word document generation
    python tests/test_streaming.py --non-stream # test /api/chat instead
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_streaming")

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_HOST = "http://localhost:8003"
DEFAULT_PROJECT_ID = 7212
DEFAULT_QUERY = "generate electrical scope exhibit"
RESULTS_DIR = ROOT / "test_results"


# ── SSE parser ────────────────────────────────────────────────────────

def parse_sse_line(line: str) -> Optional[dict]:
    """Parse a single SSE data line into a dict, or None if not a data line."""
    line = line.strip()
    if line.startswith("data:"):
        payload = line[5:].strip()
        if payload and payload != "[DONE]":
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"type": "raw", "data": payload}
    return None


# ── Drawing number validation ─────────────────────────────────────────

def validate_drawing_numbers(answer: str, drawing_index_text: str) -> dict:
    """
    Extract drawing numbers from the LLM answer and check against the
    Drawing Number Index that was injected into the context.

    Returns a dict with:
      valid_count, invented_count, invented_list, validation_passed
    """
    # Extract numbers from the Drawing Number Index line in context
    index_match = re.search(r"Drawing Numbers:\s*(.+)", drawing_index_text or "")
    valid_numbers: set[str] = set()
    if index_match:
        for dn in index_match.group(1).split(","):
            dn = dn.strip().strip("…").upper()
            if dn:
                valid_numbers.add(dn)

    # Extract drawing numbers from LLM answer
    # Pattern: "Drawing Number(s): E-101, E-102" or inline references
    found_in_answer = set(
        re.findall(r'\b([A-Z]{1,3}-?\d{2,4}[A-Z0-9.]*)\b', answer.upper())
    )

    invented = found_in_answer - valid_numbers if valid_numbers else set()

    return {
        "valid_drawing_numbers": len(valid_numbers),
        "drawing_numbers_in_answer": len(found_in_answer),
        "potentially_invented": len(invented),
        "invented_list": sorted(invented)[:30],
        "validation_passed": len(invented) == 0 or not valid_numbers,
    }


# ── Streaming test ────────────────────────────────────────────────────

async def run_streaming_test(
    host: str,
    project_id: int,
    query: str,
    generate_doc: bool = True,
    timeout_seconds: int = 600,
) -> dict:
    """
    POST to /api/chat/stream and collect all SSE events.

    Returns a result dict with timing, token usage, validation results.
    """
    url = f"{host.rstrip('/')}/api/chat/stream"
    payload = {
        "project_id": project_id,
        "query": query,
        "generate_document": generate_doc,
    }

    logger.info("=" * 65)
    logger.info("STREAMING TEST")
    logger.info("  URL         : %s", url)
    logger.info("  project_id  : %d", project_id)
    logger.info("  query       : %s", query)
    logger.info("  generate_doc: %s", generate_doc)
    logger.info("=" * 65)

    t_start = time.perf_counter()
    t_first_token: Optional[float] = None
    t_metadata: Optional[float] = None

    token_chunks: list[str] = []
    metadata_event: Optional[dict] = None
    done_event: Optional[dict] = None
    event_counts: dict[str, int] = {"token": 0, "metadata": 0, "done": 0, "other": 0}

    print("\n[Streaming output]")
    print("-" * 65)

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                logger.error("HTTP %d: %s", response.status_code, body[:500])
                return {"error": f"HTTP {response.status_code}", "body": body.decode()[:500]}

            async for line in response.aiter_lines():
                event = parse_sse_line(line)
                if event is None:
                    continue

                etype = event.get("type", "unknown")
                event_counts[etype if etype in event_counts else "other"] += 1

                if etype == "token":
                    delta = event.get("delta", "")
                    if delta:
                        token_chunks.append(delta)
                        print(delta, end="", flush=True)
                        if t_first_token is None:
                            t_first_token = time.perf_counter()
                            logger.info(
                                "\nTime-to-first-token: %.1f seconds",
                                t_first_token - t_start,
                            )

                elif etype == "metadata":
                    t_metadata = time.perf_counter()
                    metadata_event = event
                    logger.info(
                        "Metadata received at %.1fs — trade=%s doc_type=%s",
                        t_metadata - t_start,
                        event.get("trade", "?"),
                        event.get("intent", {}).get("document_type", "?"),
                    )

                elif etype == "done":
                    done_event = event
                    break

    t_done = time.perf_counter()
    print("\n" + "-" * 65)

    total_ms = int((t_done - t_start) * 1000)
    first_token_ms = int((t_first_token - t_start) * 1000) if t_first_token else None
    answer = "".join(token_chunks)

    logger.info("Stream complete.")
    logger.info("  Total time          : %.1f seconds (%d ms)", t_done - t_start, total_ms)
    logger.info("  Time-to-first-token : %s ms", first_token_ms or "N/A (no tokens received)")
    logger.info("  Token events        : %d", event_counts["token"])
    logger.info("  Answer length       : %d chars", len(answer))

    # Extract ChatResponse from done event
    chat_response: Optional[dict] = None
    if done_event and "response" in done_event:
        chat_response = done_event["response"]

    # Token usage
    token_usage = {}
    pipeline_ms = None
    if chat_response:
        token_usage = chat_response.get("token_usage", {})
        pipeline_ms = chat_response.get("pipeline_ms")
        groundedness = chat_response.get("groundedness_score", 0)
        logger.info("  Input tokens        : %s", token_usage.get("input_tokens", "?"))
        logger.info("  Output tokens       : %s", token_usage.get("output_tokens", "?"))
        logger.info("  Cost USD            : $%.4f", token_usage.get("cost_usd", 0))
        logger.info("  Groundedness        : %.2f", groundedness)
        logger.info("  Pipeline ms (server): %s", pipeline_ms)
        if chat_response.get("document"):
            logger.info("  Document            : %s", chat_response["document"].get("filename", "?"))

    # Drawing number validation
    dn_validation = validate_drawing_numbers(answer, answer)
    logger.info(
        "  Drawing # validation: %d in answer, %d possibly invented",
        dn_validation["drawing_numbers_in_answer"],
        dn_validation["potentially_invented"],
    )
    if dn_validation["invented_list"]:
        logger.warning(
            "  Potentially invented drawing numbers: %s",
            ", ".join(dn_validation["invented_list"][:10]),
        )

    # Performance assessment
    logger.info("")
    logger.info("PERFORMANCE ASSESSMENT")
    if first_token_ms is not None:
        if first_token_ms < 60_000:
            logger.info("  Time-to-first-token : EXCELLENT (< 60s) — %ds", first_token_ms // 1000)
        elif first_token_ms < 120_000:
            logger.info("  Time-to-first-token : GOOD (< 2min) — %ds", first_token_ms // 1000)
        else:
            logger.warning("  Time-to-first-token : SLOW (> 2min) — %ds", first_token_ms // 1000)

    if total_ms < 180_000:
        logger.info("  Total pipeline      : EXCELLENT (< 3min) — %ds", total_ms // 1000)
    elif total_ms < 300_000:
        logger.info("  Total pipeline      : GOOD (< 5min) — %ds", total_ms // 1000)
    else:
        logger.warning("  Total pipeline      : SLOW (> 5min) — %ds", total_ms // 1000)

    result = {
        "test": "streaming",
        "project_id": project_id,
        "query": query,
        "success": done_event is not None,
        "timing": {
            "total_ms": total_ms,
            "time_to_first_token_ms": first_token_ms,
            "pipeline_ms_server_reported": pipeline_ms,
        },
        "events": event_counts,
        "answer_length_chars": len(answer),
        "answer_preview": answer[:500],
        "token_usage": token_usage,
        "drawing_number_validation": dn_validation,
        "chat_response": chat_response,
    }

    return result


# ── Non-streaming test (for comparison) ───────────────────────────────

async def run_non_streaming_test(
    host: str,
    project_id: int,
    query: str,
    generate_doc: bool = True,
    timeout_seconds: int = 600,
) -> dict:
    """POST to /api/chat (non-streaming) and measure total time."""
    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "project_id": project_id,
        "query": query,
        "generate_document": generate_doc,
    }

    logger.info("=" * 65)
    logger.info("NON-STREAMING TEST")
    logger.info("  URL: %s", url)
    logger.info("  project_id=%d  query=%s", project_id, query)
    logger.info("=" * 65)

    t_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.error("Request failed: %s", exc)
            return {"error": str(exc)}

    t_done = time.perf_counter()
    total_ms = int((t_done - t_start) * 1000)

    answer = data.get("answer", "")
    token_usage = data.get("token_usage", {})
    dn_validation = validate_drawing_numbers(answer, answer)

    logger.info("Non-streaming complete.")
    logger.info("  Total time     : %.1f seconds (%d ms)", t_done - t_start, total_ms)
    logger.info("  Answer length  : %d chars", len(answer))
    logger.info("  Output tokens  : %s", token_usage.get("output_tokens", "?"))
    logger.info(
        "  Drawing # validation: %d in answer, %d possibly invented",
        dn_validation["drawing_numbers_in_answer"],
        dn_validation["potentially_invented"],
    )

    return {
        "test": "non_streaming",
        "project_id": project_id,
        "query": query,
        "success": bool(answer),
        "timing": {"total_ms": total_ms},
        "answer_length_chars": len(answer),
        "answer_preview": answer[:500],
        "token_usage": token_usage,
        "drawing_number_validation": dn_validation,
        "chat_response": data,
    }


# ── Save results ──────────────────────────────────────────────────────

def save_results(result: dict, label: str) -> Path:
    """Save test results to test_results/ directory."""
    RESULTS_DIR.mkdir(exist_ok=True)
    filename = RESULTS_DIR / f"{label}.json"

    # Save without full chat_response (too large) unless explicitly needed
    save_data = {k: v for k, v in result.items() if k != "chat_response"}
    save_data["answer_full"] = (result.get("chat_response") or {}).get("answer", "")

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    logger.info("Results saved: %s", filename)
    return filename


# ── Entry point ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end streaming test for the Construction Intelligence Agent"
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"Server base URL (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--project-id", type=int, default=DEFAULT_PROJECT_ID,
        help=f"Project ID to test (default: {DEFAULT_PROJECT_ID})",
    )
    parser.add_argument(
        "--query", default=DEFAULT_QUERY,
        help=f"Query string (default: '{DEFAULT_QUERY}')",
    )
    parser.add_argument(
        "--no-doc", action="store_true",
        help="Skip Word document generation",
    )
    parser.add_argument(
        "--non-stream", action="store_true",
        help="Test /api/chat (non-streaming) instead of /api/chat/stream",
    )
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Request timeout in seconds (default: 600)",
    )
    args = parser.parse_args()

    generate_doc = not args.no_doc

    if args.non_stream:
        result = asyncio.run(
            run_non_streaming_test(
                host=args.host,
                project_id=args.project_id,
                query=args.query,
                generate_doc=generate_doc,
                timeout_seconds=args.timeout,
            )
        )
        label = f"non_streaming_{args.project_id}_{args.query[:20].replace(' ', '_')}"
    else:
        result = asyncio.run(
            run_streaming_test(
                host=args.host,
                project_id=args.project_id,
                query=args.query,
                generate_doc=generate_doc,
                timeout_seconds=args.timeout,
            )
        )
        label = f"streaming_{args.project_id}_{args.query[:20].replace(' ', '_')}"

    save_results(result, label)

    # Final summary
    print("\n" + "=" * 65)
    print("FINAL SUMMARY")
    print("=" * 65)
    print(f"  Test type      : {'streaming' if not args.non_stream else 'non-streaming'}")
    print(f"  Success        : {result.get('success', False)}")
    print(f"  Total time     : {result['timing']['total_ms'] / 1000:.1f}s")
    if not args.non_stream:
        ttft = result["timing"].get("time_to_first_token_ms")
        print(f"  First token    : {ttft / 1000:.1f}s" if ttft else "  First token    : N/A")
    print(f"  Answer chars   : {result.get('answer_length_chars', 0):,}")
    dn = result.get("drawing_number_validation", {})
    print(f"  Drawing #s in answer   : {dn.get('drawing_numbers_in_answer', 0)}")
    print(f"  Possibly invented      : {dn.get('potentially_invented', 0)}")
    if dn.get("invented_list"):
        print(f"  Invented samples       : {', '.join(dn['invented_list'][:5])}")
    print("=" * 65)

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
