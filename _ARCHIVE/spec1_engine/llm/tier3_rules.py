"""Tier 3: rule-based fallback analyzer. Zero external calls."""

from __future__ import annotations

import json

THREAT_KEYWORDS: frozenset[str] = frozenset([
    "attack", "weapon", "missile", "hostile", "aggression", "warfare",
    "nuclear", "terrorism", "hack", "breach", "espionage", "assassination",
    "coup", "invasion", "airstrike", "bombing", "explosive", "armed forces",
    "military strike", "cyber attack", "disinformation campaign",
])

ANOMALY_KEYWORDS: frozenset[str] = frozenset([
    "unusual", "unexpected", "anomaly", "irregular", "suspicious",
    "unverified", "alleged", "potential", "possible", "concern",
    "warning", "alert", "detected", "intercept", "surveillance",
    "intelligence", "classified", "leaked", "compromise", "monitor",
    "reposition", "mobiliz", "deploy", "escalat",
])

# Maps Tier-3 verdict to SPEC-1 investigation classification
VERDICT_TO_CLASSIFICATION: dict[str, str] = {
    "THREAT": "ESCALATE",
    "ANOMALY": "INVESTIGATE",
    "CLEAR": "MONITOR",
}


def score(text: str) -> tuple[str, float, str]:
    """Return (verdict, confidence, reasoning) for the given text."""
    lower = text.lower()
    threat_hits = [kw for kw in THREAT_KEYWORDS if kw in lower]
    anomaly_hits = [kw for kw in ANOMALY_KEYWORDS if kw in lower]

    if len(threat_hits) >= 2:
        verdict = "THREAT"
        confidence = round(min(0.45 + len(threat_hits) * 0.05, 0.75), 4)
        reasoning = (
            f"Tier-3 rule: {len(threat_hits)} threat indicator(s) found: "
            f"{threat_hits[:3]}"
        )
    elif len(threat_hits) == 1 or len(anomaly_hits) >= 2:
        verdict = "ANOMALY"
        confidence = round(min(0.30 + len(anomaly_hits) * 0.04, 0.60), 4)
        reasoning = (
            f"Tier-3 rule: {len(anomaly_hits)} anomaly indicator(s), "
            f"{len(threat_hits)} threat indicator(s)"
        )
    else:
        verdict = "CLEAR"
        confidence = 0.20
        reasoning = "Tier-3 rule: no significant threat or anomaly indicators detected"

    return verdict, confidence, reasoning


def to_verifier_json(text: str) -> str:
    """Return verifier-schema JSON string from rule-based analysis.

    Schema matches what verifier.py expects from any LLM tier:
    {verified, confidence, reasoning, classification}
    """
    verdict, confidence, reasoning = score(text)
    classification = VERDICT_TO_CLASSIFICATION[verdict]
    return json.dumps({
        "verified": verdict == "THREAT",
        "confidence": confidence,
        "reasoning": reasoning,
        "classification": classification,
    })
