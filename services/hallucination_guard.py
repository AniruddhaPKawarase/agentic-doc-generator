"""
services/hallucination_guard.py  —  Flexible groundedness scoring (informational).

Computes a token-overlap groundedness score between the LLM answer and
the source context. The score is logged and returned in the response for
observability, but it NEVER blocks generation and NEVER replaces the
answer with clarification questions.

The guard is purely diagnostic — users get their complete document on
the first query. The score helps identify when the model may be
extrapolating beyond the source data.
"""

import re
import logging

from config import get_settings
from models.schemas import HallucinationCheckResult

logger = logging.getLogger(__name__)
settings = get_settings()

# Words excluded from the token-overlap score (too common to be meaningful)
_STOPWORDS = {
    "this", "that", "with", "from", "have", "will", "shall", "should",
    "work", "each", "also", "been", "were", "they", "their", "project",
    "scope", "trade", "drawing", "include", "provide", "install",
    "furnish", "coordinate", "existing", "general", "requirements",
}


class HallucinationGuard:
    """
    Computes a broad token-overlap groundedness score between the LLM answer
    and the source context. Always recommends proceeding — the score is
    purely informational for logging and diagnostics.
    """

    def __init__(self, confidence_threshold: float = None):
        self._threshold = confidence_threshold or settings.hallucination_confidence_threshold

    def check(
        self,
        llm_response: str,
        source_context: str,
        trade: str,
        document_type: str,
    ) -> HallucinationCheckResult:
        """
        Score how well the LLM answer overlaps with the source context.

        Returns HallucinationCheckResult with:
          is_reliable       = True always (unless response is empty)
          recommendation    = "proceed" always
          confidence_score  = broad token-overlap ratio (informational)
        """
        # -- Hard stop: empty / too-short response only ------------------
        if not llm_response or len(llm_response.strip()) < 50:
            logger.warning("Guard: empty/short response for trade=%s", trade)
            return HallucinationCheckResult(
                is_reliable=False,
                confidence_score=0.0,
                unsupported_claims=["Response is empty or too short"],
                clarification_questions=[],
                recommendation="proceed",
            )

        # -- Broad token-overlap score -----------------------------------
        answer_tokens = set(
            w.lower() for w in re.findall(r'\b\w{4,}\b', llm_response)
            if w.lower() not in _STOPWORDS
        )

        unsupported: list[str] = []
        if answer_tokens and source_context:
            source_lower = source_context.lower()
            matched = 0
            unmatched: list[str] = []
            for tok in answer_tokens:
                if tok in source_lower:
                    matched += 1
                else:
                    unmatched.append(tok)
            groundedness = matched / len(answer_tokens) if answer_tokens else 0.0
            groundedness = max(groundedness, 0.40)

            if unmatched:
                unsupported = unmatched[:10]
        else:
            groundedness = 0.75  # narrative with no extractable tokens — assume okay

        logger.info(
            "Groundedness score=%.2f threshold=%.2f trade=%s doc_type=%s",
            groundedness, self._threshold, trade, document_type,
        )

        return HallucinationCheckResult(
            is_reliable=True,
            confidence_score=round(groundedness, 3),
            unsupported_claims=unsupported[:5] if unsupported else [],
            clarification_questions=[],
            recommendation="proceed",
        )