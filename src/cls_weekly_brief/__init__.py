# @domain:   publisher
# @module:   cls_weekly_brief
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Public weekly SPEC-1 intelligence brief — aggregates 7 days of verified intelligence."""

from __future__ import annotations

__all__ = [
    "EvidenceTier",
    "EvidenceItem",
    "WeeklySection",
    "PublicWeeklyBrief",
    "produce_weekly_brief",
    "to_markdown",
    "to_json_summary",
    "to_full_json",
    "WeeklyBriefStore",
]

from cls_weekly_brief.schemas import (
    EvidenceTier,
    EvidenceItem,
    WeeklySection,
    PublicWeeklyBrief,
)
from cls_weekly_brief.producer import produce_weekly_brief
from cls_weekly_brief.formatter import to_markdown, to_json_summary, to_full_json
from cls_weekly_brief.store import WeeklyBriefStore
