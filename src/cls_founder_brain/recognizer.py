# @domain:   product
# @module:   recognizer
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain.patterns, cls_founder_brain.schemas

"""Layer 1: Pattern Recognition Engine.

Matches a Situation against the founder pattern library using
deterministic keyword/trigger matching. No LLM required.

The matching algorithm:
  1. Tokenize situation description + signals + fires into a term set
  2. For each pattern, compute overlap between situation terms and pattern triggers
  3. Score match_strength = matched_triggers / total_triggers (weighted by specificity)
  4. Return all patterns above threshold, sorted by match_strength desc
"""

from __future__ import annotations

import re

from cls_founder_brain.patterns import ALL_PATTERNS
from cls_founder_brain.schemas import PatternMatch, Situation


def _tokenize(text: str) -> set[str]:
    """Extract meaningful terms from text (lowercase, deduped)."""
    words = re.findall(r"[a-z][a-z0-9_-]+", text.lower())
    return set(words)


def _compute_trigger_overlap(situation_terms: set[str], triggers: list[str]) -> float:
    """Score how well situation terms match a pattern's triggers.

    Each trigger is a phrase — we check how many trigger phrases
    have significant word overlap with the situation terms.
    """
    if not triggers:
        return 0.0

    matched_triggers = 0
    for trigger in triggers:
        trigger_terms = _tokenize(trigger)
        if not trigger_terms:
            continue
        overlap = len(trigger_terms & situation_terms)
        # A trigger matches if >= 40% of its terms appear in the situation
        if overlap / len(trigger_terms) >= 0.4:
            matched_triggers += 1

    return matched_triggers / len(triggers)


def _build_situation_terms(situation: Situation) -> set[str]:
    """Build the full term set from all situation fields."""
    all_text = " ".join([
        situation.description,
        situation.context,
        " ".join(situation.constraints),
        " ".join(situation.active_fires),
        " ".join(situation.signals),
        situation.stage,
    ])
    return _tokenize(all_text)


def recognize_patterns(
    situation: Situation,
    threshold: float = 0.2,
    max_matches: int = 5,
) -> list[PatternMatch]:
    """Match situation against the full pattern library.

    Args:
        situation: The current situation to analyze.
        threshold: Minimum match_strength to include (0.0–1.0).
        max_matches: Maximum patterns to return.

    Returns:
        Sorted list of PatternMatch (strongest first).
    """
    situation_terms = _build_situation_terms(situation)
    if not situation_terms:
        return []

    matches: list[PatternMatch] = []

    for pattern in ALL_PATTERNS:
        match_strength = _compute_trigger_overlap(situation_terms, pattern.triggers)

        if match_strength >= threshold:
            # Determine which signals/fires provided evidence
            evidence = []
            for signal in situation.signals + situation.active_fires:
                signal_terms = _tokenize(signal)
                for trigger in pattern.triggers:
                    trigger_terms = _tokenize(trigger)
                    if trigger_terms and len(signal_terms & trigger_terms) / len(trigger_terms) >= 0.3:
                        evidence.append(signal)
                        break

            matches.append(PatternMatch(
                pattern_id=pattern.pattern_id,
                pattern_name=pattern.name,
                category=pattern.category,
                match_strength=round(match_strength, 3),
                evidence_signals=evidence,
                historical_outcome=pattern.naive_response,
                counter_move=pattern.exited_response,
            ))

    matches.sort(key=lambda m: m.match_strength, reverse=True)
    return matches[:max_matches]
