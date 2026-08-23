# @domain:   publisher
# @module:   cls_weekly_brief_schemas
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Schemas for public weekly SPEC-1 intelligence brief."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal


class EvidenceTier(str, Enum):
    """Classification of evidence quality for public brief."""

    VERIFIED = "VERIFIED"  # Corroborated across ≥2 credible sources, high confidence
    INFERRED = "INFERRED"  # Analysis from credible signals, medium-high confidence
    SPECULATION = "SPECULATION"  # Preliminary hypothesis, requires validation


@dataclass
class EvidenceItem:
    """A single piece of evidence with classification and source attribution."""

    content: str
    tier: EvidenceTier
    source_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    published_at: str = ""
    source_url: str = ""
    analyst_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "tier": self.tier.value,
            "source_ids": self.source_ids,
            "confidence": self.confidence,
            "published_at": self.published_at,
            "source_url": self.source_url,
            "analyst_notes": self.analyst_notes,
        }


@dataclass
class WeeklySection:
    """A named section in the weekly brief with evidence items."""

    title: str
    category: str  # e.g. "MILITARY", "CYBER", "GEOPOLITICAL", "FARA", "PSYOP"
    verified_items: list[EvidenceItem] = field(default_factory=list)
    inferred_items: list[EvidenceItem] = field(default_factory=list)
    speculation_items: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "category": self.category,
            "verified_items": [item.to_dict() for item in self.verified_items],
            "inferred_items": [item.to_dict() for item in self.inferred_items],
            "speculation_items": [item.to_dict() for item in self.speculation_items],
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PublicWeeklyBrief:
    """Public-facing weekly intelligence brief with evidence-linked provenance."""

    brief_id: str
    week_id: str  # ISO week format: "YYYY-W##"
    week_start: str  # ISO date "YYYY-MM-DD"
    week_end: str  # ISO date "YYYY-MM-DD"
    executive_summary: str
    methodology_note: str
    sections: list[WeeklySection] = field(default_factory=list)
    produced_at: datetime = field(default_factory=_now)
    records_analyzed: int = 0
    verified_count: int = 0
    inferred_count: int = 0
    speculation_count: int = 0
    metadata: dict = field(default_factory=dict)

    @classmethod
    def make_id(cls, week_id: str) -> str:
        """Generate stable brief ID from week."""
        raw = f"weekly_{week_id}"
        return "pwb_" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "brief_id": self.brief_id,
            "week_id": self.week_id,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "executive_summary": self.executive_summary,
            "methodology_note": self.methodology_note,
            "sections": [s.to_dict() for s in self.sections],
            "produced_at": self.produced_at.isoformat()
            if isinstance(self.produced_at, datetime)
            else str(self.produced_at),
            "records_analyzed": self.records_analyzed,
            "verified_count": self.verified_count,
            "inferred_count": self.inferred_count,
            "speculation_count": self.speculation_count,
            "metadata": self.metadata,
        }
