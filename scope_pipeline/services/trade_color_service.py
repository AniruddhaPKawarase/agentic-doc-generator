"""
Trade color service providing deterministic colors for construction trades.

Provides 23 base palette colors from scopegap-agent-v3.html.
Unknown trades receive a deterministic hash-based HSL color.
"""

from __future__ import annotations

import colorsys
import hashlib


_BASE_PALETTE: dict[str, str] = {
    "electrical": "#F48FB1",
    "hvac": "#90A4AE",
    "plumbing": "#81D4FA",
    "fire alarm": "#FFE082",
    "fire sprinkler": "#FFAB91",
    "lighting": "#FFF59D",
    "low voltage": "#CE93D8",
    "controls": "#80CBC4",
    "concrete": "#BCAAA4",
    "structural steel": "#B0BEC5",
    "framing & drywall": "#C5E1A5",
    "doors & hardware": "#EF9A9A",
    "glass & glazing": "#80DEEA",
    "roofing": "#A5D6A7",
    "elevators": "#B39DDB",
    "painting": "#F8BBD0",
    "flooring": "#DCEDC8",
    "casework": "#D7CCC8",
    "earthwork": "#FFE0B2",
    "abatement": "#FFCCBC",
    "acoustical ceilings": "#E1BEE7",
    "data & telecom": "#B2EBF2",
    "general conditions": "#CFD8DC",
}


def _hex_to_rgb(hex_color: str) -> list[int]:
    """Convert '#RRGGBB' to [R, G, B] integers."""
    h = hex_color.lstrip("#")
    return [int(h[i : i + 2], 16) for i in (0, 2, 4)]


def _hsl_to_hex(h_deg: float, s_pct: float, l_pct: float) -> str:
    """
    Convert HSL (h in [0,360), s/l in [0,100]) to '#RRGGBB'.
    Uses colorsys which expects fractions in [0, 1].
    """
    r_f, g_f, b_f = colorsys.hls_to_rgb(h_deg / 360.0, l_pct / 100.0, s_pct / 100.0)
    r, g, b = round(r_f * 255), round(g_f * 255), round(b_f * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _generate_color(trade: str) -> str:
    """
    Derive a deterministic hex color for an unknown trade.

    Algorithm: md5(trade.lower()) → first 2 bytes as uint16 → hue in [0,360),
    saturation fixed at 70%, lightness fixed at 65%.
    """
    digest = hashlib.md5(trade.lower().encode()).digest()
    hue = (int.from_bytes(digest[:2], "big") / 65536.0) * 360.0
    return _hsl_to_hex(hue, 70.0, 65.0)


class TradeColorService:
    """
    Provides display colors for construction trades.

    Look up order:
    1. Case-insensitive match against the 23-color base palette.
    2. Deterministic hash-based HSL color for anything else.
    """

    def get_color(self, trade: str) -> dict:
        """
        Return color info for a single trade.

        Returns:
            {"hex": "#RRGGBB", "rgb": [R, G, B]}
        """
        hex_color = _BASE_PALETTE.get(trade.lower()) or _generate_color(trade)
        return {"hex": hex_color, "rgb": _hex_to_rgb(hex_color)}

    def get_all_colors(self, trades: list[str]) -> dict[str, dict]:
        """
        Return a color map for every trade in the list.

        Returns:
            {trade_name: {"hex": "#RRGGBB", "rgb": [R, G, B]}, ...}
        """
        return {trade: self.get_color(trade) for trade in trades}
