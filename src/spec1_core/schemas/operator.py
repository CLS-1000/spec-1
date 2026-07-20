# @domain:   machine
# @module:   schemas_operator
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Operator structured output schema.

Every signal evaluation produces one OperatorOutput — no free-text verdicts.
Every field is queryable and comparable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Verdict values — also exported from spec1_labels
OPERATOR_VERDICT_ESCALATE = "ESCALATE"
OPERATOR_VERDICT_ARCHIVE  = "ARCHIVE"
OPERATOR_VERDICT_HOLD     = "HOLD"

OPERATOR_GATE_THRESHOLD: float = 0.40


@dataclass
class SignalSummary:
    description: str  # first 200 chars of cleaned text
    source: str
    timestamp: str   # ISO8601


@dataclass
class EvidenceQuality:
    """Pass 1 — source reliability and corroborating data volume."""
    credibility_score: float  # 0.0–1.0
    volume_score: float       # 0.0–1.0
    notes: str                # why these scores

    def to_dict(self) -> dict:
        return {
            "credibility_score": self.credibility_score,
            "volume_score": self.volume_score,
            "notes": self.notes,
        }


@dataclass
class DeviationStrength:
    """Pass 2 — speed and precedent of the observed deviation."""
    baseline_pattern: str      # what's normal, with timeframe/source
    anti_pattern_observed: str # what specifically broke from that baseline
    velocity_score: float      # 0.0–1.0
    novelty_score: float       # 0.0–1.0
    deviation_magnitude: str   # e.g. "3x normal rate, 72hrs vs typical 1–2wk"

    def to_dict(self) -> dict:
        return {
            "baseline_pattern": self.baseline_pattern,
            "anti_pattern_observed": self.anti_pattern_observed,
            "velocity_score": self.velocity_score,
            "novelty_score": self.novelty_score,
            "deviation_magnitude": self.deviation_magnitude,
        }


@dataclass
class BeneficiaryCandidate:
    candidate: Optional[str]  # entity name, or null
    evidence: Optional[str]   # financial disclosures, contracts, etc.

    def to_dict(self) -> dict:
        return {"candidate": self.candidate, "evidence": self.evidence}


@dataclass
class BeneficiaryAnalysis:
    """Pass 3 — who benefits from this deviation."""
    material_beneficiary: BeneficiaryCandidate
    power_beneficiary: BeneficiaryCandidate
    hypothesis_strength: float  # 0.0–1.0

    def to_dict(self) -> dict:
        return {
            "material_beneficiary": self.material_beneficiary.to_dict(),
            "power_beneficiary": self.power_beneficiary.to_dict(),
            "hypothesis_strength": self.hypothesis_strength,
        }


@dataclass
class CompositeScore:
    """Gate score (Pass 1+2 only) plus Pass 3 corroboration flag."""
    gate_score: float          # 0.0–1.0, 30/20/20/30 weighting
    beneficiary_supported: bool  # does Pass 3 corroborate the gate score?

    def to_dict(self) -> dict:
        return {
            "gate_score": self.gate_score,
            "beneficiary_supported": self.beneficiary_supported,
        }


@dataclass
class OperatorOutput:
    """Fully structured operator evaluation — every field is queryable across runs."""

    run_id: str
    signal: SignalSummary
    pass_1_evidence_quality: EvidenceQuality
    pass_2_deviation_strength: DeviationStrength
    # None when gate_score <= OPERATOR_GATE_THRESHOLD — Pass 3 skipped
    pass_3_beneficiary: Optional[BeneficiaryAnalysis]
    composite: CompositeScore
    verdict: str          # ESCALATE | ARCHIVE | HOLD
    confidence: float     # 0.0–1.0
    hold_reason: Optional[str]  # required when verdict == HOLD
    reasoning_log: str    # chain: pattern → anti-pattern → beneficiary → verdict

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "signal": {
                "description": self.signal.description,
                "source": self.signal.source,
                "timestamp": self.signal.timestamp,
            },
            "pass_1_evidence_quality": self.pass_1_evidence_quality.to_dict(),
            "pass_2_deviation_strength": self.pass_2_deviation_strength.to_dict(),
            "pass_3_beneficiary": (
                self.pass_3_beneficiary.to_dict() if self.pass_3_beneficiary else None
            ),
            "composite": self.composite.to_dict(),
            "verdict": self.verdict,
            "confidence": self.confidence,
            "hold_reason": self.hold_reason,
            "reasoning_log": self.reasoning_log,
        }
