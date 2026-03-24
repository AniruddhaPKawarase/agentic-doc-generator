"""
Token counting and cost estimation utilities.
"""

import logging

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
    TIKTOKEN_AVAILABLE = True
except Exception:
    _ENC = None
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available; falling back to character-based estimates")

INPUT_COST_PER_TOKEN = settings.openai_input_cost_per_million / 1_000_000
OUTPUT_COST_PER_TOKEN = settings.openai_output_cost_per_million / 1_000_000


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if TIKTOKEN_AVAILABLE and _ENC:
        return len(_ENC.encode(text))
    return max(1, len(text) // 4)


def count_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        total += count_tokens(str(msg.get("content", "")))
        total += 4
    return total + 2


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_COST_PER_TOKEN) + (output_tokens * OUTPUT_COST_PER_TOKEN)


def truncate_to_token_budget(text: str, max_tokens: int) -> tuple[str, int]:
    # Encode ONCE — previously called count_tokens twice on the same large text
    # (once to check, once to return the count), plus a third encode inside.
    if TIKTOKEN_AVAILABLE and _ENC:
        tokens = _ENC.encode(text)
        if len(tokens) <= max_tokens:
            return text, len(tokens)
        trimmed = tokens[:max_tokens]
        return _ENC.decode(trimmed), len(trimmed)

    # Char-based fallback — avoid a redundant second pass through count_tokens.
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text, max(1, len(text) // 4)
    trimmed_text = text[:max_chars]
    return trimmed_text, max(1, len(trimmed_text) // 4)
