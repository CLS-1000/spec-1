# @domain:   intelligence
# @module:   signal_scorer
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core/config/calibration.py

"""Signal Scorer — implements 4-gate scoring logic.

Ported from cls_osint/scorers/signal_scorer.py with new 4-gate architecture.

Gates:
  1. Credibility gate — source must have credibility >= threshold
  2. Volume gate     — parsed text must have enough words
  3. Velocity gate   — signal velocity score (freshness/recency proxy)
  4. Novelty gate    — text must contain high-value intelligence keywords

Only signals passing all 4 gates become Opportunity instances.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from spec1_core.schemas.models import Opportunity, ParsedSignal, Signal
from spec1_core.config.calibration import (
    SOURCE_CREDIBILITY,
    DEFAULT_CREDIBILITY,
    CREDIBILITY_THRESHOLD,
    VOLUME_THRESHOLD,
    VELOCITY_THRESHOLD,
    NOVELTY_THRESHOLD,
    VOLUME_TIERS,
)




# ─── Novelty gate ────────────────────────────────────────────────────────────
NOVELTY_TERMS: set[str] = {
    "investigation", "exclusive", "lawsuit", "indicted", "whistleblower",
    "leak", "classified", "subpoena", "fraud", "corruption", "arrested",
    "charged", "criminal", "federal", "oversight", "hearing", "testimony",
    "intelligence", "military", "strategy", "conflict", "nuclear", "cyber",
    "espionage", "covert", "sanctions", "treaty", "deployment", "warfare",
    "threat", "security", "defense", "attack", "operation", "weapon",
    "missile", "drone", "navy", "army", "coalition", "alliance", "nato",
    "ukraine", "russia", "china", "iran", "north korea", "taiwan",
    "pentagon", "cia", "nsa", "fbi", "dod", "state department",
    # DPRK military fuel & sanctions-evasion keywords
    "dprk", "pyongyang", "kim jong", "juche", "korean people's army",
    "fuel", "diesel", "petroleum", "oil imports", "refined products",
    "sanctions evasion", "dark fleet", "ship-to-ship transfer",
    "coal exports", "russia oil", "china border trade",
    "fuel depot", "strategic reserves", "military logistics",
}


# ─── Composite scoring ───────────────────────────────────────────────────────
def _score_credibility(source: str) -> float:
    return SOURCE_CREDIBILITY.get(source, DEFAULT_CREDIBILITY)


def _score_volume(word_count: int) -> float:
    for threshold, score in VOLUME_TIERS:
        if word_count >= threshold:
            return score
    return 0.10


def _score_velocity(signal: Signal) -> float:
    """Score velocity based on signal.velocity field or age."""
    if signal.velocity > 0:
        return signal.velocity
    # Derive from age: fresh signals (< 24h) score higher
    try:
        if isinstance(signal.published_at, datetime):
            pub = signal.published_at
        else:
            from dateutil import parser as dp
            pub = dp.parse(str(signal.published_at))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
        if age_hours < 6:
            return 1.0
        elif age_hours < 24:
            return 0.75
        elif age_hours < 72:
            return 0.50
        elif age_hours < 168:
            return 0.25
        else:
            return 0.10
    except Exception:
        return 0.50


def _score_novelty(text: str, keywords: list[str]) -> tuple[float, int]:
    """Return (score, hit_count) for novelty terms."""
    lower_text = text.lower()
    kw_set = {k.lower() for k in keywords}
    hits = sum(1 for term in NOVELTY_TERMS if term in lower_text or term in kw_set)
    if hits == 0:
        return 0.0, 0
    elif hits == 1:
        return 0.40, 1
    elif hits < 4:
        return 0.65, hits
    else:
        return min(0.85 + (hits - 4) * 0.03, 1.0), hits


def _priority(score: float) -> str:
    if score >= 0.75:
        return "ELEVATED"
    elif score >= 0.55:
        return "STANDARD"
    else:
        return "MONITOR"


def evaluate_gates(signal: Signal, parsed: ParsedSignal) -> dict:
    """Evaluate the 4 gates and return every score, threshold and result.

    Deterministic and side-effect free. ``score_signal`` uses this, and the
    cycle logs it for every signal — passed or blocked — so a reader can see
    exactly why an item was surfaced or discarded.
    """
    credibility = _score_credibility(signal.source)
    volume = _score_volume(parsed.word_count)
    velocity = _score_velocity(signal)
    novelty_score, novelty_hits = _score_novelty(parsed.cleaned_text, parsed.keywords)

    gates = {
        "credibility": {"value": credibility, "threshold": CREDIBILITY_THRESHOLD,
                        "passed": credibility >= CREDIBILITY_THRESHOLD},
        "volume": {"value": volume, "threshold": VOLUME_THRESHOLD,
                   "passed": volume >= VOLUME_THRESHOLD},
        "velocity": {"value": velocity, "threshold": VELOCITY_THRESHOLD,
                     "passed": velocity >= VELOCITY_THRESHOLD},
        "novelty": {"value": novelty_hits, "threshold": NOVELTY_THRESHOLD,
                    "passed": novelty_hits >= NOVELTY_THRESHOLD,
                    "score": novelty_score},
    }
    return {
        "gates": gates,
        "passed": all(g["passed"] for g in gates.values()),
        "failed_gates": [name for name, g in gates.items() if not g["passed"]],
    }


def composite_score(evaluation: dict) -> float:
    """Weighted composite of an ``evaluate_gates`` result, whether or not it passed."""
    g = evaluation["gates"]
    return round(
        g["credibility"]["value"] * 0.30
        + g["volume"]["value"] * 0.20
        + g["velocity"]["value"] * 0.20
        + g["novelty"]["score"] * 0.30,
        4,
    )


def score_signal(
    signal: Signal,
    parsed: ParsedSignal,
    run_id: str = "",
) -> Optional[Opportunity]:
    """Score a signal through 4 gates. Returns Opportunity if all pass, else None."""
    ev = evaluate_gates(signal, parsed)
    gate_results = {name: gate["passed"] for name, gate in ev["gates"].items()}

    if not ev["passed"]:
        return None

    composite = composite_score(ev)

    return Opportunity(
        opportunity_id=f"opp-{uuid.uuid4().hex[:12]}",
        signal_id=signal.signal_id,
        score=composite,
        priority=_priority(composite),
        gate_results=gate_results,
        run_id=run_id,
    )


def score_batch(
    signals: list[Signal],
    parsed_signals: list[ParsedSignal],
    run_id: str = "",
) -> dict:
    """Score a batch of signals. Returns opportunities and blocked signals."""
    opportunities: list[Opportunity] = []
    blocked: list[dict] = []
    for sig, ps in zip(signals, parsed_signals):
        opp = score_signal(sig, ps, run_id=run_id)
        if opp:
            opportunities.append(opp)
        else:
            blocked.append({"signal_id": sig.signal_id, "source": sig.source})
    return {"opportunities": opportunities, "blocked": blocked}
