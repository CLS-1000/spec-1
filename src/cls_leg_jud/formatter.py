# @domain:   publisher
# @module:   formatter
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Formatter for LegJudBrief → Markdown."""
from __future__ import annotations
from cls_leg_jud.schemas import LegJudBrief, LegJudSection


def to_markdown(brief: LegJudBrief) -> str:
    """Render full 8-section brief as Markdown."""
    # If zero eligible, emit termination line
    if brief.eligible_records == 0:
        return f"NO LEGISLATIVE OR JUDICIAL SIGNAL — CYCLE {brief.run_id}"
    lines = [
        f"# Legislative & Judicial Desk — {brief.date}",
        f"*run_id: {brief.run_id} | records: {brief.eligible_records}/{brief.total_records}*",
        "",
    ]
    for section in brief.sections:
        lines.append(section_to_markdown(section))
        lines.append("")
    return "\n".join(lines)


def section_to_markdown(section: LegJudSection) -> str:
    """Render a single section as standalone Markdown (for X publisher)."""
    return f"## {section.title}\n\n{section.body}"


def to_json_summary(brief: LegJudBrief) -> dict:
    return {
        "brief_id": brief.brief_id,
        "run_id": brief.run_id,
        "date": brief.date,
        "eligible_records": brief.eligible_records,
        "sections": [
            {
                "kind": s.kind,
                "title": s.title,
                "has_signal": s.body != "NO SIGNAL THIS CYCLE",
            }
            for s in brief.sections
        ],
    }
