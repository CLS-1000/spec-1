# @domain:   publisher
# @module:   cls_weekly_brief_formatter
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Formatter for public weekly brief — Markdown and JSON output with evidence attribution."""

from __future__ import annotations

from cls_weekly_brief.schemas import PublicWeeklyBrief, EvidenceTier


def to_markdown(brief: PublicWeeklyBrief) -> str:
    """Render PublicWeeklyBrief as Markdown document suitable for public distribution."""
    lines: list[str] = []

    # Header
    lines.append(f"# SPEC-1 Public Weekly Intelligence Brief — {brief.week_id}")
    lines.append("")
    lines.append(
        f"**Week of {brief.week_start} to {brief.week_end}**"
    )
    lines.append("")
    lines.append(
        f"*Produced: {brief.produced_at.strftime('%Y-%m-%d %H:%M UTC') if hasattr(brief.produced_at, 'strftime') else brief.produced_at}*"
    )
    lines.append("")

    # Disclaimer
    lines.append("## Disclaimer & Methodology")
    lines.append("")
    lines.append(brief.methodology_note)
    lines.append("")

    # Executive Summary
    lines.append("---")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(brief.executive_summary)
    lines.append("")
    lines.append(
        f"**Records Analyzed:** {brief.records_analyzed} | "
        f"**Verified:** {brief.verified_count} | "
        f"**Inferred:** {brief.inferred_count} | "
        f"**Speculation:** {brief.speculation_count}"
    )
    lines.append("")

    # Sections by evidence tier
    for section in brief.sections:
        lines.append("---")
        lines.append("")
        lines.append(f"## {section.title} ({section.category})")
        lines.append("")

        # VERIFIED subsection
        if section.verified_items:
            lines.append("### ✓ VERIFIED")
            lines.append("")
            for item in section.verified_items:
                lines.append(
                    f"**[{item.confidence:.0%} confidence]** {item.content[:400]}"
                )
                if item.source_ids:
                    lines.append(f"  - Source: {', '.join(item.source_ids)}")
                if item.published_at:
                    lines.append(f"  - Date: {item.published_at}")
                if item.analyst_notes:
                    lines.append(f"  - Note: {item.analyst_notes}")
                lines.append("")

        # INFERRED subsection
        if section.inferred_items:
            lines.append("### ≈ INFERRED (Analysis)")
            lines.append("")
            for item in section.inferred_items:
                lines.append(
                    f"**[{item.confidence:.0%} confidence]** {item.content[:400]}"
                )
                if item.source_ids:
                    lines.append(f"  - Basis: {', '.join(item.source_ids)}")
                if item.published_at:
                    lines.append(f"  - Date: {item.published_at}")
                if item.analyst_notes:
                    lines.append(f"  - Note: {item.analyst_notes}")
                lines.append("")

        # SPECULATION subsection
        if section.speculation_items:
            lines.append("### ? SPECULATION (Requires Validation)")
            lines.append("")
            for item in section.speculation_items:
                lines.append(
                    f"**[{item.confidence:.0%} confidence]** {item.content[:400]}"
                )
                if item.source_ids:
                    lines.append(f"  - Source: {', '.join(item.source_ids)}")
                if item.published_at:
                    lines.append(f"  - Date: {item.published_at}")
                lines.append("")

    # Metadata footer
    lines.append("---")
    lines.append("")
    lines.append("## Brief Metadata")
    lines.append("")
    lines.append(f"- **Brief ID:** {brief.brief_id}")
    lines.append(f"- **Week ID:** {brief.week_id}")
    lines.append(f"- **Total Domains:** {len(brief.sections)}")
    lines.append(f"- **Source Domains:** {brief.metadata.get('source_count', 0)}")
    lines.append(f"- **Evidence Classification:** {brief.verified_count} VERIFIED, "
                 f"{brief.inferred_count} INFERRED, {brief.speculation_count} SPECULATION")
    lines.append("")
    lines.append("*This brief is produced by SPEC-1, an open-source intelligence "
                 "platform using rule-based aggregation and LLM-assisted analysis.*")

    return "\n".join(lines)


def to_json_summary(brief: PublicWeeklyBrief) -> dict:
    """Return a lightweight JSON-serialisable summary suitable for API responses."""
    sections_summary = []
    for section in brief.sections:
        sections_summary.append({
            "title": section.title,
            "category": section.category,
            "verified_count": len(section.verified_items),
            "inferred_count": len(section.inferred_items),
            "speculation_count": len(section.speculation_items),
        })

    return {
        "brief_id": brief.brief_id,
        "week_id": brief.week_id,
        "week_start": brief.week_start,
        "week_end": brief.week_end,
        "executive_summary": brief.executive_summary,
        "produced_at": brief.produced_at.isoformat()
        if hasattr(brief.produced_at, "isoformat")
        else str(brief.produced_at),
        "records_analyzed": brief.records_analyzed,
        "verified_count": brief.verified_count,
        "inferred_count": brief.inferred_count,
        "speculation_count": brief.speculation_count,
        "sections": sections_summary,
        "metadata": brief.metadata,
    }


def to_full_json(brief: PublicWeeklyBrief) -> dict:
    """Return complete JSON representation with all evidence items."""
    return brief.to_dict()
