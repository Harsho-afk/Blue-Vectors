"""
Render a report JSON snapshot into a self-contained, downloadable PDF document.
Uses ReportLab to build a professional, vector-based PDF.
"""

import io
import html
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Define design system colors (Light mode print theme)
PRIMARY_COLOR = colors.HexColor("#1e3a8a")    # Deep Indigo
SECONDARY_COLOR = colors.HexColor("#3b82f6")  # Blue Accent
TEXT_COLOR = colors.HexColor("#1f2937")       # Charcoal
MUTED_COLOR = colors.HexColor("#4b5563")      # Gray
BORDER_COLOR = colors.HexColor("#e5e7eb")     # Light Gray
BG_LIGHT = colors.HexColor("#f9fafb")         # Light Background Card
WHITE = colors.HexColor("#ffffff")

# Helper for cell colors depending on confidence bands
CONFIDENCE_COLORS = {
    "High": colors.HexColor("#16a34a"),
    "Medium": colors.HexColor("#d97706"),
    "Low": colors.HexColor("#6b7280"),
}


def _e(text) -> str:
    """Escape text for XML safely."""
    if text is None:
        return ""
    return html.escape(str(text))


_CONFIDENCE_PLAIN = {
    "high": "Strong evidence — very likely accurate.",
    "medium": "Reasonable evidence — probably accurate, but not certain.",
    "low": "Weak or thin evidence — worth a second look before relying on it.",
}


def _plain_confidence(band: str) -> str:
    """Return a plain-English explanation of a confidence band."""
    return _CONFIDENCE_PLAIN.get((band or "").lower(), "Confidence level for this finding.")


def render_report_pdf(report: dict) -> bytes:
    """
    Renders structured report JSON into PDF bytes.
    """
    meta = report.get("report_metadata", {})
    scope = report.get("scope_and_methodology", {})
    summary = report.get("executive_summary", {})
    accounts_section = report.get("identified_accounts", {})
    correlations = report.get("correlation_findings", [])
    insights_section = report.get("analytical_insights", {})
    limitations = report.get("limitations", [])
    confidence = report.get("confidence_notes", {})
    intelligence = report.get("intelligence_briefing")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=54,  # 0.75 in
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    # Initialize styles
    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=PRIMARY_COLOR,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        textColor=MUTED_COLOR,
        spaceAfter=15,
    )

    h1_style = ParagraphStyle(
        "SectionHeading",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=PRIMARY_COLOR,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SubSectionHeading",
        parent=base_styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=SECONDARY_COLOR,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "BodyText",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=TEXT_COLOR,
        spaceAfter=5,
    )

    bold_body_style = ParagraphStyle(
        "BoldBodyText", parent=body_style, fontName="Helvetica-Bold"
    )

    bullet_style = ParagraphStyle(
        "BulletText",
        parent=body_style,
        leftIndent=15,
        bulletIndent=5,
        spaceAfter=4,
    )

    disclaimer_style = ParagraphStyle(
        "DisclaimerText",
        parent=body_style,
        fontName="Helvetica-Oblique",
        textColor=MUTED_COLOR,
        spaceAfter=4,
    )

    elements = []

    # ── Horizontal line generator ──
    def draw_hr():
        t = Table([[""]], colWidths=[504], rowHeights=[1])
        t.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -1), 1, BORDER_COLOR),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return t

    # ── 1. Header & Metadata ──
    elements.append(Paragraph("ARIA SOCMINT Investigation Report", title_style))
    elements.append(
        Paragraph(
            f"Case: {_e(meta.get('case_title', 'Unknown'))} | "
            f"Generated: {_e(meta.get('generated_at', ''))}",
            subtitle_style,
        )
    )
    elements.append(draw_hr())
    elements.append(Spacer(1, 10))

    # ── 1. Report Metadata ──
    elements.append(Paragraph("Report Metadata", h1_style))
    meta_rows = [
        [Paragraph("<b>Case ID</b>", bold_body_style), Paragraph(str(meta.get("case_id", "")), body_style)],
        [Paragraph("<b>Title</b>", bold_body_style), Paragraph(_e(meta.get("case_title", "")), body_style)],
        [Paragraph("<b>Status</b>", bold_body_style), Paragraph(str(meta.get("case_status", "open")), body_style)],
        [Paragraph("<b>Investigator</b>", bold_body_style), Paragraph(_e(meta.get("investigator", "Unknown")), body_style)],
        [Paragraph("<b>Generated</b>", bold_body_style), Paragraph(str(meta.get("generated_at", "")), body_style)],
        [Paragraph("<b>Methodology</b>", bold_body_style), Paragraph(f"v{_e(meta.get('methodology_version', '1.0'))}", body_style)],
    ]
    meta_table = Table(meta_rows, colWidths=[130, 374])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), BG_LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    # ── 2. Intelligence Briefing (AI narrative), directly below metadata ──
    if intelligence:
        elements.append(Paragraph("Executive Intelligence Briefing", h1_style))
        elements.append(Paragraph("<i>[AI-ASSISTED SYNTHESIS]</i>", disclaimer_style))
        narrative = intelligence.get("narrative", "")
        if narrative:
            # Split by double newline to preserve paragraph separation
            paragraphs = re.split(r"\n\s*\n", narrative.strip())
            for p_text in paragraphs:
                elements.append(Paragraph(_e(p_text), body_style))
                elements.append(Spacer(1, 6))
        elements.append(Spacer(1, 8))

    # ── 3. Summary (AI-generated executive summary) ──
    elements.append(Paragraph("Summary", h1_style))

    summary_bands = summary.get("correlation_bands", {})
    summary_cats = summary.get("insight_categories", {})

    sum_rows = [
        [
            Paragraph("<b>Accounts collected</b>", bold_body_style),
            Paragraph(str(summary.get("total_accounts_collected", 0)), body_style),
            Paragraph("<b>Platforms</b>", bold_body_style),
            Paragraph(str(summary.get("total_platforms", 0)), body_style),
        ],
        [
            Paragraph("<b>Correlations</b>", bold_body_style),
            Paragraph(str(summary.get("total_correlations", 0)), body_style),
            Paragraph("<b>Sources</b>", bold_body_style),
            Paragraph(str(summary.get("total_sources", 0)), body_style),
        ],
        [
            Paragraph("<b>High-confidence</b>", bold_body_style),
            Paragraph(str(summary_bands.get("High", 0)), body_style),
            Paragraph("<b>Medium-confidence</b>", bold_body_style),
            Paragraph(str(summary_bands.get("Medium", 0)), body_style),
        ],
        [
            Paragraph("<b>Low-confidence</b>", bold_body_style),
            Paragraph(str(summary_bands.get("Low", 0)), body_style),
            Paragraph("<b>Insights generated</b>", bold_body_style),
            Paragraph(str(summary.get("total_insights", 0)), body_style),
        ],
    ]
    sum_table = Table(sum_rows, colWidths=[126, 126, 126, 126])
    sum_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (0, -1), BG_LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), BG_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(sum_table)
    elements.append(Spacer(1, 10))

    takeaways = summary.get("key_takeaways", [])
    if takeaways:
        elements.append(Paragraph("Key Takeaways", h2_style))
        for t in takeaways:
            elements.append(Paragraph(f"• {_e(t)}", bullet_style))
        elements.append(Spacer(1, 10))

    if summary_cats:
        elements.append(Paragraph("Insights by Category", h2_style))
        for cat, val in summary_cats.items():
            elements.append(Paragraph(f"• <b>{_e(cat)}</b>: {val}", bullet_style))
        elements.append(Spacer(1, 10))

    # ── 4. Scope & Methodology ──
    elements.append(Paragraph("Scope &amp; Methodology", h1_style))
    elements.append(Paragraph("Seed Identifiers", h2_style))
    for s in scope.get("seed_identifiers", []):
        hint = f" ({_e(s['platform_hint'])})" if s.get("platform_hint") else ""
        elements.append(Paragraph(f"• <b>{_e(s.get('type','').upper())}</b>: {_e(s.get('value',''))}{hint}", bullet_style))
    elements.append(Spacer(1, 8))

    methods_str = ", ".join(scope.get("collection_methods", []))
    platforms_str = ", ".join(scope.get("platforms_collected", []))
    elements.append(Paragraph(f"<b>Collection Methods:</b> {_e(methods_str)}", body_style))
    elements.append(Paragraph(f"<b>Platforms Searched:</b> {_e(platforms_str)}", body_style))

    window = scope.get("collection_window")
    if window:
        elements.append(
            Paragraph(
                f"<b>Collection Window:</b> {_e(window.get('earliest', ''))} — {_e(window.get('latest', ''))}",
                body_style,
            )
        )
    elements.append(Spacer(1, 8))

    statement = scope.get("public_source_statement", "")
    if statement:
        elements.append(Paragraph(f"<i>{_e(statement)}</i>", disclaimer_style))
    elements.append(Spacer(1, 10))

    # ── 5. Identified Accounts ──
    elements.append(Paragraph("Identified Accounts", h1_style))

    collected_accounts = accounts_section.get("collected_accounts", [])
    if collected_accounts:
        elements.append(Paragraph("Collected Target Profiles", h2_style))
        acc_table_data = [
            [
                Paragraph("<b>Ref</b>", bold_body_style),
                Paragraph("<b>Platform</b>", bold_body_style),
                Paragraph("<b>Username</b>", bold_body_style),
                Paragraph("<b>Display Name</b>", bold_body_style),
                Paragraph("<b>Posts</b>", bold_body_style),
                Paragraph("<b>Status</b>", bold_body_style),
            ]
        ]
        for a in collected_accounts:
            acc_table_data.append(
                [
                    Paragraph(a.get("reference_id", ""), body_style),
                    Paragraph(a.get("platform", ""), body_style),
                    Paragraph(a.get("username", ""), body_style),
                    Paragraph(_e(a.get("display_name", "")), body_style),
                    Paragraph(str(a.get("post_count", 0)), body_style),
                    Paragraph(a.get("collection_status", ""), body_style),
                ]
            )
        acc_table = Table(
            acc_table_data,
            colWidths=[50, 75, 100, 139, 50, 90],
            repeatRows=1,
        )
        acc_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BG_LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("PADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elements.append(acc_table)
        elements.append(Spacer(1, 10))

    leads = accounts_section.get("discovered_leads", [])
    if leads:
        elements.append(Paragraph("Discovered Leads (Unverified Profiles)", h2_style))
        leads_table_data = [
            [
                Paragraph("<b>Platform</b>", bold_body_style),
                Paragraph("<b>Username</b>", bold_body_style),
                Paragraph("<b>Profile URL</b>", bold_body_style),
                Paragraph("<b>Status</b>", bold_body_style),
            ]
        ]
        # Show at most 25 leads to prevent report bloat
        for d in leads[:25]:
            leads_table_data.append(
                [
                    Paragraph(d.get("platform", ""), body_style),
                    Paragraph(d.get("username", ""), body_style),
                    Paragraph(f"<font color='blue'>{_e(d.get('url', ''))}</font>", body_style),
                    Paragraph(d.get("status", ""), body_style),
                ]
            )
        leads_table = Table(
            leads_table_data,
            colWidths=[80, 100, 234, 90],
            repeatRows=1,
        )
        leads_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BG_LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("PADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        elements.append(leads_table)
        elements.append(Spacer(1, 10))

    # ── 6. Correlation Findings ──
    elements.append(Paragraph("Correlation Findings", h1_style))
    if not correlations:
        elements.append(Paragraph("No significant identity correlations detected.", body_style))
    else:
        for c in correlations:
            band = c.get("band", "Low")
            band_color = CONFIDENCE_COLORS.get(band, MUTED_COLOR)
            confidence_pct = c.get("confidence_pct", 0)

            # Build a cohesive card using a nested KeepTogether block
            corr_blocks = []
            title_text = (
                f"<b>{c.get('account_a', {}).get('platform', '')}/{c.get('account_a', {}).get('username', '')}</b> ↔ "
                f"<b>{c.get('account_b', {}).get('platform', '')}/{c.get('account_b', {}).get('username', '')}</b>"
            )
            corr_blocks.append(Paragraph(title_text, bold_body_style))

            meta_line = (
                f"Confidence Score: <b>{confidence_pct:.1f}%</b> | "
                f"Confidence Band: <font color='{band_color.hexval()}'><b>{band}</b></font> | "
                f"Reference ID: {c.get('reference_id', '')}"
            )
            corr_blocks.append(Paragraph(meta_line, body_style))
            corr_blocks.append(Paragraph(f"<i>{_e(_plain_confidence(band))}</i>", disclaimer_style))
            corr_blocks.append(Spacer(1, 4))
            corr_blocks.append(Paragraph(f"<b>Method:</b> {c.get('evidence_type', 'N/A')}", body_style))
            corr_blocks.append(Paragraph(f"<b>Assessment:</b> {_e(c.get('conclusion', ''))}", body_style))

            # Build card layout
            card_rows = [[corr_blocks]]
            card_table = Table(card_rows, colWidths=[504])
            card_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), BG_LIGHT),
                        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                        ("LINELEFT", (0, 0), (0, -1), 4, band_color),
                        ("PADDING", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            elements.append(KeepTogether([card_table, Spacer(1, 10)]))

    # ── 7. Insights, Limitations, Confidence Framework ──

    # Insights
    elements.append(Paragraph("Analytical Insights", h1_style))
    insights = insights_section.get("insights", [])
    if not insights:
        elements.append(Paragraph("No analytical insights generated for this case.", body_style))
    else:
        for ins in insights:
            elements.append(
                Paragraph(
                    f"• <b>[{_e(ins.get('category', 'Insight'))}]</b> {_e(ins.get('claim', ''))} (Confidence: {ins.get('confidence', '')})",
                    bullet_style,
                )
            )
        elements.append(Spacer(1, 12))

    # Limitations
    elements.append(Paragraph("Limitations &amp; Data Gaps", h1_style))
    if not limitations:
        elements.append(Paragraph("No specific data capture limitations noted.", body_style))
    else:
        for lim in limitations:
            elements.append(Paragraph(f"• {_e(lim)}", bullet_style))
        elements.append(Spacer(1, 12))

    # Confidence Framework
    elements.append(Paragraph("Confidence Framework &amp; Disclaimers", h1_style))
    elements.append(
        Paragraph(
            "In plain terms: \"High\" means we're pretty sure, \"Medium\" means it's a good "
            "guess, and \"Low\" means treat it as an unverified tip.",
            disclaimer_style,
        )
    )
    band_defs = confidence.get("band_definitions", {})
    for band, desc in band_defs.items():
        band_color = CONFIDENCE_COLORS.get(band, MUTED_COLOR)
        elements.append(
            Paragraph(
                f"• <font color='{band_color.hexval()}'><b>{band} Confidence</b></font>: {_e(desc)} "
                f"<i>({_e(_plain_confidence(band))})</i>",
                bullet_style,
            )
        )
    elements.append(Spacer(1, 6))
    disclaimer = confidence.get("disclaimer", "")
    if disclaimer:
        elements.append(Paragraph(f"<i>{_e(disclaimer)}</i>", disclaimer_style))
    elements.append(Spacer(1, 12))

    # Build PDF doc
    doc.build(elements)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
