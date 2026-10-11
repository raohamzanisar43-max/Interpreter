"""Branded company report PDF (reportlab; WeasyPrint needs GTK libraries that are awkward on Windows)."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, String

BRAND = colors.HexColor("#0b5cab")
MUTED = colors.HexColor("#5b6670")
SELF = colors.HexColor("#e07a1f")


def _bars(rows, width=170 * mm, bar_h=14):
    """rows: [(label, score, highlight)] -> horizontal bar chart drawing."""
    h = len(rows) * (bar_h + 6) + 6
    d = Drawing(width, h)
    label_w = 38 * mm
    for i, (label, score, hl) in enumerate(rows):
        y = h - (i + 1) * (bar_h + 6)
        d.add(String(0, y + 3, str(label)[:28], fontSize=8, fillColor=colors.black))
        full = width - label_w - 25
        d.add(Rect(label_w, y, full, bar_h, fillColor=colors.HexColor("#eef1f4"), strokeColor=None))
        if score is not None:
            d.add(Rect(label_w, y, full * score / 100, bar_h, fillColor=SELF if hl else BRAND, strokeColor=None))
            d.add(String(label_w + full + 4, y + 3, f"{score:.0f}%", fontSize=8))
    return d


def render_report_pdf(company_name, round_name, data, summary):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            bottomMargin=18 * mm, title=f"EQAL report - {round_name}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=BRAND, fontSize=26, leading=30, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BRAND, spaceBefore=14)
    body = ParagraphStyle("b", parent=ss["BodyText"], leading=15)
    muted = ParagraphStyle("m", parent=body, textColor=MUTED, fontSize=9)
    s = [Spacer(1, 50 * mm), Paragraph("EQAL", h1), Paragraph("Interpreter quality report", ss["Heading2"]),
         Spacer(1, 10 * mm), Paragraph(f"<b>{company_name}</b>", ss["Heading2"]),
         Paragraph(f"Round: {round_name} &nbsp;·&nbsp; Language: {data['round']['language']}", body),
         Paragraph("Confidential - prepared for the named company only.", muted), PageBreak()]

    s.append(Paragraph("Overall result", h2))
    overall = data.get("overall_score")
    rows = [["Overall score", f"{overall:.1f}%" if overall is not None else "n/a"]]
    if data.get("ranking_visible"):
        rows.append(["Rank", f"{data['rank']} of {data['companies_count']}"])
        rows.append(["Percentile", f"better than {data['percentile']}% of participating companies"])
    else:
        rows.append(["Ranking", "Not shown (fewer than 3 participating companies protects anonymity)"])
    t = Table(rows, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 11), ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
    s.append(t)
    if data.get("peer_distribution"):
        s += [Paragraph("Peer distribution (anonymous)", h2),
              _bars([(p["label"], p["score"], p["is_self"]) for p in data["peer_distribution"]])]
    if data.get("per_recording"):
        s += [Paragraph("By recording", h2), _bars([(x["title"], x["score"], False) for x in data["per_recording"]])]
    if data.get("per_category"):
        s += [Paragraph("By key-point category", h2),
              _bars([(x["category"].capitalize(), x["score"], False) for x in data["per_category"]])]
    if data.get("pairwise_win_rate") is not None:
        s.append(Paragraph(f"Head-to-head win rate: {data['pairwise_win_rate']:.0f}%", body))
    if summary:
        s += [Paragraph("Summary", h2)] + [Paragraph(p, body) for p in summary.split("\n") if p.strip()]
    s += [Paragraph("Methodology", h2), Paragraph(data.get("methodology", ""), muted)]
    doc.build(s)
    return buf.getvalue()
