"""Tests for TradeColorService."""

from __future__ import annotations

import re

import pytest

from scope_pipeline.services.trade_color_service import TradeColorService


HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


@pytest.fixture
def service() -> TradeColorService:
    return TradeColorService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_color(color: dict) -> bool:
    """Return True when the color dict has a valid hex and rgb triple."""
    return (
        isinstance(color, dict)
        and "hex" in color
        and "rgb" in color
        and bool(HEX_PATTERN.match(color["hex"]))
        and isinstance(color["rgb"], list)
        and len(color["rgb"]) == 3
        and all(isinstance(v, int) and 0 <= v <= 255 for v in color["rgb"])
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_known_trade_returns_base_color(service: TradeColorService) -> None:
    """Electrical should return the exact base-palette hex #F48FB1."""
    color = service.get_color("Electrical")
    assert color["hex"] == "#F48FB1"
    assert color["rgb"] == [244, 143, 177]


def test_unknown_trade_returns_generated_color(service: TradeColorService) -> None:
    """An unknown trade must still return a valid color dict."""
    color = service.get_color("Exotic Trade XYZ")
    assert _is_valid_color(color), f"Invalid color dict: {color}"


def test_generated_color_is_deterministic(service: TradeColorService) -> None:
    """Calling get_color twice for the same unknown trade returns identical results."""
    trade = "Mystery Trade 42"
    assert service.get_color(trade) == service.get_color(trade)


def test_get_all_colors(service: TradeColorService) -> None:
    """get_all_colors returns one entry per trade with valid color dicts."""
    trades = ["Electrical", "HVAC", "Plumbing", "Unknown Trade A"]
    result = service.get_all_colors(trades)

    assert set(result.keys()) == set(trades)
    for trade, color in result.items():
        assert _is_valid_color(color), f"Invalid color for '{trade}': {color}"


def test_case_insensitive_lookup(service: TradeColorService) -> None:
    """Lookup must be case-insensitive; all variants resolve to the same color."""
    variants = ["electrical", "Electrical", "ELECTRICAL", "ElEcTrIcAl"]
    colors = [service.get_color(v) for v in variants]
    assert all(c == colors[0] for c in colors), "Case variants returned different colors"


def test_base_palette_rgb_consistency(service: TradeColorService) -> None:
    """RGB values must correctly decode from the stored hex for every base trade."""
    base_trades = [
        "Electrical", "HVAC", "Plumbing", "Fire Alarm", "Fire Sprinkler",
        "Lighting", "Low Voltage", "Controls", "Concrete", "Structural Steel",
        "Framing & Drywall", "Doors & Hardware", "Glass & Glazing", "Roofing",
        "Elevators", "Painting", "Flooring", "Casework", "Earthwork",
        "Abatement", "Acoustical Ceilings", "Data & Telecom", "General Conditions",
    ]
    for trade in base_trades:
        color = service.get_color(trade)
        hex_val = color["hex"].lstrip("#")
        expected_rgb = [int(hex_val[i : i + 2], 16) for i in (0, 2, 4)]
        assert color["rgb"] == expected_rgb, (
            f"RGB mismatch for '{trade}': {color['rgb']} != {expected_rgb}"
        )


def test_all_known_base_trades_present(service: TradeColorService) -> None:
    """All 23 base-palette trades must return the documented hex value."""
    expected = {
        "Electrical": "#F48FB1", "HVAC": "#90A4AE", "Plumbing": "#81D4FA",
        "Fire Alarm": "#FFE082", "Fire Sprinkler": "#FFAB91", "Lighting": "#FFF59D",
        "Low Voltage": "#CE93D8", "Controls": "#80CBC4", "Concrete": "#BCAAA4",
        "Structural Steel": "#B0BEC5", "Framing & Drywall": "#C5E1A5",
        "Doors & Hardware": "#EF9A9A", "Glass & Glazing": "#80DEEA",
        "Roofing": "#A5D6A7", "Elevators": "#B39DDB", "Painting": "#F8BBD0",
        "Flooring": "#DCEDC8", "Casework": "#D7CCC8", "Earthwork": "#FFE0B2",
        "Abatement": "#FFCCBC", "Acoustical Ceilings": "#E1BEE7",
        "Data & Telecom": "#B2EBF2", "General Conditions": "#CFD8DC",
    }
    for trade, expected_hex in expected.items():
        actual_hex = service.get_color(trade)["hex"]
        assert actual_hex == expected_hex, (
            f"'{trade}': expected {expected_hex}, got {actual_hex}"
        )
