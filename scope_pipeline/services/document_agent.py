"""
scope_pipeline/services/document_agent.py — Agent 7: Document generation (NO LLM).

Input: Validated pipeline results (items, ambiguities, gotchas, completeness, quality, stats).
Output: DocumentSet with file paths to Word, PDF, CSV, JSON files.

All 4 formats are generated in parallel via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from scope_pipeline.models import (
    AmbiguityItem,
    ClassifiedItem,
    CompletenessReport,
    DocumentSet,
    GotchaItem,
    PipelineStats,
    QualityReport,
)

logger = logging.getLogger(__name__)

# PDF caps to keep file size manageable
_PDF_MAX_ITEMS = 100

# Brand colours (RGB tuples)
_DARK_BLUE = (0, 51, 102)
_LIGHT_GRAY = (245, 245, 245)


class DocumentAgent:
    """Generate Word, PDF, CSV, JSON output files from validated pipeline results."""

    def __init__(self, docs_dir: str = "./generated_docs") -> None:
        self._docs_dir = docs_dir
        os.makedirs(self._docs_dir, exist_ok=True)

    async def generate_all(
        self,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> DocumentSet:
        """Generate all 4 document formats in parallel. Returns DocumentSet."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"{project_id}_{trade}_{timestamp}"

        common_kwargs: dict[str, Any] = dict(
            items=items,
            ambiguities=ambiguities,
            gotchas=gotchas,
            completeness=completeness,
            quality=quality,
            project_id=project_id,
            project_name=project_name,
            trade=trade,
            stats=stats,
        )

        word_path = os.path.join(self._docs_dir, f"{base}.docx")
        pdf_path = os.path.join(self._docs_dir, f"{base}.pdf")
        csv_path = os.path.join(self._docs_dir, f"{base}.csv")
        json_path = os.path.join(self._docs_dir, f"{base}.json")

        word_task = asyncio.to_thread(self.generate_word_sync, word_path, **common_kwargs)
        pdf_task = asyncio.to_thread(self.generate_pdf_sync, pdf_path, **common_kwargs)
        csv_task = asyncio.to_thread(self.generate_csv_sync, csv_path, **common_kwargs)
        json_task = asyncio.to_thread(self.generate_json_sync, json_path, **common_kwargs)

        results = await asyncio.gather(word_task, pdf_task, csv_task, json_task, return_exceptions=True)

        doc_set = DocumentSet()
        paths = [word_path, pdf_path, csv_path, json_path]
        attrs = ["word_path", "pdf_path", "csv_path", "json_path"]
        for idx, (result, path, attr) in enumerate(zip(results, paths, attrs)):
            if isinstance(result, Exception):
                logger.error("Document generation failed for %s: %s", attr, result)
            else:
                setattr(doc_set, attr, path)

        return doc_set

    # ------------------------------------------------------------------
    # Word (.docx)
    # ------------------------------------------------------------------

    def generate_word_sync(
        self,
        path: str,
        *,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()
        style = doc.styles["Normal"]
        style.font.size = Pt(10)
        style.font.name = "Calibri"

        # --- Title ---
        title = doc.add_heading("SCOPE GAP REPORT", level=0)
        for run in title.runs:
            run.font.color.rgb = RGBColor(*_DARK_BLUE)

        # --- Project Info ---
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        info_lines = [
            f"Project: {project_name} (ID: {project_id})",
            f"Trade: {trade}",
            f"Generated: {now}",
            f"Completeness: {completeness.overall_pct:.1f}%",
        ]
        for line in info_lines:
            doc.add_paragraph(line)

        # --- Executive Summary ---
        doc.add_heading("Executive Summary", level=1)
        doc.add_paragraph(
            f"This report contains {len(items)} scope items, "
            f"{len(ambiguities)} ambiguities, and {len(gotchas)} gotchas."
        )

        # --- Scope Inclusions ---
        doc.add_heading("Scope Inclusions", level=1)
        grouped: dict[str, list[ClassifiedItem]] = {}
        for item in items:
            grouped.setdefault(item.drawing_name, []).append(item)

        for drawing_name, drawing_items in grouped.items():
            doc.add_heading(drawing_name, level=2)
            for item in drawing_items:
                p = doc.add_paragraph()
                run_text = p.add_run(f"{item.text}")
                run_text.bold = True
                p.add_run(
                    f"\n  CSI: {item.csi_code} | Confidence: {item.confidence:.0%}"
                    f" | Source: \"{item.source_snippet}\""
                )

        # --- Ambiguities ---
        if ambiguities:
            doc.add_heading("Ambiguities", level=1)
            for amb in ambiguities:
                p = doc.add_paragraph()
                run_text = p.add_run(amb.scope_text)
                run_text.bold = True
                p.add_run(
                    f"\n  Competing trades: {', '.join(amb.competing_trades)}"
                    f" | Severity: {amb.severity}"
                    f"\n  Recommendation: {amb.recommendation}"
                )

        # --- Gotchas ---
        if gotchas:
            doc.add_heading("Gotchas", level=1)
            for gtc in gotchas:
                p = doc.add_paragraph()
                run_text = p.add_run(f"[{gtc.severity.upper()}] {gtc.description}")
                run_text.bold = True
                p.add_run(
                    f"\n  Risk type: {gtc.risk_type}"
                    f" | Affected trades: {', '.join(gtc.affected_trades)}"
                    f"\n  Recommendation: {gtc.recommendation}"
                )

        # --- Completeness ---
        doc.add_heading("Completeness Report", level=1)
        doc.add_paragraph(f"Drawing coverage: {completeness.drawing_coverage_pct:.1f}%")
        doc.add_paragraph(f"CSI coverage: {completeness.csi_coverage_pct:.1f}%")
        doc.add_paragraph(f"Overall: {completeness.overall_pct:.1f}%")
        if completeness.missing_drawings:
            doc.add_paragraph(f"Missing drawings: {', '.join(completeness.missing_drawings)}")
        if completeness.missing_csi_codes:
            doc.add_paragraph(f"Missing CSI codes: {', '.join(completeness.missing_csi_codes)}")

        # --- Footer ---
        doc.add_paragraph("")
        footer = doc.add_paragraph("Generated by iFieldSmart ScopeAI Pipeline v1.0")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in footer.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(128, 128, 128)

        doc.save(path)
        logger.info("Word document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def generate_pdf_sync(
        self,
        path: str,
        *,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        doc = SimpleDocTemplate(path, pagesize=letter)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ScopeTitle",
            parent=styles["Title"],
            textColor=HexColor("#003366"),
            fontSize=20,
        )
        heading_style = ParagraphStyle(
            "ScopeHeading",
            parent=styles["Heading2"],
            textColor=HexColor("#003366"),
        )

        story: list[Any] = []

        # Title
        story.append(Paragraph("SCOPE GAP REPORT", title_style))
        story.append(Spacer(1, 12))

        # Summary
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary_text = (
            f"Project: {project_name} (ID: {project_id})<br/>"
            f"Trade: {trade}<br/>"
            f"Generated: {now}<br/>"
            f"Items: {len(items)} | Ambiguities: {len(ambiguities)} | Gotchas: {len(gotchas)}<br/>"
            f"Completeness: {completeness.overall_pct:.1f}%"
        )
        story.append(Paragraph(summary_text, styles["Normal"]))
        story.append(Spacer(1, 18))

        # Scope Items (capped)
        story.append(Paragraph("Scope Items", heading_style))
        story.append(Spacer(1, 6))
        for item in items[:_PDF_MAX_ITEMS]:
            item_text = (
                f"<b>{item.text}</b><br/>"
                f"Drawing: {item.drawing_name} | CSI: {item.csi_code} | "
                f"Confidence: {item.confidence:.0%}"
            )
            story.append(Paragraph(item_text, styles["Normal"]))
            story.append(Spacer(1, 4))

        if len(items) > _PDF_MAX_ITEMS:
            story.append(Paragraph(
                f"<i>... and {len(items) - _PDF_MAX_ITEMS} more items (see Word/CSV)</i>",
                styles["Normal"],
            ))

        # Footer
        story.append(Spacer(1, 24))
        story.append(Paragraph(
            "Generated by iFieldSmart ScopeAI Pipeline v1.0",
            ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=HexColor("#808080")),
        ))

        doc.build(story)
        logger.info("PDF document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def generate_csv_sync(
        self,
        path: str,
        *,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        header = [
            "Trade",
            "CSI Code",
            "CSI Division",
            "Scope Item",
            "Drawing",
            "Drawing Title",
            "Page",
            "Source Snippet",
            "Confidence",
            "Classification Reason",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for item in items:
                writer.writerow([
                    item.trade,
                    item.csi_code,
                    item.csi_division,
                    item.text,
                    item.drawing_name,
                    item.drawing_title or "",
                    item.page,
                    item.source_snippet,
                    f"{item.confidence:.2f}",
                    item.classification_reason,
                ])

        logger.info("CSV document saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def generate_json_sync(
        self,
        path: str,
        *,
        items: list[ClassifiedItem],
        ambiguities: list[AmbiguityItem],
        gotchas: list[GotchaItem],
        completeness: CompletenessReport,
        quality: QualityReport,
        project_id: int,
        project_name: str,
        trade: str,
        stats: PipelineStats,
    ) -> str:
        output = {
            "project_id": project_id,
            "project_name": project_name,
            "trade": trade,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [item.model_dump() for item in items],
            "ambiguities": [amb.model_dump() for amb in ambiguities],
            "gotchas": [gtc.model_dump() for gtc in gotchas],
            "completeness": completeness.model_dump(),
            "quality": quality.model_dump(),
            "pipeline_stats": stats.model_dump(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info("JSON document saved: %s", path)
        return path
