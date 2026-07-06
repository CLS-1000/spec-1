# @domain:   product
# @module:   conviction
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain.schemas, spec1_labels

"""Layer 2: Conviction Scorer.

Quantifies how convicted a founder should be about a signal/opportunity.
This is NOT confidence in the data — it's confidence in the DECISION.

The exited-founder heuristic:
  - When downside_asymmetry is high (cheap to be wrong, expensive to miss)
    AND time_decay is high (window closing fast) → conviction spikes
  - This is the "act now, correct later" pattern that separates exited
    founders from analytical paralysis

Scoring formula:
  base = weighted_mean(clarity, market_val, gut_alignment)
  urgency_multiplier = 1 + (downside_asymmetry * time_decay * 0.5)
  conviction = min(1.0, base * urgency_multiplier)

No LLM required — purely deterministic scoring.
"""

from __future__ import annotations

from spec1_labels import (
    FOUNDER_CONVICTION_HIGH,
    FOUNDER_CONVICTION_MEDIUM,
    FOUNDER_CONVICTION_LOW,
    FOUNDER_CONVICTION_NOISE,
)

from cls_founder_brain.schemas import ConvictionSignal, PatternMatch


# Weights: exited founders weight gut_alignment heavily when backed by pattern matches
_W_CLARITY = 0.20
_W_MARKET = 0.25
_W_GUT = 0.30
_W_ASYMMETRY = 0.15
_W_TIME = 0.10


def _compute_conviction_score(
    signal_clarity: float,
    market_validation: float,
    gut_alignment: float,
    downside_asymmetry: float,
    time_decay: float,
) -> float:
    """Core conviction computation — the exited-founder formula.

    Key insight: when downside_asymmetry AND time_decay are both high,
    the urgency multiplier kicks in. This encodes "cheap to try + window
    closing = just do it" which is the #1 exited-founder pattern.
    """
    base = (
        signal_clarity * _W_CLARITY
        + market_validation * _W_MARKET
        + gut_alignment * _W_GUT
        + downside_asymmetry * _W_ASYMMETRY
        + time_decay * _W_TIME
    )

    # Urgency multiplier: compounds when both asymmetry and decay are high
    urgency = 1.0 + (downside_asymmetry * time_decay * 0.5)

    return min(1.0, round(base * urgency, 3))


def _classify_conviction(score: float) -> str:
    """Map numeric score to conviction level."""
    if score >= 0.75:
        return FOUNDER_CONVICTION_HIGH
    elif score >= 0.50:
        return FOUNDER_CONVICTION_MEDIUM
    elif score >= 0.25:
        return FOUNDER_CONVICTION_LOW
    return FOUNDER_CONVICTION_NOISE


def score_conviction(
    signal_id: str,
    signal_description: str,
    signal_clarity: float = 0.5,
    market_validation: float = 0.5,
    gut_alignment: float = 0.5,
    downside_asymmetry: float = 0.5,
    time_decay: float = 0.5,
    pattern_matches: list[PatternMatch] | None = None,
) -> ConvictionSignal:
    """Score conviction for a single signal.

    If pattern_matches are provided, gut_alignment gets boosted by
    the strongest pattern match (exited founders trust pattern recognition).

    Args:
        signal_id: Unique identifier for this signal.
        signal_description: Human-readable description.
        signal_clarity: How unambiguous is the signal (0.0–1.0).
        market_validation: External evidence supporting this (0.0–1.0).
        gut_alignment: Does this feel right based on experience (0.0–1.0).
        downside_asymmetry: Cost of inaction vs cost of action (0.0–1.0).
        time_decay: How fast the window closes (0.0–1.0).
        pattern_matches: Optional Layer 1 output to boost gut_alignment.

    Returns:
        ConvictionSignal with computed score and classification.
    """
    # Boost gut_alignment when strong pattern matches exist
    effective_gut = gut_alignment
    if pattern_matches:
        strongest = max(pm.match_strength for pm in pattern_matches)
        # Pattern recognition = encoded gut feel. Boost proportionally.
        effective_gut = min(1.0, gut_alignment + strongest * 0.3)

    score = _compute_conviction_score(
        signal_clarity=signal_clarity,
        market_validation=market_validation,
        gut_alignment=effective_gut,
        downside_asymmetry=downside_asymmetry,
        time_decay=time_decay,
    )

    level = _classify_conviction(score)

    # Generate rationale
    rationale_parts = []
    if downside_asymmetry >= 0.7 and time_decay >= 0.7:
        rationale_parts.append("High asymmetry + closing window → act now, correct later.")
    if effective_gut >= 0.8:
        rationale_parts.append("Strong pattern-library resonance — this matches exited-founder experience.")
    if market_validation >= 0.7:
        rationale_parts.append("External validation confirms signal.")
    if signal_clarity < 0.3:
        rationale_parts.append("Signal unclear — gather one more data point before committing.")
    if not rationale_parts:
        rationale_parts.append(f"Moderate signal across dimensions. Conviction: {level}.")

    return ConvictionSignal(
        signal_id=signal_id,
        signal_description=signal_description,
        signal_clarity=signal_clarity,
        market_validation=market_validation,
        gut_alignment=effective_gut,
        downside_asymmetry=downside_asymmetry,
        time_decay=time_decay,
        conviction_score=score,
        conviction_level=level,
        rationale=" ".join(rationale_parts),
    )
