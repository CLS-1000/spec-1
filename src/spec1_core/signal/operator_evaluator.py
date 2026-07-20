# @domain:   intelligence
# @module:   signal_operator_evaluator
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core/schemas/operator.py, spec1_core/signal/scorer.py

"""Operator signal evaluator — 3-pass structured assessment.

Pass 1  Evidence quality  (credibility + volume)
Pass 2  Deviation strength (velocity + novelty + baseline comparison)
Pass 3  Beneficiary analysis — runs ONLY when gate_score > 0.40

Gate score uses the canonical 30/20/20/30 weighting (credibility/volume/velocity/novelty).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from spec1_core.config.calibration import COMPOSITE_WEIGHTS, DEFAULT_CREDIBILITY, SOURCE_CREDIBILITY
from spec1_core.schemas.models import ParsedSignal, Signal
from spec1_core.schemas.operator import (
    OPERATOR_GATE_THRESHOLD,
    OPERATOR_VERDICT_ARCHIVE,
    OPERATOR_VERDICT_ESCALATE,
    OPERATOR_VERDICT_HOLD,
    BeneficiaryAnalysis,
    BeneficiaryCandidate,
    CompositeScore,
    DeviationStrength,
    EvidenceQuality,
    OperatorOutput,
    SignalSummary,
)
from spec1_core.signal.scorer import (
    _score_credibility,
    _score_novelty,
    _score_velocity,
    _score_volume,
)

# ── Deviation marker sets ─────────────────────────────────────────────────────

_FINANCIAL_MARKERS: frozenset[str] = frozenset({
    "contract", "bid", "grant", "subsidy", "fund", "budget", "award",
    "billion", "million", "procurement", "acquisition", "revenue",
    "investment", "payment", "transfer", "profit", "loss",
})

_POWER_MARKERS: frozenset[str] = frozenset({
    "appointment", "regulation", "policy", "sanction", "treaty",
    "legislation", "executive", "classified", "operation", "oversight",
    "subpoena", "indicted", "arrested", "whistleblower", "hearing",
    "testimony", "surveillance", "directive", "mandate",
})


# ── Pass 1 — Evidence Quality ─────────────────────────────────────────────────

def _pass1(signal: Signal, parsed: ParsedSignal) -> EvidenceQuality:
    cred = _score_credibility(signal.source)
    vol = _score_volume(parsed.word_count)

    if cred >= 0.80:
        tier = "primary"
    elif cred >= 0.60:
        tier = "secondary"
    else:
        tier = "unverified"

    if parsed.word_count >= 200:
        word_tier = "rich"
    elif parsed.word_count >= 80:
        word_tier = "moderate"
    else:
        word_tier = "sparse"

    notes = (
        f"source={signal.source!r} ({tier}, credibility={cred:.2f}); "
        f"word_count={parsed.word_count} ({word_tier}, volume={vol:.2f})"
    )
    return EvidenceQuality(
        credibility_score=round(cred, 4),
        volume_score=round(vol, 4),
        notes=notes,
    )


# ── Pass 2 — Deviation Strength ───────────────────────────────────────────────

def _baseline_for(signal: Signal) -> str:
    cred = SOURCE_CREDIBILITY.get(signal.source, DEFAULT_CREDIBILITY)
    if cred >= 0.85:
        return (
            f"{signal.source}: high-credibility outlet; consistent publication cadence; "
            "deviation requires confirmed scoop or classified-level disclosure"
        )
    if cred >= 0.60:
        return (
            f"{signal.source}: mid-credibility outlet; typical reporting lag 24–72h after event; "
            "baseline = routine coverage without editorial escalation"
        )
    return (
        f"{signal.source}: low-credibility or unregistered source; "
        "elevated noise floor with no predictable publication pattern"
    )


def _anti_pattern_for(parsed: ParsedSignal, novelty_hits: int) -> str:
    text_lower = parsed.cleaned_text.lower()
    fin = [m for m in _FINANCIAL_MARKERS if m in text_lower]
    pow_ = [m for m in _POWER_MARKERS if m in text_lower]

    parts: list[str] = []
    if novelty_hits:
        parts.append(f"novelty-term hits={novelty_hits}")
    if fin:
        parts.append(f"financial-deviation markers: {', '.join(fin[:4])}")
    if pow_:
        parts.append(f"power-shift markers: {', '.join(pow_[:4])}")
    return "; ".join(parts) if parts else "no deviation from baseline pattern detected"


def _magnitude_label(velocity: float, novelty: float, novelty_hits: int) -> str:
    if velocity > 0.90:
        vel_desc = "extreme (< 6 h)"
    elif velocity > 0.70:
        vel_desc = "high (6–24 h)"
    elif velocity > 0.40:
        vel_desc = "moderate (24–72 h)"
    else:
        vel_desc = "low (> 72 h)"

    if novelty > 0.80:
        nov_desc = "very high"
    elif novelty > 0.60:
        nov_desc = "high"
    elif novelty > 0.40:
        nov_desc = "moderate"
    else:
        nov_desc = "low"

    return (
        f"velocity={vel_desc} ({velocity:.2f}); "
        f"novelty={nov_desc} ({novelty:.2f}, hits={novelty_hits})"
    )


def _pass2(signal: Signal, parsed: ParsedSignal) -> tuple[DeviationStrength, float, float, int]:
    """Return (DeviationStrength, velocity, novelty_score, novelty_hits)."""
    vel = _score_velocity(signal)
    nov_score, nov_hits = _score_novelty(parsed.cleaned_text, parsed.keywords)

    return (
        DeviationStrength(
            baseline_pattern=_baseline_for(signal),
            anti_pattern_observed=_anti_pattern_for(parsed, nov_hits),
            velocity_score=round(vel, 4),
            novelty_score=round(nov_score, 4),
            deviation_magnitude=_magnitude_label(vel, nov_score, nov_hits),
        ),
        vel,
        nov_score,
        nov_hits,
    )


# ── Gate Score ────────────────────────────────────────────────────────────────

def _gate_score(cred: float, vol: float, vel: float, nov: float) -> float:
    w = COMPOSITE_WEIGHTS
    return round(
        cred * w["credibility"]
        + vol * w["volume"]
        + vel * w["velocity"]
        + nov * w["novelty"],
        4,
    )


# ── Pass 3 — Beneficiary Analysis ────────────────────────────────────────────

def _pass3(signal: Signal, parsed: ParsedSignal) -> BeneficiaryAnalysis:
    text_lower = parsed.cleaned_text.lower()
    entities = parsed.entities

    fin = [m for m in _FINANCIAL_MARKERS if m in text_lower]
    pow_ = [m for m in _POWER_MARKERS if m in text_lower]

    # Material beneficiary
    material_candidate: Optional[str] = None
    material_evidence: Optional[str] = None
    if fin and entities:
        material_candidate = entities[0]
        material_evidence = f"financial markers in signal: {', '.join(fin[:3])}"

    # Power beneficiary — prefer a second entity if material already claimed the first
    power_candidate: Optional[str] = None
    power_evidence: Optional[str] = None
    if pow_ and entities:
        power_candidate = entities[1] if (material_candidate and len(entities) > 1) else entities[0]
        power_evidence = f"regulatory/procedural markers: {', '.join(pow_[:3])}"

    # Hypothesis strength
    if fin and pow_ and entities:
        strength = 0.75
    elif (fin or pow_) and entities:
        strength = 0.50
    elif entities:
        # Entities present but no marker matches — low-confidence hypothesis only
        material_candidate = material_candidate or entities[0]
        material_evidence = material_evidence or (
            "entity present in signal; financial/power markers not confirmed"
        )
        strength = 0.25
    else:
        strength = 0.10

    return BeneficiaryAnalysis(
        material_beneficiary=BeneficiaryCandidate(
            candidate=material_candidate, evidence=material_evidence
        ),
        power_beneficiary=BeneficiaryCandidate(
            candidate=power_candidate, evidence=power_evidence
        ),
        hypothesis_strength=round(strength, 4),
    )


# ── Verdict ───────────────────────────────────────────────────────────────────

def _verdict(
    gate_score: float,
    pass3: Optional[BeneficiaryAnalysis],
) -> tuple[str, bool, Optional[str]]:
    """Return (verdict, beneficiary_supported, hold_reason)."""
    if gate_score <= OPERATOR_GATE_THRESHOLD:
        return OPERATOR_VERDICT_ARCHIVE, False, None

    hypothesis_strength = pass3.hypothesis_strength if pass3 else 0.0
    beneficiary_supported = hypothesis_strength >= OPERATOR_GATE_THRESHOLD

    if beneficiary_supported:
        return OPERATOR_VERDICT_ESCALATE, True, None

    return (
        OPERATOR_VERDICT_HOLD,
        False,
        (
            "gate score clears threshold but no beneficiary identified — "
            "anomaly without established motive; human checkpoint required"
        ),
    )


# ── Reasoning log ─────────────────────────────────────────────────────────────

def _reasoning_log(
    pass1: EvidenceQuality,
    pass2: DeviationStrength,
    gate_score: float,
    pass3: Optional[BeneficiaryAnalysis],
    verdict: str,
    beneficiary_supported: bool,
) -> str:
    lines = [
        (
            f"Pass 1 | credibility={pass1.credibility_score:.2f} "
            f"volume={pass1.volume_score:.2f} | {pass1.notes}"
        ),
        (
            f"Pass 2 | velocity={pass2.velocity_score:.2f} "
            f"novelty={pass2.novelty_score:.2f} | "
            f"baseline: {pass2.baseline_pattern} | "
            f"anti-pattern: {pass2.anti_pattern_observed}"
        ),
        (
            f"Gate score = {gate_score:.4f} "
            f"({'> 0.40 — Pass 3 eligible' if gate_score > OPERATOR_GATE_THRESHOLD else '≤ 0.40 — ARCHIVE'})"
        ),
    ]
    if pass3:
        lines.append(
            f"Pass 3 | material={pass3.material_beneficiary.candidate!r} "
            f"power={pass3.power_beneficiary.candidate!r} | "
            f"strength={pass3.hypothesis_strength:.2f} | "
            f"beneficiary_supported={beneficiary_supported}"
        )
    else:
        lines.append("Pass 3 | skipped (gate_score ≤ 0.40)")
    lines.append(f"Verdict → {verdict}")
    return "\n".join(lines)


# ── Public entry point ────────────────────────────────────────────────────────

def evaluate(
    signal: Signal,
    parsed: ParsedSignal,
    run_id: str = "",
) -> OperatorOutput:
    """Run 3-pass operator evaluation and return a fully structured OperatorOutput."""
    if not run_id:
        run_id = f"eval-{uuid.uuid4().hex[:8]}"

    p1 = _pass1(signal, parsed)
    p2_obj, vel, nov_score, nov_hits = _pass2(signal, parsed)

    gate = _gate_score(p1.credibility_score, p1.volume_score, vel, nov_score)

    p3: Optional[BeneficiaryAnalysis] = None
    if gate > OPERATOR_GATE_THRESHOLD:
        p3 = _pass3(signal, parsed)

    v, beneficiary_supported, hold_reason = _verdict(gate, p3)

    hypothesis_strength = p3.hypothesis_strength if p3 else 0.0
    if v == OPERATOR_VERDICT_ARCHIVE:
        confidence = round(gate, 4)
    else:
        confidence = round(gate * 0.6 + hypothesis_strength * 0.4, 4)

    log = _reasoning_log(p1, p2_obj, gate, p3, v, beneficiary_supported)

    ts = (
        signal.published_at.isoformat()
        if isinstance(signal.published_at, datetime)
        else str(signal.published_at)
    )

    return OperatorOutput(
        run_id=run_id,
        signal=SignalSummary(
            description=parsed.cleaned_text[:200].strip(),
            source=signal.source,
            timestamp=ts,
        ),
        pass_1_evidence_quality=p1,
        pass_2_deviation_strength=p2_obj,
        pass_3_beneficiary=p3,
        composite=CompositeScore(
            gate_score=gate,
            beneficiary_supported=beneficiary_supported,
        ),
        verdict=v,
        confidence=min(confidence, 0.99),
        hold_reason=hold_reason,
        reasoning_log=log,
    )
