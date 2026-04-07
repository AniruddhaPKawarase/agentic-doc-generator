"""
Score card rendering for the report view.
"""
import streamlit as st

from utils.session import score_bar_html


def render_score_cards(result: dict):
    """Render the four score cards at the top of the report view."""
    completeness_data = result.get("completeness", {})
    quality_data = result.get("quality", {})
    stats_data = result.get("pipeline_stats", {})

    completeness_pct = completeness_data.get("overall_pct", 0) if isinstance(completeness_data, dict) else 0
    quality_score = quality_data.get("accuracy_score", 0) if isinstance(quality_data, dict) else 0
    drawing_cov = completeness_data.get("drawing_coverage_pct", 0) if isinstance(completeness_data, dict) else 0
    attempts_count = stats_data.get("attempts", 1) if isinstance(stats_data, dict) else 1
    items_count = len(result.get("items", []))

    s1, s2, s3, s4 = st.columns(4)

    def _score_card(col, label, value, color):
        pct = value * 100 if value <= 1 else value
        with col:
            st.markdown(
                f'<div class="score-card">'
                f'<div class="score-label">{label}</div>'
                f'<div class="score-value">{pct:.0f}%</div>'
                f'{score_bar_html(value if value <= 1 else value / 100, color)}'
                f"</div>",
                unsafe_allow_html=True,
            )

    _score_card(s1, "Completeness", completeness_pct, "#22C55E")
    _score_card(s2, "Quality", quality_score, "#3B82F6")
    _score_card(s3, "Drawing Coverage", drawing_cov, "#8B5CF6")
    with s4:
        st.markdown(
            f'<div class="score-card">'
            f'<div class="score-label">Items / Attempts</div>'
            f'<div class="score-value">{items_count} / {attempts_count}</div>'
            f'<div class="score-sub">Scope items extracted</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
