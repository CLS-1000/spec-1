# @domain:   intelligence
# @module:   test_operator_output
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the operator 3-pass structured output evaluator."""

from __future__ import annotations

from datetime import datetime, timezone

from spec1_core.schemas.models import ParsedSignal, Signal
from spec1_core.schemas.operator import (
    OPERATOR_GATE_THRESHOLD,
    OPERATOR_VERDICT_ARCHIVE,
    OPERATOR_VERDICT_ESCALATE,
    OPERATOR_VERDICT_HOLD,
    OperatorOutput,
)
from spec1_core.signal.operator_evaluator import (
    _gate_score,
    _pass1,
    _pass2,
    _pass3,
    _verdict,
    evaluate,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_signal(
    source: str = "reuters_world",
    text: str = "",
    velocity: float = 0.8,
) -> Signal:
    return Signal(
        signal_id="sig-test-001",
        source=source,
        source_type="rss",
        text=text or (
            "Federal investigators have subpoenaed records from the defense contractor "
            "following allegations of classified contract fraud and sanctions evasion. "
            "The Pentagon confirmed the investigation is ongoing. Congressional oversight "
            "hearings are scheduled. Military intelligence sources indicate the operation "
            "involved covert procurement of prohibited weapon systems."
        ),
        url="https://example.com/test",
        author="",
        published_at=datetime.now(timezone.utc),
        velocity=velocity,
        engagement=0.0,
        run_id="run-test",
        environment="test",
        metadata={},
    )


_DEFAULT_ENTITIES = ["Pentagon", "Congress", "Defense Contractor"]
_DEFAULT_KEYWORDS = ["federal", "investigation", "subpoena", "classified", "sanctions"]
_DEFAULT_TEXT = (
    "Federal investigators subpoenaed records from defense contractor "
    "regarding classified contract fraud and sanctions evasion. "
    "Pentagon confirmed ongoing military intelligence operation. "
    "Congressional oversight hearings scheduled. Covert procurement of weapon systems."
)


def _make_parsed(
    word_count: int = 120,
    keywords: list[str] | None = None,
    cleaned_text: str = "",
    entities: list[str] | None = None,
) -> ParsedSignal:
    return ParsedSignal(
        signal_id="sig-test-001",
        cleaned_text=cleaned_text if cleaned_text else _DEFAULT_TEXT,
        keywords=keywords if keywords is not None else _DEFAULT_KEYWORDS,
        entities=entities if entities is not None else _DEFAULT_ENTITIES,
        language="en",
        word_count=word_count,
    )


# ── Schema round-trip ─────────────────────────────────────────────────────────

def test_operator_output_to_dict_has_all_keys():
    sig = _make_signal()
    parsed = _make_parsed()
    out = evaluate(sig, parsed, run_id="run-001")
    d = out.to_dict()

    assert "run_id" in d
    assert "signal" in d
    assert "pass_1_evidence_quality" in d
    assert "pass_2_deviation_strength" in d
    assert "composite" in d
    assert "verdict" in d
    assert "confidence" in d
    assert "hold_reason" in d
    assert "reasoning_log" in d


def test_operator_output_signal_fields():
    sig = _make_signal(source="propublica")
    parsed = _make_parsed()
    out = evaluate(sig, parsed, run_id="run-002")
    d = out.to_dict()

    assert d["signal"]["source"] == "propublica"
    assert d["signal"]["timestamp"]  # non-empty ISO string
    assert len(d["signal"]["description"]) <= 200


# ── Pass 1 — Evidence Quality ─────────────────────────────────────────────────

def test_pass1_high_credibility_source():
    sig = _make_signal(source="reuters_world")
    parsed = _make_parsed(word_count=500)
    p1 = _pass1(sig, parsed)

    assert p1.credibility_score >= 0.85
    assert p1.volume_score == 1.0
    assert "primary" in p1.notes
    assert "rich" in p1.notes


def test_pass1_unknown_source_gets_default():
    sig = _make_signal(source="obscure_blog")
    parsed = _make_parsed(word_count=40)
    p1 = _pass1(sig, parsed)

    assert p1.credibility_score == 0.60  # DEFAULT_CREDIBILITY
    assert "sparse" in p1.notes or "moderate" in p1.notes


def test_pass1_low_word_count_low_volume():
    sig = _make_signal()
    parsed = _make_parsed(word_count=10)
    p1 = _pass1(sig, parsed)

    assert p1.volume_score < 0.30


# ── Pass 2 — Deviation Strength ───────────────────────────────────────────────

def test_pass2_high_velocity_fresh_signal():
    sig = _make_signal(velocity=1.0)
    parsed = _make_parsed()
    p2, vel, nov, hits = _pass2(sig, parsed)

    assert vel > 0.90
    assert "extreme" in p2.deviation_magnitude or "high" in p2.deviation_magnitude


def test_pass2_novelty_markers_detected():
    sig = _make_signal()
    parsed = _make_parsed(
        cleaned_text=(
            "Military intelligence classified operation subpoena investigation "
            "sanctions evasion federal oversight congressional hearing testimony "
            "weapon deployment covert cyber espionage"
        ),
        keywords=["military", "intelligence", "classified", "sanctions", "subpoena"],
        word_count=20,
    )
    p2, vel, nov, hits = _pass2(sig, parsed)

    assert hits > 0
    assert nov > 0.0
    assert "novelty-term" in p2.anti_pattern_observed


def test_pass2_no_deviation_clean_signal():
    sig = _make_signal()
    parsed = _make_parsed(
        cleaned_text="The weather in Portland was sunny today. Local residents enjoyed the park.",
        keywords=["weather", "portland", "sunny", "park"],
        word_count=15,
    )
    p2, vel, nov, hits = _pass2(sig, parsed)

    assert hits == 0
    assert "no deviation" in p2.anti_pattern_observed


def test_pass2_baseline_describes_source():
    sig = _make_signal(source="reuters_world")
    parsed = _make_parsed()
    p2, *_ = _pass2(sig, parsed)

    assert "reuters_world" in p2.baseline_pattern
    assert "high-credibility" in p2.baseline_pattern


# ── Gate Score ────────────────────────────────────────────────────────────────

def test_gate_score_weighting():
    """30/20/20/30 weighting should hold."""
    g = _gate_score(1.0, 1.0, 1.0, 1.0)
    assert g == 1.0

    g_half = _gate_score(0.5, 0.5, 0.5, 0.5)
    assert abs(g_half - 0.5) < 1e-4


def test_gate_score_below_threshold_for_weak_signal():
    # All low values should produce a score <= threshold
    g = _gate_score(0.30, 0.10, 0.10, 0.0)
    assert g <= OPERATOR_GATE_THRESHOLD


# ── Pass 3 — Beneficiary Analysis ────────────────────────────────────────────

def test_pass3_financial_markers_trigger_material_candidate():
    sig = _make_signal()
    parsed = _make_parsed(
        cleaned_text=(
            "Defense contractor awarded multi-billion dollar procurement contract. "
            "Budget allocation approved. Grant fund transfer confirmed."
        ),
        entities=["Defense Contractor", "Pentagon"],
        word_count=20,
    )
    p3 = _pass3(sig, parsed)

    assert p3.material_beneficiary.candidate is not None
    assert "financial markers" in (p3.material_beneficiary.evidence or "")
    assert p3.hypothesis_strength >= 0.40


def test_pass3_power_markers_trigger_power_candidate():
    sig = _make_signal()
    parsed = _make_parsed(
        cleaned_text=(
            "Executive directive issued overturning existing regulation. "
            "New legislation mandates surveillance oversight. Policy appointment confirmed."
        ),
        entities=["Agency", "Secretary"],
        word_count=20,
    )
    p3 = _pass3(sig, parsed)

    assert p3.power_beneficiary.candidate is not None
    assert "regulatory" in (p3.power_beneficiary.evidence or "")


def test_pass3_no_entities_low_strength():
    sig = _make_signal()
    parsed = ParsedSignal(
        signal_id="sig-test-001",
        cleaned_text="general text with sanctions and contract mentioned",
        keywords=["sanctions", "contract"],
        entities=[],
        language="en",
        word_count=10,
    )
    p3 = _pass3(sig, parsed)

    assert p3.hypothesis_strength < 0.40


def test_pass3_entities_only_gives_low_strength():
    sig = _make_signal()
    parsed = _make_parsed(
        cleaned_text="The City Council met today.",
        entities=["City Council"],
        keywords=["council"],
        word_count=6,
    )
    p3 = _pass3(sig, parsed)

    assert p3.hypothesis_strength == 0.25
    assert p3.material_beneficiary.candidate == "City Council"


# ── Verdict ───────────────────────────────────────────────────────────────────

def test_verdict_archive_when_below_threshold():
    v, supported, reason = _verdict(0.30, None)
    assert v == OPERATOR_VERDICT_ARCHIVE
    assert not supported
    assert reason is None


def test_verdict_escalate_when_beneficiary_supported():
    from spec1_core.schemas.operator import BeneficiaryAnalysis, BeneficiaryCandidate

    p3 = BeneficiaryAnalysis(
        material_beneficiary=BeneficiaryCandidate("Contractor X", "contract award"),
        power_beneficiary=BeneficiaryCandidate(None, None),
        hypothesis_strength=0.75,
    )
    v, supported, reason = _verdict(0.65, p3)
    assert v == OPERATOR_VERDICT_ESCALATE
    assert supported
    assert reason is None


def test_verdict_hold_when_high_gate_no_beneficiary():
    from spec1_core.schemas.operator import BeneficiaryAnalysis, BeneficiaryCandidate

    p3 = BeneficiaryAnalysis(
        material_beneficiary=BeneficiaryCandidate(None, None),
        power_beneficiary=BeneficiaryCandidate(None, None),
        hypothesis_strength=0.10,
    )
    v, supported, reason = _verdict(0.65, p3)
    assert v == OPERATOR_VERDICT_HOLD
    assert not supported
    assert reason is not None
    assert "human checkpoint" in reason


# ── End-to-end evaluate() ─────────────────────────────────────────────────────

def test_evaluate_high_value_signal_escalates():
    """A high-credibility, high-novelty, fresh signal with entity + financial markers escalates."""
    sig = _make_signal(source="reuters_world", velocity=1.0)
    parsed = _make_parsed(
        word_count=300,
        cleaned_text=(
            "Federal investigators have subpoenaed classified records from a major defense "
            "contractor over alleged contract fraud and sanctions evasion. The Pentagon "
            "confirmed an ongoing military intelligence operation. Congressional hearings "
            "scheduled. Covert procurement of weapon systems under investigation. "
            "Billions in procurement budget implicated."
        ),
        keywords=["federal", "subpoena", "classified", "contract", "sanctions", "fraud"],
        entities=["Defense Contractor", "Pentagon", "Congress"],
    )
    out = evaluate(sig, parsed, run_id="run-esc")

    assert isinstance(out, OperatorOutput)
    assert out.verdict == OPERATOR_VERDICT_ESCALATE
    assert out.hold_reason is None
    assert out.composite.gate_score > OPERATOR_GATE_THRESHOLD
    assert out.composite.beneficiary_supported
    assert out.pass_3_beneficiary is not None
    assert out.confidence > 0.0
    assert "Verdict → ESCALATE" in out.reasoning_log


def test_evaluate_low_quality_signal_archives():
    """A low-credibility, sparse, stale signal with no novelty should ARCHIVE."""
    sig = Signal(
        signal_id="sig-low",
        source="obscure_blog",
        source_type="rss",
        text="Weather report for today.",
        url="",
        author="",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),  # very old
        velocity=0.0,
        engagement=0.0,
        run_id="run-arch",
        environment="test",
        metadata={},
    )
    parsed = ParsedSignal(
        signal_id="sig-low",
        cleaned_text="Weather report for today.",
        keywords=["weather", "report"],
        entities=[],
        language="en",
        word_count=4,
    )
    out = evaluate(sig, parsed, run_id="run-arch")

    assert out.verdict == OPERATOR_VERDICT_ARCHIVE
    assert out.pass_3_beneficiary is None
    assert out.hold_reason is None
    assert "≤ 0.40 — ARCHIVE" in out.reasoning_log


def test_evaluate_anomalous_signal_no_beneficiary_holds():
    """A high-novelty signal with no identifiable beneficiary should HOLD."""
    sig = _make_signal(source="propublica", velocity=0.9)
    parsed = ParsedSignal(
        signal_id="sig-test-001",
        cleaned_text=(
            "Investigation reveals classified military operation underway. "
            "Whistleblower testimony submitted to congressional oversight. "
            "Federal subpoena issued for surveillance records. "
            "Cyber espionage suspected. Operation covert. Sanctions evasion confirmed."
        ),
        keywords=["classified", "military", "whistleblower", "subpoena", "surveillance", "espionage"],
        entities=[],  # no entities → beneficiary hypothesis_strength stays low
        language="en",
        word_count=250,
    )
    out = evaluate(sig, parsed, run_id="run-hold")

    assert out.verdict == OPERATOR_VERDICT_HOLD
    assert out.hold_reason is not None
    assert "human checkpoint" in out.hold_reason
    assert out.composite.gate_score > OPERATOR_GATE_THRESHOLD
    assert not out.composite.beneficiary_supported


def test_evaluate_run_id_auto_assigned():
    sig = _make_signal()
    parsed = _make_parsed()
    out = evaluate(sig, parsed)

    assert out.run_id.startswith("eval-")


def test_evaluate_confidence_bounded():
    sig = _make_signal()
    parsed = _make_parsed()
    out = evaluate(sig, parsed)

    assert 0.0 <= out.confidence <= 0.99


def test_evaluate_reasoning_log_has_all_passes():
    sig = _make_signal(source="reuters_world", velocity=1.0)
    parsed = _make_parsed(word_count=300)
    out = evaluate(sig, parsed)

    assert "Pass 1" in out.reasoning_log
    assert "Pass 2" in out.reasoning_log
    assert "Pass 3" in out.reasoning_log
    assert "Gate score" in out.reasoning_log
    assert "Verdict →" in out.reasoning_log


def test_to_dict_verdict_is_string():
    sig = _make_signal()
    parsed = _make_parsed()
    out = evaluate(sig, parsed)
    d = out.to_dict()

    assert isinstance(d["verdict"], str)
    assert d["verdict"] in {OPERATOR_VERDICT_ESCALATE, OPERATOR_VERDICT_ARCHIVE, OPERATOR_VERDICT_HOLD}


def test_to_dict_pass3_none_when_archived():
    sig = Signal(
        signal_id="sig-x",
        source="unknown",
        source_type="rss",
        text="brief note",
        url="",
        author="",
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        velocity=0.0,
        engagement=0.0,
        run_id="r",
        environment="test",
        metadata={},
    )
    parsed = ParsedSignal(
        signal_id="sig-x",
        cleaned_text="brief note",
        keywords=[],
        entities=[],
        language="en",
        word_count=2,
    )
    out = evaluate(sig, parsed)
    d = out.to_dict()

    assert d["verdict"] == OPERATOR_VERDICT_ARCHIVE
    assert d["pass_3_beneficiary"] is None
