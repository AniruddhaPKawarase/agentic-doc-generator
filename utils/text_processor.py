"""
Text cleaning, deduplication, grouping, and relevance scoring utilities.
"""

import hashlib
import re
from collections import defaultdict
from typing import Any

_DIMENSION_RE = re.compile(
    r"""
    \d+\s*[xX]\s*\d+
    | \d+(?:\.\d+)?\s*(?:in|ft|"|')
    | \d+\s*/\s*\d+\s*"
    | \d+'\s*-\s*\d+"
    | #\d+(?:\s*@\s*\d+")?
    | R-?\d+
    | \d+\s*PSI
    | \d+\s*(?:CFM|BTU|SEER|AWG|AMP|VA|V|KV)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_MATERIAL_MARKERS = [
    "CONCRETE",
    "GWB",
    "PLYWOOD",
    "FRAMING",
    "INSULATION",
    "WATERPROOF",
    "DRYWALL",
    "STEEL",
    "COPPER",
    "PVC",
    "CAST IRON",
    "MEMBRANE",
    "FOOTING",
    "FOUNDATION",
    "SHEATHING",
    "PIPE",
    "DUCT",
    "PANEL",
    "VALVE",
]

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "all",
    "full",
    "report",
    "generate",
    "create",
    "extract",
}


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def text_fingerprint(text: str) -> str:
    return hashlib.md5(normalize_text(text).lower().encode()).hexdigest()


def deduplicate_texts(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for text in texts:
        cleaned = normalize_text(text)
        if not cleaned:
            continue
        fp = text_fingerprint(cleaned)
        if fp in seen:
            continue
        seen.add(fp)
        result.append(cleaned)
    return result


def is_high_value_text(text: str) -> bool:
    if _DIMENSION_RE.search(text):
        return True
    upper = text.upper()
    return any(marker in upper for marker in _MATERIAL_MARKERS)


def group_drawing_records(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for rec in records:
        drawing_name = rec.get("drawingName", "") or rec.get("drawing_name", "")
        drawing_title = rec.get("drawingTitle", "") or rec.get("drawing_title", "")
        key = " - ".join([part for part in [drawing_name, drawing_title] if part]).strip()
        if not key:
            key = "General"
        text = normalize_text(str(rec.get("text", "")))
        if text:
            groups[key].append(text)
    return {k: deduplicate_texts(v) for k, v in groups.items()}


def extract_trade_from_texts(texts: list[str], target_trade: str) -> list[str]:
    target_upper = target_trade.upper()
    trade_keywords = _get_trade_keywords(target_trade)
    filtered: list[str] = []
    for text in texts:
        upper = text.upper()
        if target_upper in upper or any(keyword in upper for keyword in trade_keywords):
            filtered.append(text)
    return filtered


def build_context_block(
    grouped: dict[str, list[str]],
    trade: str,
    csi_divisions: list[str],
    max_lines_per_section: int = 140,
) -> str:
    lines: list[str] = [
        f"## Project Drawing Data - Trade: {trade}",
        f"### CSI Divisions: {', '.join(csi_divisions) if csi_divisions else 'N/A'}",
        "",
    ]

    for section, texts in grouped.items():
        lines.append(f"#### Drawing Section: {section}")
        # Pre-compute is_high_value_text ONCE per text — previously each text
        # was evaluated twice (once for high_value list, once for low_value list).
        classified = [(is_high_value_text(t), t) for t in texts]
        high_value = [t for hv, t in classified if hv]
        low_value = [t for hv, t in classified if not hv]
        selected = high_value[:max_lines_per_section]
        remaining = max_lines_per_section - len(selected)
        if remaining > 0:
            selected.extend(low_value[:remaining])
        for text in selected:
            lines.append(f"- {text}")
        lines.append("")

    return "\n".join(lines)


def build_unique_text_context(
    trade: str,
    csi_divisions: list[str],
    ranked_texts: list[str],
) -> str:
    lines: list[str] = [
        f"## Project Text Context - Trade: {trade}",
        f"### CSI Divisions: {', '.join(csi_divisions) if csi_divisions else 'N/A'}",
        "### Filtered source lines",
    ]
    for idx, text in enumerate(ranked_texts, start=1):
        lines.append(f"{idx}. {normalize_text(text)}")
    return "\n".join(lines)


def extract_query_keywords(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]+", query.lower())
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if len(word) < 3 or word in _STOPWORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result


def rank_trade_texts(
    texts: list[str],
    trade: str,
    query: str,
    max_items: int,
) -> list[str]:
    trade_keywords = _get_trade_keywords(trade)
    query_keywords = extract_query_keywords(query)
    scored: list[tuple[int, str]] = []

    for text in deduplicate_texts(texts):
        upper = text.upper()
        score = 0
        if is_high_value_text(text):
            score += 8
        if trade.upper() in upper:
            score += 6
        score += sum(3 for keyword in trade_keywords if keyword in upper)
        score += sum(4 for keyword in query_keywords if keyword.upper() in upper)
        if len(text) > 180:
            score -= 1
        if score > 0:
            scored.append((score, text))

    if not scored:
        return deduplicate_texts(texts)[:max_items]

    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[:max_items]]


def _get_trade_keywords(trade: str) -> list[str]:
    keyword_map: dict[str, list[str]] = {
        "Plumbing": [
            "PIPE",
            "DRAIN",
            "WATER",
            "SEWER",
            "WSFU",
            "PLUMB",
            "LAVATORY",
            "TOILET",
            "SHOWER",
            "TUB",
            "VALVE",
            "SANITARY",
        ],
        "Electrical": [
            "ELECTRICAL",
            "OUTLET",
            "BREAKER",
            "PANEL",
            "AMP",
            "GFCI",
            "SWITCH",
            "CIRCUIT",
            "WIRING",
            "CONDUIT",
            "FIXTURE",
            "VOLT",
        ],
        "HVAC": [
            "HVAC",
            "DUCT",
            "AIR",
            "HEATING",
            "COOLING",
            "CFM",
            "BTU",
            "SEER",
            "COMPRESSOR",
            "VENT",
            "EXHAUST",
        ],
        "Structural": [
            "STRUCTURAL",
            "BEAM",
            "COLUMN",
            "STEEL",
            "FRAMING",
            "LOAD",
            "HEADER",
            "JOIST",
            "RAFTER",
            "SHEAR",
            "FOUNDATION",
        ],
    }

    canonical = trade.strip().upper()
    for key, values in keyword_map.items():
        if key.upper() == canonical:
            return values
    for key, values in keyword_map.items():
        if key.upper() in canonical or canonical in key.upper():
            return values
    return [canonical[:8]]
