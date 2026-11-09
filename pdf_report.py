"""Create executive PDF reports from submitted scan records; no network access."""
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from scoring import BANDS, CAVEAT, VERSION
from wordlist import load_wordlist


def executive_report(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("A report must contain a records list.")
    records = [r for r in payload["records"] if isinstance(r, dict) and not r.get("error")
               and isinstance(r.get("status"), int) and 200 <= r["status"] < 300]
    records.sort(key=lambda r: (r.get("assessment") or {}).get("score") if isinstance((r.get("assessment") or {}).get("score"), (int, float)) else -1, reverse=True)
    assessed = [r for r in records if isinstance((r.get("assessment") or {}).get("score"), (int, float))]
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    return {"records": records, "parameters": parameters,
            "mode": "Database scan" if payload.get("scan_type") == "database" else "Single URL scan",
            "complete": payload.get("complete", True) is True,
            "fetched": len(records), "assessed": len(assessed),
            "flagged": sum((r.get("assessment") or {}).get("score", 0) >= 50 for r in assessed),
            "coverage": parameters.get("urls", len(payload["records"]))}


def render_pdf(payload):
    from reportlab import rl_config
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    report = executive_report(payload)
    import reportlab
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, filename in [("Report", "Vera.ttf"), ("ReportBold", "VeraBd.ttf")]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    pdfmetrics.registerFontFamily("Report", normal="Report", bold="ReportBold", italic="Report", boldItalic="ReportBold")
    navy, green, muted = colors.HexColor("#142e28"), colors.HexColor("#147653"), colors.HexColor("#51625c")
    styles = {
        "title": ParagraphStyle("Title", fontName="ReportBold", fontSize=25, leading=31, textColor=navy, spaceAfter=10),
        "h2": ParagraphStyle("H2", fontName="ReportBold", fontSize=13, leading=18, textColor=navy, spaceBefore=14, spaceAfter=7),
        "body": ParagraphStyle("Body", fontName="Report", fontSize=9, leading=14, textColor=navy, spaceAfter=7, splitLongWords=True),
        "small": ParagraphStyle("Small", fontName="Report", fontSize=8, leading=12, textColor=muted, spaceAfter=6, splitLongWords=True),
        "metric": ParagraphStyle("Metric", fontName="ReportBold", fontSize=19, leading=24, textColor=green),
    }
    def safe(value):
        # Vera lacks emoji; render unsupported glyphs explicitly instead of black squares.
        cmap = pdfmetrics.getFont("Report").face.charToGlyph
        text = str(value)
        return escape("".join(c if ord(c) in cmap or c in "\n\t" else f"[U+{ord(c):04X}]" for c in text if ord(c) >= 32 or c in "\n\t"))
    def p(value, kind="body"):
        return Paragraph(safe(value), styles[kind])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm,
                            title="Executive scan report", author="Vibe code scanner")
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    story = [p("EXECUTIVE REVIEW", "small"), p("Content scan report", "title"),
             p(f"{report['mode']}  |  {now}", "small")]
    if not report["complete"]:
        story.append(p("PARTIAL REPORT - Scan stopped or interrupted. Findings cover only results received.", "h2"))
    params = report["parameters"]
    if params.get("cashout_method"):
        story.append(p(f"Cashout method: {params['cashout_method']} | Message limit: {params.get('limit', '-')} | Messages selected: {params.get('messages', '-')}", "small"))
    metrics = Table([[p(str(report["fetched"]), "metric"), p(str(report["assessed"]), "metric"), p(str(report["flagged"]), "metric")],
                     [p("Pages fetched", "small"), p("Pages scored", "small"), p("Flagged for review", "small")]], colWidths=[doc.width/3]*3)
    metrics.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#edf5f1")),
                                ("TOPPADDING", (0,0), (-1,0), 12), ("BOTTOMPADDING", (0,-1), (-1,-1), 10),
                                ("LEFTPADDING", (0,0), (-1,-1), 12)]))
    story += [Spacer(1, 10), metrics, Spacer(1, 10),
              p(f"Coverage: {report['fetched']} successfully fetched pages from {report['coverage']} discovered URLs. Unavailable pages are outside this assessment.", "small"),
              p(CAVEAT, "small"), p(BANDS, "small"), p("Findings by review priority", "h2")]
    if not report["records"]:
        story.append(p("No successfully fetched pages are available. No assessment or safety conclusion can be made."))
    for index, record in enumerate(report["records"], start=1):
        assessment = record.get("assessment") or {}
        score = assessment.get("score")
        valid_score = isinstance(score, (int, float)) and 0 <= score <= 100
        label = f"{score}/100 - {assessment.get('level', 'Review')} priority" if valid_score else "Not assessed"
        url = str(record.get("url") or "Unknown URL")
        display = url if len(url) <= 240 else url[:237]+"..."
        story.append(KeepTogether([p(f"{index}. {label}", "h2"), p(display, "small")]))
        story.append(p(assessment.get("explanation") or "No assessment was available for this page."))
        for factor in assessment.get("factors", [])[:6]:
            if isinstance(factor, dict):
                story.append(p(f"{factor.get('name', 'Signal')} (+{factor.get('points', 0)}): {str(factor.get('evidence', ''))[:180]}", "small"))
        if assessment.get("action"):
            story.append(p("Recommended action: " + str(assessment["action"])))
    story += [p("Scoring methodology", "h2"),
              p("Wordlist category caps: " + "; ".join(f"{g['name']}: {g['cap']}" for g in load_wordlist()) + ". Additional checks: repeated language 10; unusual formatting 5. Distinct matches contribute points up to each category cap; repeating an entry does not multiply points. Total score is capped at 100. Text groups examine extracted text; source groups also examine HTML and scripts. Limited-text pages without wordlist evidence are not scored. Content requiring JavaScript may be missing.", "small"),
              p(f"Model: {VERSION}. Rule-based and uncalibrated. Validate with labeled legitimate and fraudulent examples before operational use. Long URLs are abbreviated for readability; JSON exports retain full URLs.", "small")]
    def footer(canvas, document):
        canvas.setStrokeColor(colors.HexColor("#d6e2dc"))
        canvas.line(20*mm, 16*mm, A4[0]-20*mm, 16*mm)
        canvas.setFont("Report", 8)
        canvas.setFillColor(muted)
        canvas.drawString(20*mm, 11*mm, "Content scan report | Review support")
        canvas.drawRightString(A4[0]-20*mm, 11*mm, f"Page {document.page}")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        sys.stdout.buffer.write(render_pdf(payload))
    except Exception:
        print("Could not generate report. Install requirements.txt and submit valid scan results.", file=sys.stderr)
        sys.exit(1)
