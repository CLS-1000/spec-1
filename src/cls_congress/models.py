from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_id(prefix: str, *parts: str) -> str:
    raw = ":".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


class ConfidenceTier(IntEnum):
    HARD_RECORD = 1
    REPORTED = 2
    INFERRED = 3


class EdgeType(IntEnum):
    DONATION = 1
    LOBBYING = 2
    EMPLOYMENT = 3
    BOARD_SEAT = 4
    POLICY_ALIGNMENT = 5


class AnomalyTier(IntEnum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


class Chamber(IntEnum):
    HOUSE = 1
    SENATE = 2


class BillStatus(IntEnum):
    INTRODUCED = 1
    PASSED_HOUSE = 2
    PASSED_SENATE = 3
    ENACTED = 4
    FAILED = 5


class Provenance(BaseModel):
    source_uri: str
    source_name: str
    fetched_at: datetime
    notes: Optional[str] = None


class Member(BaseModel):
    member_id: str
    name: str
    chamber: Chamber
    state: str
    district: Optional[str] = None
    committees: list[str] = Field(default_factory=list)
    party: Optional[str] = None
    term_start: Optional[date] = None
    term_end: Optional[date] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, name: str, chamber: Chamber, state: str, district: Optional[str]) -> str:
        return _make_id("member", name, str(int(chamber)), state, district or "")


class Entity(BaseModel):
    entity_id: str
    canonical_name: str
    kind: str
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, canonical_name: str) -> str:
        return _make_id("entity", canonical_name)


class Affiliation(BaseModel):
    affiliation_id: str = ""
    member_id: str
    entity_id: str
    edge_type: EdgeType
    confidence: ConfidenceTier
    observed_at: datetime
    valid_from: date
    valid_to: Optional[date] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.affiliation_id:
            object.__setattr__(
                self,
                "affiliation_id",
                _make_id(
                    "aff",
                    self.member_id,
                    self.entity_id,
                    str(int(self.edge_type)),
                    self.valid_from.isoformat(),
                ),
            )


class Bill(BaseModel):
    bill_id: str
    external_id: str
    title: str
    chamber: Chamber
    sponsor_id: Optional[str] = None
    status: BillStatus = BillStatus.INTRODUCED
    introduced_at: Optional[date] = None
    last_action_at: Optional[date] = None
    source_url: str
    stated_purpose: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, external_id: str, chamber: Chamber) -> str:
        return _make_id("bill", external_id, str(int(chamber)))


class Signal(BaseModel):
    signal_id: str = ""
    kind: str
    occurred_at: datetime
    detected_at: datetime
    member_id: Optional[str] = None
    entity_id: Optional[str] = None
    bill_id: Optional[str] = None
    weight: float = 1.0
    description: Optional[str] = None
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.signal_id:
            object.__setattr__(
                self,
                "signal_id",
                _make_id("sig", self.kind, self.occurred_at.isoformat(), self.member_id or "", self.entity_id or ""),
            )


class Anomaly(BaseModel):
    anomaly_id: str = ""
    entity_id: str
    tier: AnomalyTier
    detected_at: datetime
    kind: str
    description: str
    baseline_window_days: int = 90
    sigma: Optional[float] = None
    observed_value: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    provenance: Provenance

    def model_post_init(self, __context: Any) -> None:
        if not self.anomaly_id:
            object.__setattr__(
                self,
                "anomaly_id",
                _make_id("anom", self.entity_id, self.kind, self.detected_at.isoformat()),
            )


class IssueSection(BaseModel):
    title: str
    body: str
    section_type: str
    source_uri: str
    member_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    bill_ids: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    issue_id: str
    issue_number: int
    title: str
    published_at: datetime
    sections: list[IssueSection] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    anomaly_ids: list[str] = Field(default_factory=list)

    @classmethod
    def make_id(cls, issue_number: int, published_at: datetime) -> str:
        return _make_id("issue", str(issue_number), published_at.date().isoformat())


class MemberRegistry:
    def __init__(self, seed_path: Optional[Path] = None) -> None:
        self._seed_path = seed_path or Path(__file__).parent / "data" / "officials_seed.json"
        self._members: list[Member] = []
        self._members_by_id: dict[str, Member] = {}

    def load(self) -> list[Member]:
        if not self._seed_path.exists():
            self._members = []
            self._members_by_id = {}
            return []

        rows = json.loads(self._seed_path.read_text(encoding="utf-8"))
        members: list[Member] = []
        for row in rows:
            raw_chamber = str(row.get("chamber", "HOUSE")).upper()
            chamber = {"HOUSE": Chamber.HOUSE, "SENATE": Chamber.SENATE}.get(raw_chamber)
            if chamber is None:
                continue
            member_id = row.get("member_id") or Member.make_id(
                row.get("name", "Unknown"),
                chamber,
                row.get("state", "NA"),
                row.get("district"),
            )
            members.append(
                Member(
                    member_id=member_id,
                    name=row.get("name", "Unknown"),
                    chamber=chamber,
                    state=row.get("state", ""),
                    district=row.get("district"),
                    committees=row.get("committees", []),
                    party=row.get("party"),
                    term_start=date.fromisoformat(row["term_start"]) if row.get("term_start") else None,
                    term_end=date.fromisoformat(row["term_end"]) if row.get("term_end") else None,
                    metadata=row.get("metadata", {}),
                )
            )

        self._members = members
        self._members_by_id = {m.member_id: m for m in members}
        return members

    def members(self) -> list[Member]:
        return list(self._members)

    def get(self, member_id: str) -> Optional[Member]:
        return self._members_by_id.get(member_id)

    def find(
        self,
        *,
        name: Optional[str] = None,
        chamber: Optional[Chamber] = None,
        state: Optional[str] = None,
    ) -> list[Member]:
        records = self._members
        if name:
            lowered = name.lower()
            records = [m for m in records if lowered in m.name.lower()]
        if chamber:
            records = [m for m in records if m.chamber == chamber]
        if state:
            records = [m for m in records if m.state.upper() == state.upper()]
        return records
