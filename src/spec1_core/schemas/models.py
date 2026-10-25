# @domain:   machine
# @module:   schemas_models
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Data models for SPEC-1 Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from spec1_labels import ANALYSIS_TIER_RULE_BASED


@dataclass
class Signal:
    """Raw signal harvested from an RSS feed."""

    signal_id: str
    source: str
    source_type: str
    text: str
    url: str
    author: str
    published_at: datetime
    velocity: float
    engagement: float
    run_id: str
    environment: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "signal_id": self.signal_id,
            "source": self.source,
            "source_type": self.source_type,
            "text": self.text,
            "url": self.url,
            "author": self.author,
            "published_at": self.published_at.isoformat() if isinstance(self.published_at, datetime) else str(self.published_at),
            "velocity": self.velocity,
            "engagement": self.engagement,
            "run_id": self.run_id,
            "environment": self.environment,
            "metadata": self.metadata,
        }
        return d


@dataclass
class ParsedSignal:
    """Signal after HTML cleaning and keyword extraction."""

    signal_id: str
    cleaned_text: str
    keywords: list[str]
    entities: list[str]
    language: str
    word_count: int

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "cleaned_text": self.cleaned_text,
            "keywords": self.keywords,
            "entities": self.entities,
            "language": self.language,
            "word_count": self.word_count,
        }


@dataclass
class Opportunity:
    """Signal that has passed all 4 scoring gates."""

    opportunity_id: str
    signal_id: str
    score: float
    priority: str  # "ELEVATED" | "STANDARD" | "MONITOR"
    gate_results: dict  # {"credibility": bool, "volume": bool, "velocity": bool, "novelty": bool}
    run_id: str

    def to_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "signal_id": self.signal_id,
            "score": self.score,
            "priority": self.priority,
            "gate_results": self.gate_results,
            "run_id": self.run_id,
        }


@dataclass
class Investigation:
    """Investigation generated for an opportunity."""

    investigation_id: str
    opportunity_id: str
    hypothesis: str
    queries: list[str]
    sources_to_check: list[str]
    analyst_leads: list[str]

    def to_dict(self) -> dict:
        return {
            "investigation_id": self.investigation_id,
            "opportunity_id": self.opportunity_id,
            "hypothesis": self.hypothesis,
            "queries": self.queries,
            "sources_to_check": self.sources_to_check,
            "analyst_leads": self.analyst_leads,
        }


@dataclass
class Outcome:
    """Outcome of verifying an investigation."""

    outcome_id: str
    classification: str  # "CORROBORATED" | "ESCALATE" | "INVESTIGATE" | "MONITOR" | "CONFLICTED" | "ARCHIVE"
    confidence: float
    evidence: list[str]
    # How the classification was produced; see spec1_labels.ANALYSIS_TIER_*.
    # Defaults to rule-based so nothing is ever mistaken for model output.
    analysis_tier: str = ANALYSIS_TIER_RULE_BASED

    def to_dict(self) -> dict:
        return {
            "outcome_id": self.outcome_id,
            "classification": self.classification,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "analysis_tier": self.analysis_tier,
        }


@dataclass
class IntelligenceRecord:
    """Analyzed intelligence record ready for storage."""

    record_id: str
    pattern: str
    classification: str
    confidence: float
    source_weight: float
    analyst_weight: float

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "pattern": self.pattern,
            "classification": self.classification,
            "confidence": self.confidence,
            "source_weight": self.source_weight,
            "analyst_weight": self.analyst_weight,
        }


@dataclass
class AnalystRecord:
    """Known analyst record."""

    analyst_id: str
    name: str
    affiliation: str
    domains: list[str]
    credibility_score: float

    def to_dict(self) -> dict:
        return {
            "analyst_id": self.analyst_id,
            "name": self.name,
            "affiliation": self.affiliation,
            "domains": self.domains,
            "credibility_score": self.credibility_score,
        }


@dataclass
class CaseFile:
    """Persistent investigation case that accumulates evidence across cycles."""

    case_id: str
    title: str
    question: str
    tags: list[str] = field(default_factory=list)
    status: str = "OPEN"  # OPEN | CLOSED | WATCHING
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_ids: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    research_runs: int = 0
    confidence: float = 0.5
    run_id: str = ""
    environment: str = "osint"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "question": self.question,
            "tags": self.tags,
            "status": self.status,
            "opened_at": self.opened_at.isoformat() if isinstance(self.opened_at, datetime) else str(self.opened_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
            "signal_ids": self.signal_ids,
            "findings": self.findings,
            "research_runs": self.research_runs,
            "confidence": self.confidence,
            "run_id": self.run_id,
            "environment": self.environment,
            "metadata": self.metadata,
        }

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class DeterministicScoreVerification(BaseModel):
    credibility_pass: bool = Field(description="Gate A: Source authority and signature validation")
    volume_pass: bool = Field(description="Gate B: Cross-source confirmation volume check")
    velocity_pass: bool = Field(description="Gate C: Acceleration and transmission rate threshold")
    novelty_pass: bool = Field(description="Gate D: Lexical and conceptual distance from baseline")


class Tier3TriageVerdict(BaseModel):
    record_id: str = Field(description="Canonical record identifier being audited")
    analysis_tier: Literal["llm_verified", "rule_based"] = Field(
        description="Required by migration 011: only llm_verified unlocks publish guard"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Evaluated confidence score between 0.0 and 1.0")
    classification: str = Field(description="Primary domain classification")
    gate_checks: DeterministicScoreVerification
    justification: str = Field(max_length=500, description="Concise rationale for verification")
    flags: List[str] = Field(default_factory=list, description="Audit flags: TIER_1, RETRACTED, ANOMALOUS")
