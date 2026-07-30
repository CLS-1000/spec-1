# @domain:   citizens_source
# @module:   publication_newsletter
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Markdown + PDF newsletter renderer for Metro Citizens Brief."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from cls_pdx1.models import Issue

logger = logging.getLogger(__name__)

_HEADER = """\
# Metro Citizens Brief
**Portland Metro Intelligence — PDX-1i**

---
"""

_FOOTER = """\
---
*Metro Citizens Brief is produced by SPEC-1 / PDX-1i. Every factual claim carries
a source citation. Raw source links appear inline. This brief is for informational
purposes only.*
"""


def to_markdown(issue: Issue) -> str:
    """Render an Issue to Markdown text."""
    lines = [_HEADER]
    lines.append(f"## Issue #{issue.issue_number} — {issue.title}\n")
    lines.append(f"*Published: {issue.published_at.strftime('%B %d, %Y')}*\n")
    lines.append("")

    if not issue.sections:
        lines.append("*No sections in this issue.*\n")
    else:
        for section in issue.sections:
            lines.append(f"### {section.title}\n")
            lines.append(section.body)
            lines.append(f"\n*Source: [{section.source_uri}]({section.source_uri})*\n")
            lines.append("")

    lines.append(_FOOTER)
    return "\n".join(lines)


def write_markdown(issue: Issue, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"mcb_issue_{issue.issue_number:04d}.md"
    path = output_dir / filename
    path.write_text(to_markdown(issue), encoding="utf-8")
    logger.info("MCB markdown written: %s", path)
    return path


def write_pdf(issue: Issue, output_dir: Path) -> Optional[Path]:
    """Write PDF via ReportLab. Returns None if ReportLab unavailable."""
    try:
        from reportlab.lib.pagesizes import LETTER  # type: ignore
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer  # type: ignore
        from reportlab.lib.styles import getSampleStyleSheet  # type: ignore
        from reportlab.lib.units import inch  # type: ignore
    except ImportError:
        logger.warning("reportlab not installed — PDF skipped")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"mcb_issue_{issue.issue_number:04d}.pdf"
    path = output_dir / filename

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    story = []

    story.append(Paragraph("Metro Citizens Brief", styles["Title"]))
    story.append(Paragraph(f"Issue #{issue.issue_number} — {issue.title}", styles["Heading1"]))
    story.append(Paragraph(f"Published: {issue.published_at.strftime('%B %d, %Y')}", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    for section in issue.sections:
        story.append(Paragraph(section.title, styles["Heading2"]))
        story.append(Paragraph(section.body, styles["Normal"]))
        story.append(Paragraph(f"Source: {section.source_uri}", styles["Italic"]))
        story.append(Spacer(1, 0.1 * inch))

    doc.build(story)
    logger.info("MCB PDF written: %s", path)
    return path
