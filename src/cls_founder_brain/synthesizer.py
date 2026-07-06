# @domain:   product
# @module:   synthesizer
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain.schemas

"""Layer 4: Decision Synthesizer.

Combines outputs from all three layers into a single executive decision.
This is the "so what do I DO" layer.

The exited-founder synthesis rules:
  1. If ANY pattern matches EXIT_SIGNAL with strength >= 0.4 → primary action is explore exit
  2. If fire triage has ATTACK items → primary action addresses the top ATTACK fire
  3. If conviction is HIGH on any signal → primary action exploits that signal
  4. Otherwise → primary action is "prove one thing" (de-risk with smallest possible test)

The output is ONE action + ignore list. Exited founders never have 5 priorities.
They have 1 priority and a list of things they're explicitly NOT doing.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from spec1_labels import (
    FOUNDER_CONVICTION_HIGH,
    FOUNDER_FIRE_ATTACK,
    FOUNDER_FIRE_IGNORE,
    FOUNDER_PATTERN_EXIT_SIGNAL,
)

from cls_founder_brain.schemas import (
    ConvictionSignal,
    FireClassification,
    FounderDecision,
    PatternMatch,
    Situation,
)


def _generate_decision_id(situation_id: str) -> str:
    """Generate a unique (time-based) decision ID from a situation ID."""
    ts = datetime.now(timezone.utc).isoformat()
    raw = f"{situation_id}_{ts}"
    return f"fd_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def synthesize_decision(
    situation: Situation,
    pattern_matches: list[PatternMatch],
    conviction_signals: list[ConvictionSignal],
    fire_classifications: list[FireClassification],
) -> FounderDecision:
    """Synthesize all layers into a single executive decision.

    The synthesis priority stack (exited-founder order):
      1. Exit signals (don't miss an exit window)
      2. Existential fires (don't die)
      3. High-conviction opportunities (act on pull)
      4. Default: prove one thing (de-risk)

    Returns:
        FounderDecision with primary_action and ignore_list.
    """
    decision_id = _generate_decision_id(situation.situation_id)

    # Collect the ignore list (fires classified as IGNORE)
    ignore_list = [
        f.description for f in fire_classifications
        if f.classification == FOUNDER_FIRE_IGNORE
    ]

    # Attack fires
    attack_fires = [
        f for f in fire_classifications
        if f.classification == FOUNDER_FIRE_ATTACK
    ]

    # High-conviction signals
    high_conviction = [
        cs for cs in conviction_signals
        if cs.conviction_level == FOUNDER_CONVICTION_HIGH
    ]

    # Exit signals
    exit_patterns = [
        pm for pm in pattern_matches
        if pm.category == FOUNDER_PATTERN_EXIT_SIGNAL and pm.match_strength >= 0.4
    ]

    # ── Synthesis decision tree ──
    primary_action = ""
    action_rationale = ""
    conviction_level = FOUNDER_CONVICTION_HIGH
    time_horizon = situation.runway_days * 24  # Convert to hours
    confidence = 0.0

    if exit_patterns:
        # Priority 1: Exit signal detected
        top_exit = max(exit_patterns, key=lambda p: p.match_strength)
        primary_action = (
            f"Explore exit path: {top_exit.pattern_name}. "
            f"Take the meeting. Know your BATNA. Don't dismiss this signal."
        )
        action_rationale = (
            f"Exit signal '{top_exit.pattern_name}' matched at {top_exit.match_strength:.0%} strength. "
            f"Exited founders never ignore exit windows. Even if you don't sell, "
            f"knowing your options changes your leverage."
        )
        confidence = top_exit.match_strength
        conviction_level = FOUNDER_CONVICTION_HIGH
        time_horizon = min(time_horizon, 336)  # 14 days max for exit exploration

    elif attack_fires:
        # Priority 2: Existential fire
        top_fire = max(attack_fires, key=lambda f: (f.existential_score, 1.0 - f.reversibility))
        primary_action = (
            f"ATTACK: {top_fire.description}. "
            f"This is existential. Clear your calendar. "
            f"Time to irreversible: {top_fire.time_to_irreversible}."
        )
        action_rationale = (
            f"Existential fire (score: {top_fire.existential_score:.2f}, "
            f"reversibility: {top_fire.reversibility:.2f}). "
            f"{top_fire.reasoning}"
        )
        confidence = top_fire.existential_score
        conviction_level = FOUNDER_CONVICTION_HIGH
        time_horizon = 48  # Fires need 48h response

    elif high_conviction:
        # Priority 3: High-conviction opportunity
        top_signal = max(high_conviction, key=lambda s: s.conviction_score)
        primary_action = (
            f"ACT ON: {top_signal.signal_description}. "
            f"Conviction is {top_signal.conviction_score:.0%}. "
            f"Ship the smallest version in 48h."
        )
        action_rationale = (
            f"High conviction signal (score: {top_signal.conviction_score:.2f}). "
            f"{top_signal.rationale}"
        )
        confidence = top_signal.conviction_score
        conviction_level = FOUNDER_CONVICTION_HIGH
        time_horizon = 48  # Act fast on conviction

    else:
        # Priority 4: Default — prove one thing
        # Find the strongest signal even if not HIGH conviction
        if conviction_signals:
            top_signal = max(conviction_signals, key=lambda s: s.conviction_score)
            primary_action = (
                f"PROVE ONE THING: Test '{top_signal.signal_description}' with "
                f"the smallest possible experiment. Zero cost. 48h deadline. "
                f"One metric that proves or kills it."
            )
            action_rationale = (
                f"No high-conviction signal yet (top: {top_signal.conviction_score:.2f}). "
                f"Exited founders don't wait — they create conviction through "
                f"cheap, fast experiments. Pick ONE hypothesis and test it."
            )
            confidence = top_signal.conviction_score * 0.5
            conviction_level = top_signal.conviction_level
        else:
            primary_action = (
                "TALK TO 3 CUSTOMERS TODAY. You have no signals yet. "
                "Signals come from the market, not from thinking. "
                "Get out of the building."
            )
            action_rationale = (
                "No signals to score. First principle of exited founders: "
                "information comes from action, not analysis. "
                "Find 3 potential customers and learn what keeps them up at night."
            )
            confidence = 0.3
            conviction_level = FOUNDER_CONVICTION_HIGH  # High conviction in the process

        time_horizon = 48

    # Add pattern-based wisdom to rationale
    if pattern_matches and not exit_patterns:
        top_pattern = pattern_matches[0]
        action_rationale += (
            f" Pattern alert: '{top_pattern.pattern_name}' detected "
            f"(strength: {top_pattern.match_strength:.0%}). "
            f"Counter-move: {top_pattern.counter_move}"
        )

    return FounderDecision(
        decision_id=decision_id,
        situation_id=situation.situation_id,
        pattern_matches=[pm.to_dict() for pm in pattern_matches],
        conviction_signals=[cs.to_dict() for cs in conviction_signals],
        fire_classifications=[fc.to_dict() for fc in fire_classifications],
        primary_action=primary_action,
        action_rationale=action_rationale,
        ignore_list=ignore_list,
        conviction_level=conviction_level,
        time_horizon_hours=time_horizon,
        confidence=round(confidence, 3),
    )
