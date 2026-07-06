# @domain:   product
# @module:   schemas
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_labels

"""Data schemas for cls_founder_brain.

Plain dataclasses with to_dict/from_dict round-trips, no I/O.
Models the cognitive layers of a two-time exited founder's decision process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from spec1_labels import (
    FOUNDER_FIRE_IGNORE,
    FOUNDER_CONVICTION_HIGH,
    FOUNDER_PATTERN_FAILURE,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


# ── Layer 1: Pattern Recognition ──────────────────────────────────────────────


@dataclass
class PatternMatch:
    """A matched failure/success archetype from the founder pattern library.

    pattern_id references the canonical pattern (e.g. 'premature_scaling',
    'founder_market_fit_drift', 'burn_rate_denial'). match_strength is 0.0–1.0.
    evidence_signals lists which inputs triggered the match.
    """

    pattern_id: str
    pattern_name: str
    category: str  # FAILURE | SUCCESS | PIVOT | EXIT_SIGNAL
    match_strength: float  # 0.0 – 1.0
    evidence_signals: list[str] = field(default_factory=list)
    historical_outcome: str = ""  # What happened when founders hit this pattern
    counter_move: str = ""  # What exited founders did differently
    matched_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "category": self.category,
            "match_strength": self.match_strength,
            "evidence_signals": list(self.evidence_signals),
            "historical_outcome": self.historical_outcome,
            "counter_move": self.counter_move,
            "matched_at": _iso(self.matched_at),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PatternMatch":
        return cls(
            pattern_id=d["pattern_id"],
            pattern_name=d["pattern_name"],
            category=d.get("category", FOUNDER_PATTERN_FAILURE),
            match_strength=float(d.get("match_strength", 0.0)),
            evidence_signals=list(d.get("evidence_signals", [])),
            historical_outcome=d.get("historical_outcome", ""),
            counter_move=d.get("counter_move", ""),
            matched_at=_parse_dt(d.get("matched_at")) or _now(),
        )


# ── Layer 2: Conviction Scorer ────────────────────────────────────────────────


@dataclass
class ConvictionSignal:
    """Quantified signal strength under uncertainty.

    Exited founders don't wait for certainty — they act on conviction.
    This scores HOW convicted you should be given:
      - signal_clarity: how unambiguous is the signal (0.0–1.0)
      - market_validation: external evidence (0.0–1.0)
      - gut_alignment: pattern-library resonance (0.0–1.0)
      - downside_asymmetry: cost of being wrong vs right (0.0–1.0)
      - time_decay: how fast the window closes (0.0–1.0)

    conviction_score is the composite — not a simple average but weighted
    by the exited-founder heuristic: downside_asymmetry and time_decay
    dominate when both are high.
    """

    signal_id: str
    signal_description: str
    signal_clarity: float = 0.0
    market_validation: float = 0.0
    gut_alignment: float = 0.0
    downside_asymmetry: float = 0.0
    time_decay: float = 0.0
    conviction_score: float = 0.0
    conviction_level: str = FOUNDER_CONVICTION_HIGH  # HIGH | MEDIUM | LOW | NOISE
    rationale: str = ""
    scored_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "signal_description": self.signal_description,
            "signal_clarity": self.signal_clarity,
            "market_validation": self.market_validation,
            "gut_alignment": self.gut_alignment,
            "downside_asymmetry": self.downside_asymmetry,
            "time_decay": self.time_decay,
            "conviction_score": self.conviction_score,
            "conviction_level": self.conviction_level,
            "rationale": self.rationale,
            "scored_at": _iso(self.scored_at),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConvictionSignal":
        return cls(
            signal_id=d["signal_id"],
            signal_description=d.get("signal_description", ""),
            signal_clarity=float(d.get("signal_clarity", 0.0)),
            market_validation=float(d.get("market_validation", 0.0)),
            gut_alignment=float(d.get("gut_alignment", 0.0)),
            downside_asymmetry=float(d.get("downside_asymmetry", 0.0)),
            time_decay=float(d.get("time_decay", 0.0)),
            conviction_score=float(d.get("conviction_score", 0.0)),
            conviction_level=d.get("conviction_level", FOUNDER_CONVICTION_HIGH),
            rationale=d.get("rationale", ""),
            scored_at=_parse_dt(d.get("scored_at")) or _now(),
        )


# ── Layer 3: Fire Triage ──────────────────────────────────────────────────────


@dataclass
class FireClassification:
    """Classifies a problem as IGNORE / DELEGATE / ATTACK.

    The exited-founder difference: most fires are cosmetic. Only existential
    fires get direct founder attention. The classification uses:
      - existential_score: does this kill the company if unaddressed (0.0–1.0)
      - reversibility: can this be undone later (0.0=irreversible, 1.0=trivial)
      - founder_leverage: does the founder uniquely add value here (0.0–1.0)
      - opportunity_cost: what you DON'T do while fighting this fire (0.0–1.0)
    """

    fire_id: str
    description: str
    existential_score: float = 0.0
    reversibility: float = 1.0
    founder_leverage: float = 0.0
    opportunity_cost: float = 0.0
    classification: str = FOUNDER_FIRE_IGNORE  # IGNORE | DELEGATE | ATTACK
    reasoning: str = ""
    time_to_irreversible: Optional[str] = None  # e.g. "48h", "7d", "never"
    classified_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "fire_id": self.fire_id,
            "description": self.description,
            "existential_score": self.existential_score,
            "reversibility": self.reversibility,
            "founder_leverage": self.founder_leverage,
            "opportunity_cost": self.opportunity_cost,
            "classification": self.classification,
            "reasoning": self.reasoning,
            "time_to_irreversible": self.time_to_irreversible,
            "classified_at": _iso(self.classified_at),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FireClassification":
        return cls(
            fire_id=d["fire_id"],
            description=d.get("description", ""),
            existential_score=float(d.get("existential_score", 0.0)),
            reversibility=float(d.get("reversibility", 1.0)),
            founder_leverage=float(d.get("founder_leverage", 0.0)),
            opportunity_cost=float(d.get("opportunity_cost", 0.0)),
            classification=d.get("classification", FOUNDER_FIRE_IGNORE),
            reasoning=d.get("reasoning", ""),
            time_to_irreversible=d.get("time_to_irreversible"),
            classified_at=_parse_dt(d.get("classified_at")) or _now(),
        )


# ── Layer 4: Decision Synthesizer (Output) ────────────────────────────────────


@dataclass
class Situation:
    """Input: the current state the founder-brain evaluates.

    This is the raw input — what's happening RIGHT NOW that needs
    the exited-founder lens applied to it.
    """

    situation_id: str
    description: str
    context: str = ""  # Market, stage, resources available
    constraints: list[str] = field(default_factory=list)  # e.g. ["$0 budget", "7 days"]
    active_fires: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)  # Opportunities, threats, data points
    stage: str = "pre_revenue"  # pre_revenue | revenue | scaling | exit_prep
    runway_days: int = 7
    created_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "situation_id": self.situation_id,
            "description": self.description,
            "context": self.context,
            "constraints": list(self.constraints),
            "active_fires": list(self.active_fires),
            "signals": list(self.signals),
            "stage": self.stage,
            "runway_days": self.runway_days,
            "created_at": _iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Situation":
        return cls(
            situation_id=d["situation_id"],
            description=d.get("description", ""),
            context=d.get("context", ""),
            constraints=list(d.get("constraints", [])),
            active_fires=list(d.get("active_fires", [])),
            signals=list(d.get("signals", [])),
            stage=d.get("stage", "pre_revenue"),
            runway_days=int(d.get("runway_days", 7)),
            created_at=_parse_dt(d.get("created_at")) or _now(),
        )


@dataclass
class FounderDecision:
    """Output: the synthesized executive decision.

    Combines all four layers into a single actionable output:
      - What patterns are active (Layer 1)
      - What conviction level exists (Layer 2)
      - Which fires to ignore (Layer 3)
      - What to DO in the next 24–168 hours (synthesis)
    """

    decision_id: str
    situation_id: str
    # Layer outputs
    pattern_matches: list[dict] = field(default_factory=list)
    conviction_signals: list[dict] = field(default_factory=list)
    fire_classifications: list[dict] = field(default_factory=list)
    # Synthesis
    primary_action: str = ""  # The ONE thing to do
    action_rationale: str = ""
    ignore_list: list[str] = field(default_factory=list)  # Fires explicitly ignored
    conviction_level: str = FOUNDER_CONVICTION_HIGH
    time_horizon_hours: int = 168  # Default 7 days
    confidence: float = 0.0
    # Meta
    cognitive_model: str = "exited_founder_v1"
    generated_at: datetime = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "situation_id": self.situation_id,
            "pattern_matches": self.pattern_matches,
            "conviction_signals": self.conviction_signals,
            "fire_classifications": self.fire_classifications,
            "primary_action": self.primary_action,
            "action_rationale": self.action_rationale,
            "ignore_list": list(self.ignore_list),
            "conviction_level": self.conviction_level,
            "time_horizon_hours": self.time_horizon_hours,
            "confidence": self.confidence,
            "cognitive_model": self.cognitive_model,
            "generated_at": _iso(self.generated_at),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FounderDecision":
        return cls(
            decision_id=d["decision_id"],
            situation_id=d["situation_id"],
            pattern_matches=list(d.get("pattern_matches", [])),
            conviction_signals=list(d.get("conviction_signals", [])),
            fire_classifications=list(d.get("fire_classifications", [])),
            primary_action=d.get("primary_action", ""),
            action_rationale=d.get("action_rationale", ""),
            ignore_list=list(d.get("ignore_list", [])),
            conviction_level=d.get("conviction_level", FOUNDER_CONVICTION_HIGH),
            time_horizon_hours=int(d.get("time_horizon_hours", 168)),
            confidence=float(d.get("confidence", 0.0)),
            cognitive_model=d.get("cognitive_model", "exited_founder_v1"),
            generated_at=_parse_dt(d.get("generated_at")) or _now(),
        )
