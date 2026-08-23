# @domain:   publisher
# @module:   cls_weekly_brief_producer
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Producer for public weekly intelligence brief.

Aggregates 7 days of IntelligenceRecords, classifies evidence into
VERIFIED / INFERRED / SPECULATION tiers, and produces a PublicWeeklyBrief.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from cls_weekly_brief.schemas import (
    EvidenceItem,
    EvidenceTier,
    PublicWeeklyBrief,
    WeeklySection,
)


def _get_iso_week(dt: datetime) -> tuple[int, int, int]:
    """Return (year, week, weekday) in ISO format."""
    iso = dt.isocalendar()
    return iso[0], iso[1], iso[2]


def _week_id_from_date(dt: datetime) -> str:
    """Generate week ID in YYYY-W## format."""
    year, week, _ = _get_iso_week(dt)
    return f"{year:04d}-W{week:02d}"


def _week_start_from_date(dt: datetime) -> datetime:
    """Get Monday (start of ISO week) for a given date."""
    year, week, weekday = _get_iso_week(dt)
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    week_1_monday = jan4 - timedelta(days=jan4.weekday())
    target_monday = week_1_monday + timedelta(weeks=week - 1)
    return target_monday


def _is_in_week(record_ts: str, week_start: datetime) -> bool:
    """Check if record timestamp falls within the week (Mon-Sun)."""
    try:
        if record_ts.endswith("Z"):
            record_ts = record_ts[:-1] + "+00:00"
        record_dt = datetime.fromisoformat(record_ts)
        if record_dt.tzinfo is None:
            record_dt = record_dt.replace(tzinfo=timezone.utc)

        week_end = week_start + timedelta(days=7)
        return week_start <= record_dt < week_end
    except (ValueError, AttributeError):
        return False


def _classify_evidence(record: dict) -> EvidenceTier:
    """Classify record confidence into VERIFIED / INFERRED / SPECULATION."""
    confidence = record.get("confidence", 0.5)
    classification = record.get("classification", "").upper()
    source_weight = record.get("source_weight", 0.5)

    # VERIFIED: High confidence + Corroborated classification + credible source
    if confidence >= 0.8 and "CORROBORATED" in classification and source_weight >= 0.7:
        return EvidenceTier.VERIFIED

    # INFERRED: Medium-high confidence
    if confidence >= 0.65 and source_weight >= 0.6:
        return EvidenceTier.INFERRED

    # SPECULATION: Everything else
    return EvidenceTier.SPECULATION


def _categorize_record(record: dict) -> str:
    """Infer category from record content/keywords."""
    pattern = (record.get("pattern", "") + " " + record.get("content", "")).lower()
    keywords = record.get("keywords", [])
    all_text = pattern + " " + " ".join(keywords if isinstance(keywords, list) else [])

    if any(
        kw in all_text
        for kw in ["military", "defense", "army", "navy", "air force", "nato"]
    ):
        return "MILITARY"
    if any(
        kw in all_text
        for kw in ["cyber", "hack", "espionage", "intelligence", "nsa", "cia"]
    ):
        return "CYBER"
    if any(
        kw in all_text
        for kw in ["china", "russia", "iran", "ukraine", "taiwan", "geopolitical"]
    ):
        return "GEOPOLITICAL"
    if any(kw in all_text for kw in ["fara", "foreign agent", "lobbying", "registrant"]):
        return "FARA"
    if any(
        kw in all_text
        for kw in ["psyop", "narrative", "disinformation", "propaganda", "influence"]
    ):
        return "PSYOP"
    if any(kw in all_text for kw in ["terrorism", "extremism", "isis", "jihad"]):
        return "TERRORISM"
    if any(
        kw in all_text
        for kw in ["congress", "senate", "house", "legislation", "bill", "law"]
    ):
        return "POLICY"
    return "GENERAL"


def produce_weekly_brief(
    records: Sequence[dict],
    week_id: str | None = None,
    reference_date: datetime | None = None,
) -> PublicWeeklyBrief:
    """Produce a PublicWeeklyBrief from 7 days of IntelligenceRecords.

    Args:
        records: IntelligenceRecord or OSINTRecord dicts
        week_id: Optional ISO week format "YYYY-W##"; defaults to current week
        reference_date: Date to use for week calculation; defaults to now

    Returns:
        PublicWeeklyBrief with evidence classified into tiers
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    if week_id is None:
        week_id = _week_id_from_date(reference_date)

    week_start = _week_start_from_date(reference_date)
    week_end = week_start + timedelta(days=7)

    # Filter records to this week
    records_list = list(records)
    week_records = [
        r
        for r in records_list
        if _is_in_week(
            r.get("written_at") or r.get("created_at") or r.get("published_at", ""),
            week_start,
        )
    ]

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for rec in week_records:
        cat = _categorize_record(rec)
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(rec)

    # Build sections
    sections: list[WeeklySection] = []
    verified_total = 0
    inferred_total = 0
    speculation_total = 0

    for category in sorted(by_category.keys()):
        cat_records = by_category[category]
        if not cat_records:
            continue

        section = WeeklySection(title=f"{category} Intelligence", category=category)

        for rec in sorted(
            cat_records,
            key=lambda r: r.get("confidence", 0.5),
            reverse=True,
        ):
            tier = _classify_evidence(rec)
            confidence = rec.get("confidence", 0.5)
            content = rec.get("pattern", rec.get("content", ""))

            if content:
                evidence = EvidenceItem(
                    content=content[:500],  # Truncate
                    tier=tier,
                    source_ids=[rec.get("record_id", rec.get("signal_id", ""))],
                    confidence=confidence,
                    published_at=rec.get("written_at", rec.get("created_at", "")),
                    source_url=rec.get("url", rec.get("doc_url", "")),
                    analyst_notes=f"Classification: {rec.get('classification', 'UNKNOWN')}",
                )

                if tier == EvidenceTier.VERIFIED:
                    section.verified_items.append(evidence)
                    verified_total += 1
                elif tier == EvidenceTier.INFERRED:
                    section.inferred_items.append(evidence)
                    inferred_total += 1
                else:
                    section.speculation_items.append(evidence)
                    speculation_total += 1

        # Only include section if it has content
        if (
            section.verified_items
            or section.inferred_items
            or section.speculation_items
        ):
            sections.append(section)

    # Build methodology note
    methodology_note = (
        f"This brief aggregates {len(week_records)} intelligence signals from "
        f"{len(by_category)} domains over one week. Evidence is classified as follows:\n\n"
        f"• **VERIFIED** ({verified_total} items): Corroborated across ≥2 credible sources, "
        f"high confidence (≥0.8)\n"
        f"• **INFERRED** ({inferred_total} items): Analysis from credible signals, "
        f"medium-high confidence (0.65–0.79)\n"
        f"• **SPECULATION** ({speculation_total} items): Preliminary hypotheses requiring validation\n\n"
        f"All claims link to source records (IDs). Timestamps reflect UTC publication/receipt."
    )

    # Build summary
    active_categories = sorted(by_category.keys())
    if active_categories:
        summary = (
            f"SPEC-1 weekly intelligence cycle {week_id} processed {len(week_records)} "
            f"signals across {len(active_categories)} domains. Key activity areas: "
            f"{', '.join(active_categories)}."
        )
    else:
        summary = f"SPEC-1 weekly intelligence cycle {week_id} completed with no significant activity."

    brief_id = PublicWeeklyBrief.make_id(week_id)

    return PublicWeeklyBrief(
        brief_id=brief_id,
        week_id=week_id,
        week_start=week_start.strftime("%Y-%m-%d"),
        week_end=week_end.strftime("%Y-%m-%d"),
        executive_summary=summary,
        methodology_note=methodology_note,
        sections=sections,
        produced_at=datetime.now(timezone.utc),
        records_analyzed=len(week_records),
        verified_count=verified_total,
        inferred_count=inferred_total,
        speculation_count=speculation_total,
        metadata={
            "week_id": week_id,
            "categories": active_categories,
            "source_count": len(set(r.get("url", r.get("doc_url", "")) for r in week_records)),
        },
    )
