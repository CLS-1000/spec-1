# @domain:   citizens_source
# @module:   models
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Core data models for cls_pdx1 (PDX-1i).

Uses Pydantic v2 throughout — API-safe and schema-exportable.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_id(prefix: str, *parts: str) -> str:
    raw = ":".join(str(p) for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ConfidenceTier(IntEnum):
    """Evidence quality tier. Governs corroboration requirements."""

    HARD_RECORD = 1   # Public record: donation, contract, board seat, court filing
    REPORTED = 2      # Credible news/journalism with byline
    INFERRED = 3      # Statistical or NLP inference; effectively unpublishable alone


class EdgeType(IntEnum):
    """Type of affiliation edge between an official and an entity."""

    DONATION = 1        # Campaign contribution
    BOARD_SEAT = 2      # Directorship or advisory position
    CONTRACT = 3        # Public contract award
    LOBBYING = 4        # Registered lobbying relationship
    EMPLOYMENT = 5      # Former or current employer
    CO_MENTION = 6      # News co-mention (soft; ConfidenceTier.INFERRED)
    ENDORSEMENT = 7     # Formal endorsement
    FAMILY_TIE = 8      # Disclosed family / household relationship


class AnomalyTier(IntEnum):
    """Severity tier for detected anomalies. TIER_1 is highest."""

    TIER_1 = 1   # >= 3 sigma above baseline; publish-eligible
    TIER_2 = 2   # >= 2 sigma; publish-eligible
    TIER_3 = 3   # >= 1 sigma; log, do not publish
    TIER_4 = 4   # < 1 sigma; routine noise


class BillStatus(IntEnum):
    """Legislative bill lifecycle states."""

    INTRODUCED = 1
    IN_COMMITTEE = 2
    PASSED_COMMITTEE = 3
    PASSED_ONE_CHAMBER = 4
    PASSED_BOTH_CHAMBERS = 5
    ENROLLED = 6
    SIGNED = 7
    VETOED = 8
    OVERRIDDEN = 9
    FAILED = 10
    DEAD = 11


class Jurisdiction(IntEnum):
    """Jurisdictional scope of an official, district, or bill."""

    CITY_PORTLAND = 1
    CITY_VANCOUVER = 2
    MULTNOMAH_COUNTY = 3
    WASHINGTON_COUNTY = 4
    CLACKAMAS_COUNTY = 5
    CLARK_COUNTY_WA = 6
    METRO = 7
    STATE_OREGON = 8
    STATE_WASHINGTON = 9
    FEDERAL = 10


class Sector(IntEnum):
    """Industry/sector tags for entities."""

    REAL_ESTATE = 1
    SOFTWARE = 2
    CONSTRUCTION = 3
    UTILITY = 4
    TRANSIT = 5
    HEALTHCARE = 6
    FINANCE = 7
    LEGAL = 8
    MEDIA = 9
    EDUCATION = 10
    GOVERNMENT = 11
    NONPROFIT = 12
    LABOR = 13
    RETAIL = 14
    ENERGY = 15


# ---------------------------------------------------------------------------
# Core record types
# ---------------------------------------------------------------------------


class Provenance(BaseModel):
    """Source attribution for every record. Required; no record enters without it."""

    source_uri: str
    source_name: str
    fetched_at: datetime
    notes: Optional[str] = None


class District(BaseModel):
    """An electoral or administrative district."""

    district_id: str
    name: str
    jurisdiction: Jurisdiction
    district_type: str   # "city_council" | "county_commission" | "state_house" | etc.
    current_holder: Optional[str] = None   # official_id

    @classmethod
    def make_id(cls, jurisdiction: Jurisdiction, district_type: str, name: str) -> str:
        return _make_id("district", str(int(jurisdiction)), district_type, name)


class Official(BaseModel):
    """An elected or appointed official in the Portland metro."""

    official_id: str
    name: str
    role: str                              # "Mayor" | "Commissioner" | "State Rep" | etc.
    jurisdiction: Jurisdiction
    district_id: Optional[str] = None
    term_start: Optional[date] = None
    term_end: Optional[date] = None
    status: str = "active"                 # "active" | "former" | "appointed"
    party: Optional[str] = None
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, name: str, role: str, jurisdiction: Jurisdiction) -> str:
        return _make_id("official", name, role, str(int(jurisdiction)))


class Entity(BaseModel):
    """A company, family network, agency, nonprofit, or PAC."""

    entity_id: str
    canonical_name: str
    kind: str                              # "company" | "family" | "agency" | "nonprofit" | "pac"
    sectors: list[Sector] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    parent_id: Optional[str] = None       # parent entity_id for subsidiaries
    jurisdiction: Optional[Jurisdiction] = None
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, canonical_name: str) -> str:
        return _make_id("entity", canonical_name)


class Affiliation(BaseModel):
    """An edge between an official and an entity. Every edge is time-bounded."""

    affiliation_id: str = ""
    official_id: str
    entity_id: str
    edge_type: EdgeType
    confidence: ConfidenceTier
    observed_at: datetime
    valid_from: date
    valid_to: Optional[date] = None        # None = open-ended / still active
    amount: Optional[float] = None         # dollars, for donations/contracts
    description: Optional[str] = None
    provenance: Provenance
    corroborating_uris: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.affiliation_id:
            object.__setattr__(
                self,
                "affiliation_id",
                _make_id(
                    "aff",
                    self.official_id,
                    self.entity_id,
                    str(int(self.edge_type)),
                    self.valid_from.isoformat(),
                ),
            )


class Bill(BaseModel):
    """A tracked legislative bill or ordinance."""

    bill_id: str
    external_id: str                       # e.g. "HB 1234" or "Ordinance 192345"
    title: str
    jurisdiction: Jurisdiction
    chamber: str                           # "House" | "Senate" | "City Council" | "County"
    sponsor: Optional[str] = None          # official_id
    co_sponsors: list[str] = Field(default_factory=list)
    status: BillStatus = BillStatus.INTRODUCED
    plain_summary: Optional[str] = None    # LLM-generated, neutrality-gated
    introduced_at: Optional[date] = None
    last_action_at: Optional[date] = None
    next_hearing_at: Optional[datetime] = None
    source_url: str
    tags: list[str] = Field(default_factory=list)
    entity_mentions: list[str] = Field(default_factory=list)   # entity_ids mentioned
    provenance: Provenance
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, jurisdiction: Jurisdiction, external_id: str) -> str:
        return _make_id("bill", str(int(jurisdiction)), external_id)


class Signal(BaseModel):
    """A discrete event that may trigger further analysis or publication."""

    signal_id: str = ""
    kind: str            # "donation_made" | "bill_state_change" | "board_appointment" | etc.
    occurred_at: datetime
    detected_at: datetime
    official_id: Optional[str] = None
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
                _make_id("sig", self.kind, self.occurred_at.isoformat()),
            )


class Anomaly(BaseModel):
    """A statistically significant deviation from entity baseline."""

    anomaly_id: str = ""
    entity_id: str
    tier: AnomalyTier
    detected_at: datetime
    kind: str                              # "donation_spike" | "contract_surge" | "lobbying_new" | etc.
    description: str
    baseline_window_days: int = 90
    sigma: Optional[float] = None
    observed_value: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    provenance: Provenance
    signal_ids: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.anomaly_id:
            object.__setattr__(
                self,
                "anomaly_id",
                _make_id("anom", self.entity_id, self.kind, self.detected_at.isoformat()),
            )


class IssueSection(BaseModel):
    """A single section within a Metro Citizens Brief issue."""

    title: str
    body: str
    source_uri: str
    section_type: str = "narrative"    # "narrative" | "legislation" | "anomaly" | "watchlist"
    entity_ids: list[str] = Field(default_factory=list)
    official_ids: list[str] = Field(default_factory=list)
    bill_ids: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    """A published Metro Citizens Brief issue."""

    issue_id: str
    issue_number: int
    title: str
    published_at: datetime
    sections: list[IssueSection] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    anomaly_ids: list[str] = Field(default_factory=list)
    diagram_path: Optional[str] = None    # path to static diagram asset
    pdf_path: Optional[str] = None
    markdown_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def make_id(cls, issue_number: int, published_at: datetime) -> str:
        return _make_id("issue", str(issue_number), published_at.isoformat()[:10])
