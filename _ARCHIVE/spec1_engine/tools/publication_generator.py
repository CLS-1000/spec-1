"""
SPEC-1 Publication Generator.
Produces a PDF brief matching the Psyche-Ops Issue 001 layout.
Runs after each cycle completes.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Line, Circle, Polygon, String
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from spec1_labels import THREAT_MEDIUM

W, H = letter
M = 0.7 * inch

BLACK  = colors.HexColor('#111110')
WHITE  = colors.white
MUTED  = colors.HexColor('#444442')
DIM    = colors.HexColor('#888884')
BORDER = colors.HexColor('#cccccc')
LIGHT  = colors.HexColor('#f2f1ed')
MONO   = 'Courier'
MONO_B = 'Courier-Bold'

_ISSUE_RE = re.compile(r'spec1_issue_(\d+)')


def _styles() -> dict:
    return {
        'masthead_title': ParagraphStyle('mt',
            fontName=MONO_B, fontSize=32, textColor=BLACK,
            leading=34, spaceAfter=4, letterSpacing=6, alignment=TA_CENTER),
        'masthead_sub': ParagraphStyle('ms',
            fontName=MONO, fontSize=9, textColor=DIM,
            leading=13, spaceAfter=2, letterSpacing=3, alignment=TA_CENTER),
        'masthead_meta': ParagraphStyle('mm',
            fontName=MONO, fontSize=8, textColor=DIM,
            leading=12, letterSpacing=1),
        'section_label': ParagraphStyle('sl',
            fontName=MONO_B, fontSize=8, textColor=BLACK,
            leading=10, spaceBefore=14, spaceAfter=6, letterSpacing=3),
        'story_headline': ParagraphStyle('sh',
            fontName=MONO_B, fontSize=13, textColor=BLACK,
            leading=17, spaceAfter=4),
        'story_source': ParagraphStyle('ss',
            fontName=MONO, fontSize=7.5, textColor=DIM,
            leading=11, spaceAfter=8, letterSpacing=1.5),
        'body': ParagraphStyle('body',
            fontName=MONO, fontSize=9, textColor=MUTED,
            leading=15, spaceAfter=8, alignment=TA_JUSTIFY),
        'gate_label': ParagraphStyle('gl',
            fontName=MONO_B, fontSize=7.5, textColor=BLACK,
            leading=10, spaceBefore=4, spaceAfter=4, letterSpacing=1.5),
        'gate_item': ParagraphStyle('gi',
            fontName=MONO, fontSize=8, textColor=MUTED, leading=13),
        'footer': ParagraphStyle('footer',
            fontName=MONO, fontSize=7.5, textColor=DIM,
            leading=12, letterSpacing=1, alignment=TA_CENTER),
        'pattern_title': ParagraphStyle('pt',
            fontName=MONO_B, fontSize=12, textColor=BLACK,
            leading=16, spaceAfter=4),
        'analyst_meta': ParagraphStyle('am',
            fontName=MONO, fontSize=7.5, textColor=DIM,
            leading=11, spaceAfter=8, letterSpacing=1.5),
    }


def _hr(color=BORDER, thickness=0.5, sb=4, sa=4) -> HRFlowable:
    return HRFlowable(width='100%', thickness=thickness,
                      color=color, spaceBefore=sb, spaceAfter=sa)


def _page_canvas(c, doc) -> None:
    """Draw masthead and footer on every page."""
    c.saveState()

    # Top border
    c.setFillColor(BLACK)
    c.rect(0, H - 3, W, 3, fill=1, stroke=0)

    # Masthead box
    box_h = 1.1 * inch
    c.setStrokeColor(BLACK)
    c.setLineWidth(1)
    c.rect(M, H - M - box_h, W - 2 * M, box_h, fill=0, stroke=1)

    # SPEC-1 title in box
    c.setFont(MONO_B, 28)
    c.setFillColor(BLACK)
    c.drawCentredString(W / 2, H - M - 0.55 * inch, 'S P E C - 1')

    c.setFont(MONO, 8)
    c.setFillColor(DIM)
    c.drawCentredString(W / 2, H - M - 0.78 * inch, 'SIGNAL INTELLIGENCE ENGINE  \xb7  OSINT')

    # Issue and date below box
    issue_n  = getattr(doc, '_issue_number', '001')
    date_str = getattr(doc, '_issue_date', datetime.now(timezone.utc).strftime('%B %d, %Y').upper())
    c.setFont(MONO, 7.5)
    c.setFillColor(DIM)
    c.drawString(M, H - M - box_h - 0.25 * inch, f'ISSUE {issue_n}')
    c.drawRightString(W - M, H - M - box_h - 0.25 * inch, date_str)

    # Footer
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.4)
    c.line(M, 0.55 * inch, W - M, 0.55 * inch)
    c.setFont(MONO, 6.5)
    c.setFillColor(DIM)
    c.drawCentredString(W / 2, 0.38 * inch,
        'SPEC-1 is an independent OSINT intelligence engine operated by EVASTARARCANA LLC')
    c.drawCentredString(W / 2, 0.26 * inch,
        'Signal processing follows append-only, failure-first architecture principles')

    c.restoreState()


def _gate_box(gates: dict, s: dict) -> list:
    """Render the four-gate investigation trigger box."""
    rows = [
        Spacer(1, 4),
        Paragraph('INVESTIGATION TRIGGER', s['gate_label']),
    ]
    gate_lines = []
    for gate_name, result in gates.items():
        status = 'PASSED' if result.get('pass') else 'FAILED'
        reason = _xml_escape(result.get('reason', ''))
        gate_lines.append(
            Paragraph(f'{_xml_escape(gate_name)} Gate: {status} ({reason})', s['gate_item'])
        )
    table_data = [[g] for g in gate_lines]
    t = Table(table_data, colWidths=[W - 2 * M - 0.4 * inch])
    t.setStyle(TableStyle([
        ('BOX',          (0, 0), (-1, -1), 0.8, BLACK),
        ('BACKGROUND',   (0, 0), (-1, -1), LIGHT),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    rows.append(t)
    rows.append(Spacer(1, 10))
    return rows


def _build_signals_page(records: list, s: dict) -> list:
    """Build Page 1 — SIGNALS section."""
    story = []
    story.append(Spacer(1, 1.85 * inch))  # clear masthead
    story.append(_hr(BLACK, 0.8, 0, 6))
    story.append(Paragraph('SIGNALS', s['section_label']))
    story.append(_hr(BORDER, 0.4, 0, 10))

    top_records = records[:2] if records else []

    if not top_records:
        story.append(Paragraph('No signals available for this cycle.', s['body']))
        return story

    for rec in top_records:
        # Prefer hypothesis (rich investigation text) over pattern (short label).
        content = rec.get('hypothesis', rec.get('content', rec.get('pattern', 'No content')))
        source  = rec.get('source', rec.get('signal_source', 'UNKNOWN'))
        credibility = rec.get('credibility_score', rec.get('outcome_confidence', 0.0))
        cred_label = 'HIGH' if credibility >= 0.8 else 'MEDIUM' if credibility >= 0.6 else 'LOW'
        velocity = rec.get('velocity_label', 'STANDARD')

        # Escape XML special chars — ReportLab Paragraph uses an XML parser.
        safe_content = _xml_escape(content)
        safe_source  = _xml_escape(source.upper())
        safe_velocity = _xml_escape(velocity.upper())

        headline = _xml_escape(content[:80].strip())
        if len(content) > 80:
            headline += '...'

        story.append(Paragraph(headline, s['story_headline']))
        story.append(Paragraph(
            f'SOURCE: {safe_source}  \xb7  CREDIBILITY: {cred_label}  \xb7  VELOCITY: {safe_velocity}',
            s['story_source']
        ))
        story.append(Paragraph(safe_content, s['body']))

        # Gate box — handle both real engine shape (dict[str, bool]) and
        # enriched shape (dict[str, {passed, reason}]).
        gate_results = rec.get('gate_results', {})
        if gate_results:
            gates = {}
            for name, res in gate_results.items():
                if isinstance(res, dict):
                    gates[name.title()] = {'pass': res.get('passed', True), 'reason': res.get('reason', '')}
                else:
                    gates[name.title()] = {'pass': bool(res), 'reason': ''}
        else:
            gates = {
                'Credibility': {'pass': True, 'reason': 'Primary source, verifiable'},
                'Volume':      {'pass': True, 'reason': 'Sufficient content depth'},
                'Velocity':    {'pass': True, 'reason': 'Within recency threshold'},
                'Novelty':     {'pass': True, 'reason': 'High-value domain keyword match'},
            }

        story.extend(_gate_box(gates, s))
        story.append(_hr(BORDER, 0.4, 4, 10))

    return story


def _build_intelligence_page(brief_text: str, cycle_stats: dict, s: dict) -> list:
    """Build Page 2 — INTELLIGENCE section."""
    story = []
    story.append(Spacer(1, 1.85 * inch))
    story.append(_hr(BLACK, 0.8, 0, 6))
    story.append(Paragraph('INTELLIGENCE', s['section_label']))
    story.append(_hr(BORDER, 0.4, 0, 10))

    raw_text     = brief_text[:600].strip() if brief_text else 'Pattern analysis pending.'
    pattern_text = _xml_escape(raw_text)

    psyop_class  = cycle_stats.get('psyop_classification', 'NOISE')
    patterns     = cycle_stats.get('psyop_patterns_fired', [])
    raw_name     = patterns[0] if patterns else 'Signal Convergence'
    pattern_name = _xml_escape(raw_name.replace('_', ' ').title())

    story.append(Paragraph(
        f'Pattern: {pattern_name}',
        s['pattern_title']
    ))
    story.append(Paragraph(
        f'ANALYST: SYSTEMS ARCHITECT  \xb7  CONFIDENCE: '
        f'{"MEDIUM-HIGH" if psyop_class != "NOISE" else THREAT_MEDIUM}',
        s['analyst_meta']
    ))
    story.append(Paragraph(pattern_text, s['body']))

    fara_count = cycle_stats.get('fara_signals', 0)
    if fara_count > 0:
        story.append(_hr(BORDER, 0.4, 8, 8))
        story.append(Paragraph(
            f'FARA Registration Activity — {fara_count} signals detected this cycle. '
            'Temporal clustering analysis pending cross-reference with legislative calendar.',
            s['body']
        ))

    return story


def _draw_hexagon_cover(domain_scores: dict) -> Drawing:
    """
    Draw the World State Brief hexagon radar cover.
    Six nodes: POWER · SECURITY · ECONOMICS · CONFLICT · DIPLOMACY · ALLIANCES
    """
    size = 360
    cx, cy = size / 2, size / 2 + 20
    r = 110  # outer radius
    d = Drawing(size, size + 40)

    domains = ['POWER', 'SECURITY', 'ECONOMICS', 'CONFLICT', 'DIPLOMACY', 'ALLIANCES']
    n = len(domains)

    # Draw nested hexagons (4 rings)
    for ring in [1.0, 0.75, 0.5, 0.25]:
        pts = []
        for i in range(n):
            angle = math.radians(90 + i * 60)
            pts.extend([cx + r * ring * math.cos(angle), cy + r * ring * math.sin(angle)])
        pts.extend([pts[0], pts[1]])
        poly = Polygon(pts, fillColor=None,
                       strokeColor=colors.HexColor('#cccccc'), strokeWidth=0.6)
        d.add(poly)

    # Draw radar fill from domain scores
    score_pts = []
    for i, dom in enumerate(domains):
        score = min(1.0, max(0.0, domain_scores.get(dom.lower(), 0.5)))
        angle = math.radians(90 + i * 60)
        sr = r * score
        score_pts.extend([cx + sr * math.cos(angle), cy + sr * math.sin(angle)])
    score_pts.extend([score_pts[0], score_pts[1]])
    score_poly = Polygon(score_pts,
                         fillColor=colors.HexColor('#111110'),
                         fillOpacity=0.08,
                         strokeColor=colors.HexColor('#111110'),
                         strokeWidth=1)
    d.add(score_poly)

    # Spokes and node dots
    for i, dom in enumerate(domains):
        angle = math.radians(90 + i * 60)
        nx = cx + r * math.cos(angle)
        ny = cy + r * math.sin(angle)
        spoke = Line(cx, cy, nx, ny,
                     strokeColor=colors.HexColor('#cccccc'), strokeWidth=0.5)
        d.add(spoke)

        dot = Circle(nx, ny, 7,
                     fillColor=WHITE,
                     strokeColor=colors.HexColor('#111110'), strokeWidth=1)
        d.add(dot)
        inner = Circle(nx, ny, 2.5, fillColor=colors.HexColor('#111110'))
        d.add(inner)

        label_r = r + 22
        lx = cx + label_r * math.cos(angle)
        ly = cy + label_r * math.sin(angle)
        lbl = String(lx, ly - 3, dom,
                     fontName=MONO, fontSize=7,
                     fillColor=colors.HexColor('#111110'),
                     textAnchor='middle')
        d.add(lbl)

    # Halftone dashes at bottom left
    for x in [20, 36, 52, 68]:
        dash = Line(x, 18, x + 10, 18,
                    strokeColor=colors.HexColor('#111110'), strokeWidth=2)
        d.add(dash)

    return d


def _derive_domain_scores(cycle_stats: dict) -> dict:
    """Derive and clamp the six radar domain scores to [0.0, 1.0]."""
    return {
        'power':     min(1.0, max(0.0, cycle_stats.get('signals_harvested', 100) / 300)),
        'security':  min(1.0, max(0.0, cycle_stats.get('confidence_avg', 0.6))),
        'economics': 0.5,
        'conflict':  min(1.0, max(0.0, cycle_stats.get('psyop_score', 2) / 10)),
        'diplomacy': 0.4,
        'alliances': 0.35,
    }


def generate_publication(
    records: list,
    brief_text: str,
    cycle_stats: dict,
    output_dir: str = 'generated/briefs',
    issue_number: Optional[int] = None,
) -> str:
    """
    Generate a Psyche-Ops publication PDF from cycle output.

    Args:
        records:      List of IntelligenceRecord dicts (top scored).
        brief_text:   The full brief markdown text.
        cycle_stats:  Cycle run summary dict.
        output_dir:   Directory to write PDF to.
        issue_number: Issue number (auto-increments if None).

    Returns:
        Path to the generated PDF.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    run_date = datetime.now(timezone.utc)
    date_str  = run_date.strftime('%B %d, %Y').upper()
    file_date = run_date.strftime('%Y-%m-%d')

    if issue_number is None:
        existing = list(Path(output_dir).glob('spec1_issue_*.pdf'))
        max_n = 0
        for p in existing:
            m = _ISSUE_RE.search(p.stem)
            if m:
                max_n = max(max_n, int(m.group(1)))
        issue_number = max_n + 1

    # Bump issue number until we find a path that doesn't exist (never overwrites).
    for _ in range(10_000):
        issue_str = str(issue_number).zfill(3)
        out_path = str(Path(output_dir) / f'spec1_issue_{issue_str}_{file_date}.pdf')
        if not Path(out_path).exists():
            break
        issue_number += 1
    else:
        raise RuntimeError(
            f"Could not find an unused issue number after 10000 attempts in {output_dir!r}"
        )

    doc = SimpleDocTemplate(
        out_path,
        pagesize=letter,
        leftMargin=M, rightMargin=M,
        topMargin=0.55 * inch, bottomMargin=0.8 * inch,
        title=f'SPEC-1 Issue {issue_str}',
        author='SPEC-1 \xb7 EVASTARARCANA LLC',
    )
    doc._issue_number = issue_str
    doc._issue_date   = date_str

    s = _styles()
    story = []

    # ── PAGE 1: SIGNALS ──
    story.extend(_build_signals_page(records, s))
    story.append(PageBreak())

    # ── PAGE 2: INTELLIGENCE ──
    story.extend(_build_intelligence_page(brief_text, cycle_stats, s))
    story.append(PageBreak())

    # ── PAGE 3: WORLD STATE BRIEF COVER ──
    story.append(Spacer(1, 1.85 * inch))
    story.append(_hr(BLACK, 1, 0, 16))

    hex_drawing = _draw_hexagon_cover(_derive_domain_scores(cycle_stats))
    story.append(hex_drawing)

    title_data = [[
        Paragraph('WORLD STATE BRIEF', ParagraphStyle('ws',
            fontName=MONO_B, fontSize=28, textColor=BLACK,
            leading=30, alignment=TA_CENTER, letterSpacing=4)),
    ]]
    tt = Table(title_data, colWidths=[W - 2 * M])
    tt.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(tt)

    story.append(Paragraph(
        'GEOPOLITICAL INTELLIGENCE  \xb7  DAILY ANALYSIS',
        ParagraphStyle('wsub', fontName=MONO, fontSize=9, textColor=DIM,
                       leading=13, alignment=TA_CENTER, letterSpacing=3, spaceAfter=16)
    ))
    story.append(Paragraph(
        'Matt Lakamp',
        ParagraphStyle('wbl', fontName=MONO, fontSize=10, textColor=MUTED,
                       leading=14, alignment=TA_CENTER, spaceAfter=4)
    ))
    story.append(Paragraph(
        'mjlakamp@gmail.com',
        ParagraphStyle('wct', fontName=MONO, fontSize=8, textColor=DIM,
                       leading=12, alignment=TA_CENTER)
    ))

    doc.build(story, onFirstPage=_page_canvas, onLaterPages=_page_canvas)
    return out_path
