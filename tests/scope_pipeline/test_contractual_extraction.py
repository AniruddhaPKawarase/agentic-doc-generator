"""tests/scope_pipeline/test_contractual_extraction.py

Tests for contractual language requirements in the ExtractionAgent SYSTEM_PROMPT
and drawing_refs parsing in _parse_response.
"""

import json
import pytest


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT content tests
# ---------------------------------------------------------------------------

def test_system_prompt_contains_contractor_shall():
    """Every scope item must begin with 'Contractor shall'."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "Contractor shall" in SYSTEM_PROMPT


def test_system_prompt_contains_furnish_and_install():
    """Prompt must list 'furnish and install' as a standard AIA/CSI phrase."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "furnish and install" in SYSTEM_PROMPT


def test_system_prompt_contains_division_reference():
    """Prompt must document the 'per Division [number] — [name]' phrase."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "per Division" in SYSTEM_PROMPT


def test_system_prompt_contains_verify_in_field():
    """Prompt must list 'verify in field' as a standard AIA/CSI phrase."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "verify in field" in SYSTEM_PROMPT


def test_system_prompt_contains_drawing_refs():
    """Prompt must require drawing_refs field in every extracted item."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "drawing_refs" in SYSTEM_PROMPT


def test_system_prompt_retains_trade_placeholder():
    """Original {trade} format placeholder must still be present."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "{trade}" in SYSTEM_PROMPT


def test_system_prompt_retains_drawing_list_placeholder():
    """Original {drawing_list} format placeholder must still be present."""
    from scope_pipeline.agents.extraction_agent import SYSTEM_PROMPT

    assert "{drawing_list}" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _parse_response drawing_refs tests
# ---------------------------------------------------------------------------

def test_parse_response_with_drawing_refs():
    """drawing_refs provided by LLM are stored on the ScopeItem."""
    from scope_pipeline.agents.extraction_agent import ExtractionAgent

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1-mini")

    raw = json.dumps([
        {
            "text": "Contractor shall furnish and install 200A panel board",
            "drawing_name": "E-103",
            "page": 3,
            "source_snippet": "200A panel board, 42-circuit, surface mounted",
            "confidence": 0.95,
            "csi_hint": "26 24 16",
            "drawing_refs": ["E-103", "E-001"],
        }
    ])

    items = agent._parse_response(raw)

    assert len(items) == 1
    assert items[0].drawing_refs == ["E-103", "E-001"]


def test_parse_response_drawing_refs_defaults_to_drawing_name():
    """When drawing_refs is absent, it defaults to [drawing_name]."""
    from scope_pipeline.agents.extraction_agent import ExtractionAgent

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1-mini")

    raw = json.dumps([
        {
            "text": "Contractor shall provide conduit sleeves",
            "drawing_name": "E-201",
            "page": 5,
            "source_snippet": "provide conduit sleeves at all penetrations",
            "confidence": 0.80,
        }
    ])

    items = agent._parse_response(raw)

    assert len(items) == 1
    assert items[0].drawing_refs == ["E-201"]


def test_parse_response_preserves_existing_fields():
    """Existing fields (text, drawing_name, page, etc.) are unaffected by drawing_refs change."""
    from scope_pipeline.agents.extraction_agent import ExtractionAgent

    agent = ExtractionAgent(api_key="test-key", model="gpt-4.1-mini")

    raw = json.dumps([
        {
            "text": "Contractor shall coordinate with mechanical contractor",
            "drawing_name": "E-104",
            "drawing_title": "Power Plan Level 2",
            "page": 4,
            "source_snippet": "coordinate with mechanical contractor for VRF connections",
            "confidence": 0.88,
            "csi_hint": "26 05 19",
            "drawing_refs": ["E-104", "M-201"],
        }
    ])

    items = agent._parse_response(raw)

    assert len(items) == 1
    item = items[0]
    assert item.text == "Contractor shall coordinate with mechanical contractor"
    assert item.drawing_name == "E-104"
    assert item.drawing_title == "Power Plan Level 2"
    assert item.page == 4
    assert item.source_snippet == "coordinate with mechanical contractor for VRF connections"
    assert item.confidence == 0.88
    assert item.csi_hint == "26 05 19"
    assert item.drawing_refs == ["E-104", "M-201"]
