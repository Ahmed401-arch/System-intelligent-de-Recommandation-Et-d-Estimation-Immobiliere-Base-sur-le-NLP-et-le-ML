"""
pdf_export.py — Feature 9: PDF Report Generator
Uses reportlab (already available).

PHASE 1 FIXES
─────────────
- Removed ALL emoji characters from PDF content. Helvetica/Courier have no
  emoji glyphs, so reportlab silently drops them and leaves stray artifacts
  (e.g. "n", "(cid:127)") in the rendered text. Replaced with plain-text
  labels / ASCII bullets so the PDF renders cleanly in every viewer.
- Removed the invalid "ROUNDEDCORNERS" TableStyle command (not a real
  reportlab TableStyle op — it was silently ignored, but is dead/incorrect
  code that could break on stricter reportlab versions).
- Fixed the duplicated "Économie" label (row label said "Économie" AND the
  cell value also started with "Économie : ...").
- Wrapped the whole generation in try/except with a logger so failures are
  diagnosable instead of producing a corrupt/empty download.
- Added defensive .get() access everywhere (no more apt['savings'] direct
  indexing) so a missing key can never raise a KeyError mid-build.
"""
import io
import logging
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)

PRIMARY  = colors.HexColor("#4f46e5")
ACCENT   = colors.HexColor("#06b6d4")
SUCCESS  = colors.HexColor("#10b981")
WARNING  = colors.HexColor("#f59e0b")
DANGER   = colors.HexColor("#ef4444")
DARK     = colors.HexColor("#1e293b")
LIGHT_BG = colors.HexColor("#f8fafc")
BORDER   = colors.HexColor("#e2e8f0")

# Plain-text ranking labels — no emoji, renders correctly with Helvetica.
RANK_LABELS = {1: "#1 (TOP)", 2: "#2", 3: "#3"}


def _score_color(pct: float):
    if pct >= 80:
        return SUCCESS
    if pct >= 60:
        return WARNING
    return DANGER


def _rank_label(i: int) -> str:
    return RANK_LABELS.get(i, f"#{i}")


def _fmt_money(value) -> str:
    try:
        return f"{int(value):,} MAD"
    except (TypeError, ValueError):
        return "—"


def generate_pdf(profile: dict, results: list, original_query: str = "",
                 optimized_prompt: str = "") -> bytes:
    """
    Generate a professional PDF report and return its bytes.

    Never raises: on any internal error a minimal, valid "error report" PDF
    is returned instead, so /api/export-pdf can always send_file() a usable
    document and the frontend download never silently fails.
    """
    try:
        return _build_pdf(profile or {}, results or [], original_query or "",
                           optimized_prompt or "")
    except Exception:
        logger.exception("PDF generation failed — returning fallback report")
        return _build_error_pdf()


def _build_error_pdf() -> bytes:
    """Minimal valid PDF returned if the main report build fails."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("ApartmentAI — Rapport", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "Une erreur est survenue lors de la génération du rapport détaillé. "
            "Veuillez réessayer ou contacter le support.",
            styles["Normal"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Date : {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}",
            styles["Normal"],
        ),
    ]
    doc.build(story)
    return buf.getvalue()


def _build_pdf(profile: dict, results: list, original_query: str,
               optimized_prompt: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    h1 = ParagraphStyle("H1", parent=styles["Normal"], fontSize=22,
                         textColor=PRIMARY, spaceAfter=4, fontName="Helvetica-Bold")
    h2 = ParagraphStyle("H2", parent=styles["Normal"], fontSize=13,
                         textColor=DARK, spaceAfter=4, fontName="Helvetica-Bold",
                         spaceBefore=12)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10,
                           textColor=DARK, leading=15)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8,
                            textColor=colors.HexColor("#64748b"))
    mono = ParagraphStyle("Mono", parent=styles["Normal"], fontSize=9,
                           fontName="Courier", textColor=colors.HexColor("#0284c7"),
                           backColor=colors.HexColor("#f0f9ff"),
                           borderPadding=(6, 8, 6, 8))

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Paragraph("ApartmentAI", h1))
    story.append(Paragraph("Rapport de Recommandation Intelligente", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Généré le {datetime.datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        small,
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=12))

    # ── Original query ───────────────────────────────────────────────────
    if original_query:
        story.append(Paragraph("Requête originale", h2))
        story.append(Paragraph(f'« {_escape(original_query)} »', body))
        story.append(Spacer(1, 8))

    # ── Search criteria ──────────────────────────────────────────────────
    story.append(Paragraph("Critères de recherche", h2))
    criteria = [
        ["Critère", "Valeur"],
        ["Ville", profile.get("city") or "—"],
        ["Budget max", _fmt_money(profile["budget"]) if profile.get("budget") else "—"],
        ["Surface min", f"{profile['surface']} m²" if profile.get("surface") else "Non précisée"],
        ["Chambres", str(profile["bedrooms"]) if profile.get("bedrooms") else "—"],
    ]
    t = Table(criteria, colWidths=[6 * cm, 9 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_BG, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # ── Optimized prompt ─────────────────────────────────────────────────
    if optimized_prompt:
        story.append(Paragraph("Prompt optimisé (IA)", h2))
        story.append(Paragraph(_escape(optimized_prompt).replace("\n", "<br/>"), mono))
        story.append(Spacer(1, 10))

    # ── Recommendations ──────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=6))
    story.append(Paragraph(f"Top {len(results)} Recommandations", h2))

    for i, apt in enumerate(results, 1):
        if not isinstance(apt, dict):
            continue

        pct   = min(100, max(0, apt.get("score_pct", 0) or 0))
        rank  = _rank_label(i)
        color = _score_color(pct)

        # Card header
        hdr_data = [[
            Paragraph(
                f"{rank}  Appartement #{apt.get('id', '—')}  —  {apt.get('quartier', '') or ''}",
                ParagraphStyle("AH", parent=body, fontSize=11,
                               fontName="Helvetica-Bold", textColor=colors.white)),
            Paragraph(
                f"{pct}%",
                ParagraphStyle("SC", parent=body, fontSize=16,
                               fontName="Helvetica-Bold",
                               textColor=colors.white, alignment=TA_RIGHT)),
        ]]
        hdr_table = Table(hdr_data, colWidths=[12 * cm, 4 * cm])
        hdr_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (0, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(hdr_table)

        # Card details (savings value no longer duplicates the row label)
        savings = apt.get("savings")
        savings_str = _fmt_money(savings) if savings and savings > 0 else "—"

        details = [
            ["Ville",   apt.get("ville", "—") or "—",            "Prix",     _fmt_money(apt.get("prix", 0))],
            ["Surface", f"{apt.get('surface', '—')} m²",          "Chambres", str(apt.get("chambres", "—"))],
            ["Valeur",  f"{apt.get('value_ratio', '—')} m²/100k", "Économie", savings_str],
        ]
        dt = Table(details, colWidths=[3.5 * cm, 6 * cm, 3 * cm, 4 * cm])
        dt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT_BG, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY),
            ("TEXTCOLOR", (2, 0), (2, -1), PRIMARY),
        ]))
        story.append(dt)

        # AI Explanation — render reasons as plain ASCII-bulleted text
        reasons = apt.get("reasons") or apt.get("breakdown_reasons") or []
        if reasons:
            reason_text = "  -  ".join(_escape(str(r)) for r in reasons[:5])
            story.append(Paragraph(
                f"<b>Explication IA :</b> {reason_text}",
                ParagraphStyle("Expl", parent=small, spaceBefore=4,
                               backColor=colors.HexColor("#f0fdf4"),
                               borderPadding=(4, 8, 4, 8)),
            ))

        story.append(Spacer(1, 10))

    if not results:
        story.append(Paragraph(
            "Aucune recommandation disponible pour ces critères.",
            ParagraphStyle("Empty", parent=body, textColor=colors.HexColor("#64748b")),
        ))
        story.append(Spacer(1, 10))

    # ── Footer ────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Généré par ApartmentAI — Système de recommandation intelligent · PFE 2025",
        ParagraphStyle("Footer", parent=small, alignment=TA_CENTER),
    ))

    doc.build(story)
    return buf.getvalue()


def _escape(text: str) -> str:
    """Escape characters that have special meaning in reportlab Paragraph XML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
