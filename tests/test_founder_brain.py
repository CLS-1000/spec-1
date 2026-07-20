# @domain:   test
# @module:   test_founder_brain
# @loc:      gh_main
# @status:   stable
# @depends:  cls_founder_brain

"""Tests for cls_founder_brain — Exited-Founder Cognitive Engine.

Covers all four layers + pipeline + store + formatting.
"""

from __future__ import annotations

from pathlib import Path


from cls_founder_brain.schemas import (
    ConvictionSignal,
    FireClassification,
    FounderDecision,
    PatternMatch,
    Situation,
)
from cls_founder_brain.patterns import (
    ALL_PATTERNS,
    FAILURE_PATTERNS,
    SUCCESS_PATTERNS,
    PIVOT_PATTERNS,
    EXIT_SIGNAL_PATTERNS,
    get_pattern,
    get_patterns_by_category,
)
from cls_founder_brain.recognizer import recognize_patterns
from cls_founder_brain.conviction import score_conviction, _compute_conviction_score
from cls_founder_brain.triage import classify_fire, triage_fires
from cls_founder_brain.synthesizer import synthesize_decision
from cls_founder_brain.store import FounderBrainStore
from cls_founder_brain.pipeline import run_founder_brain, format_decision
from spec1_labels import (
    FOUNDER_PATTERN_FAILURE,
    FOUNDER_PATTERN_SUCCESS,
    FOUNDER_CONVICTION_HIGH,
    FOUNDER_CONVICTION_NOISE,
    FOUNDER_FIRE_IGNORE,
    FOUNDER_FIRE_ATTACK,
    FOUNDER_FIRE_DELEGATE,
)


# ── Schema round-trip tests ───────────────────────────────────────────────────


class TestSchemaRoundTrips:
    """All schemas must survive to_dict/from_dict without data loss."""

    def test_pattern_match_roundtrip(self):
        pm = PatternMatch(
            pattern_id="test_pattern",
            pattern_name="Test Pattern",
            category=FOUNDER_PATTERN_FAILURE,
            match_strength=0.75,
            evidence_signals=["signal_a", "signal_b"],
            historical_outcome="Companies died",
            counter_move="Do the opposite",
        )
        d = pm.to_dict()
        restored = PatternMatch.from_dict(d)
        assert restored.pattern_id == "test_pattern"
        assert restored.match_strength == 0.75
        assert restored.evidence_signals == ["signal_a", "signal_b"]
        assert restored.counter_move == "Do the opposite"

    def test_conviction_signal_roundtrip(self):
        cs = ConvictionSignal(
            signal_id="sig_1",
            signal_description="Test signal",
            signal_clarity=0.8,
            conviction_score=0.72,
            conviction_level=FOUNDER_CONVICTION_HIGH,
        )
        d = cs.to_dict()
        restored = ConvictionSignal.from_dict(d)
        assert restored.signal_id == "sig_1"
        assert restored.conviction_score == 0.72
        assert restored.conviction_level == FOUNDER_CONVICTION_HIGH

    def test_fire_classification_roundtrip(self):
        fc = FireClassification(
            fire_id="fire_1",
            description="Server is down",
            existential_score=0.8,
            reversibility=0.3,
            classification=FOUNDER_FIRE_ATTACK,
            time_to_irreversible="48h",
        )
        d = fc.to_dict()
        restored = FireClassification.from_dict(d)
        assert restored.fire_id == "fire_1"
        assert restored.classification == FOUNDER_FIRE_ATTACK
        assert restored.time_to_irreversible == "48h"

    def test_situation_roundtrip(self):
        sit = Situation(
            situation_id="sit_abc123",
            description="Building an AI product with $0",
            constraints=["$0 budget", "7 days"],
            active_fires=["no revenue", "no users"],
            signals=["AI market growing", "competitor launched"],
            stage="pre_revenue",
            runway_days=7,
        )
        d = sit.to_dict()
        restored = Situation.from_dict(d)
        assert restored.situation_id == "sit_abc123"
        assert restored.constraints == ["$0 budget", "7 days"]
        assert restored.runway_days == 7

    def test_founder_decision_roundtrip(self):
        fd = FounderDecision(
            decision_id="fd_abc123",
            situation_id="sit_abc123",
            primary_action="Ship the MVP today",
            action_rationale="Pattern match + high conviction",
            ignore_list=["logo design", "perfect docs"],
            conviction_level=FOUNDER_CONVICTION_HIGH,
            confidence=0.82,
        )
        d = fd.to_dict()
        restored = FounderDecision.from_dict(d)
        assert restored.decision_id == "fd_abc123"
        assert restored.primary_action == "Ship the MVP today"
        assert restored.ignore_list == ["logo design", "perfect docs"]


# ── Pattern Library tests ─────────────────────────────────────────────────────


class TestPatternLibrary:
    """Pattern library must be complete and indexed."""

    def test_all_patterns_non_empty(self):
        assert len(ALL_PATTERNS) >= 14

    def test_failure_patterns_exist(self):
        assert len(FAILURE_PATTERNS) >= 8

    def test_success_patterns_exist(self):
        assert len(SUCCESS_PATTERNS) >= 3

    def test_pivot_patterns_exist(self):
        assert len(PIVOT_PATTERNS) >= 2

    def test_exit_signal_patterns_exist(self):
        assert len(EXIT_SIGNAL_PATTERNS) >= 2

    def test_pattern_index_lookup(self):
        p = get_pattern("premature_scaling")
        assert p is not None
        assert p.name == "Premature Scaling"
        assert p.category == FOUNDER_PATTERN_FAILURE

    def test_pattern_index_returns_none_for_unknown(self):
        assert get_pattern("nonexistent") is None

    def test_get_patterns_by_category(self):
        failures = get_patterns_by_category(FOUNDER_PATTERN_FAILURE)
        assert len(failures) == len(FAILURE_PATTERNS)
        for p in failures:
            assert p.category == FOUNDER_PATTERN_FAILURE

    def test_all_patterns_have_triggers(self):
        for p in ALL_PATTERNS:
            assert p.triggers, f"Pattern {p.pattern_id} has no triggers"

    def test_all_patterns_have_responses(self):
        for p in ALL_PATTERNS:
            assert p.exited_response, f"Pattern {p.pattern_id} has no exited_response"
            assert p.naive_response, f"Pattern {p.pattern_id} has no naive_response"

    def test_pattern_ids_unique(self):
        ids = [p.pattern_id for p in ALL_PATTERNS]
        assert len(ids) == len(set(ids))


# ── Layer 1: Pattern Recognition tests ────────────────────────────────────────


class TestPatternRecognition:
    """Pattern recognizer must match relevant patterns."""

    def test_recognizes_premature_scaling(self):
        sit = Situation(
            situation_id="test_1",
            description="We're hiring fast but revenue isn't growing",
            signals=["team size growing faster than revenue", "hiring for roles that don't touch customers"],
            stage="pre_revenue",
            runway_days=90,
        )
        matches = recognize_patterns(sit, threshold=0.2)
        pattern_ids = [m.pattern_id for m in matches]
        assert "premature_scaling" in pattern_ids

    def test_recognizes_feature_therapy(self):
        sit = Situation(
            situation_id="test_2",
            description="We keep building features but conversion stays flat",
            signals=["roadmap growing while conversion stays flat", "engineering velocity high but growth flat"],
            stage="revenue",
            runway_days=60,
        )
        matches = recognize_patterns(sit, threshold=0.2)
        pattern_ids = [m.pattern_id for m in matches]
        assert "feature_therapy" in pattern_ids

    def test_no_match_on_empty_situation(self):
        sit = Situation(
            situation_id="test_3",
            description="",
            stage="pre_revenue",
            runway_days=7,
        )
        matches = recognize_patterns(sit, threshold=0.2)
        assert len(matches) == 0

    def test_match_strength_bounded(self):
        sit = Situation(
            situation_id="test_4",
            description="We have all the triggers for premature scaling happening at once",
            signals=[
                "team size growing faster than revenue",
                "hiring for roles that don't directly touch customers",
                "burn rate increasing without proportional revenue growth",
                "celebrating user signups instead of paying customers",
            ],
            stage="pre_revenue",
            runway_days=30,
        )
        matches = recognize_patterns(sit)
        for m in matches:
            assert 0.0 <= m.match_strength <= 1.0

    def test_max_matches_respected(self):
        sit = Situation(
            situation_id="test_5",
            description="Everything is on fire, all patterns triggered",
            signals=["hiring fast", "revenue flat", "features growing", "cofounder angry"],
            active_fires=["burn rate high", "conversion flat", "team misaligned"],
            stage="pre_revenue",
            runway_days=30,
        )
        matches = recognize_patterns(sit, threshold=0.1, max_matches=3)
        assert len(matches) <= 3


# ── Layer 2: Conviction Scorer tests ──────────────────────────────────────────


class TestConvictionScorer:
    """Conviction scoring must follow exited-founder heuristics."""

    def test_high_asymmetry_high_decay_boosts_conviction(self):
        score_high = _compute_conviction_score(
            signal_clarity=0.5,
            market_validation=0.5,
            gut_alignment=0.5,
            downside_asymmetry=0.9,
            time_decay=0.9,
        )
        score_low = _compute_conviction_score(
            signal_clarity=0.5,
            market_validation=0.5,
            gut_alignment=0.5,
            downside_asymmetry=0.2,
            time_decay=0.2,
        )
        assert score_high > score_low

    def test_conviction_bounded_0_1(self):
        score = _compute_conviction_score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert 0.0 <= score <= 1.0

    def test_score_conviction_returns_signal(self):
        cs = score_conviction(
            signal_id="test_sig",
            signal_description="AI market exploding",
            signal_clarity=0.8,
            market_validation=0.7,
            gut_alignment=0.9,
            downside_asymmetry=0.8,
            time_decay=0.7,
        )
        assert cs.conviction_level == FOUNDER_CONVICTION_HIGH
        assert cs.conviction_score > 0.5

    def test_noise_signal_classified_correctly(self):
        cs = score_conviction(
            signal_id="noise",
            signal_description="Vague tweet about market",
            signal_clarity=0.1,
            market_validation=0.1,
            gut_alignment=0.1,
            downside_asymmetry=0.1,
            time_decay=0.1,
        )
        assert cs.conviction_level == FOUNDER_CONVICTION_NOISE

    def test_pattern_matches_boost_gut(self):
        pm = PatternMatch(
            pattern_id="pull_not_push",
            pattern_name="Pull > Push",
            category=FOUNDER_PATTERN_SUCCESS,
            match_strength=0.8,
        )
        cs_with = score_conviction(
            signal_id="s1",
            signal_description="Customers finding us organically",
            gut_alignment=0.5,
            pattern_matches=[pm],
        )
        cs_without = score_conviction(
            signal_id="s2",
            signal_description="Customers finding us organically",
            gut_alignment=0.5,
            pattern_matches=None,
        )
        assert cs_with.conviction_score > cs_without.conviction_score


# ── Layer 3: Fire Triage tests ────────────────────────────────────────────────


class TestFireTriage:
    """Fire triage must correctly classify fires."""

    def test_existential_fire_classified_attack(self):
        fc = classify_fire("f1", "Production server down, all customers affected, data breach possible")
        assert fc.classification == FOUNDER_FIRE_ATTACK
        assert fc.existential_score > 0.0

    def test_cosmetic_fire_classified_ignore(self):
        fc = classify_fire("f2", "The logo color scheme doesn't match the branding guidelines")
        assert fc.classification == FOUNDER_FIRE_IGNORE

    def test_delegatable_fire_classified_delegate(self):
        fc = classify_fire("f3", "Customer support ticket about onboarding documentation needs fixing")
        assert fc.classification == FOUNDER_FIRE_DELEGATE

    def test_triage_fires_sorted_correctly(self):
        fires = [
            ("f1", "Logo needs updating for branding"),
            ("f2", "Server down, data breach suspected"),
            ("f3", "Bug fix needed in reporting dashboard"),
        ]
        results = triage_fires(fires)
        # ATTACK should come first
        classifications = [r.classification for r in results]
        if FOUNDER_FIRE_ATTACK in classifications:
            assert classifications.index(FOUNDER_FIRE_ATTACK) == 0

    def test_fire_scores_bounded(self):
        fc = classify_fire("f4", "Random situation with ambiguous severity")
        assert 0.0 <= fc.existential_score <= 1.0
        assert 0.0 <= fc.reversibility <= 1.0
        assert 0.0 <= fc.founder_leverage <= 1.0
        assert 0.0 <= fc.opportunity_cost <= 1.0


# ── Layer 4: Synthesizer tests ────────────────────────────────────────────────


class TestSynthesizer:
    """Synthesizer must produce actionable decisions."""

    def test_exit_signal_takes_priority(self):
        sit = Situation(situation_id="s1", description="test", runway_days=30)
        exit_pattern = PatternMatch(
            pattern_id="acquihire_interest",
            pattern_name="Acqui-Hire Interest",
            category="EXIT_SIGNAL",
            match_strength=0.7,
        )
        decision = synthesize_decision(sit, [exit_pattern], [], [])
        assert "exit" in decision.primary_action.lower() or "Exit" in decision.primary_action

    def test_attack_fire_takes_priority_over_signals(self):
        sit = Situation(situation_id="s2", description="test", runway_days=7)
        attack_fire = FireClassification(
            fire_id="f1",
            description="Runway hits zero in 7 days",
            existential_score=0.9,
            reversibility=0.1,
            classification=FOUNDER_FIRE_ATTACK,
            reasoning="You're about to die.",
            time_to_irreversible="7d",
        )
        decision = synthesize_decision(sit, [], [], [attack_fire])
        assert "ATTACK" in decision.primary_action

    def test_high_conviction_produces_action(self):
        sit = Situation(situation_id="s3", description="test", runway_days=14)
        high_cs = ConvictionSignal(
            signal_id="cs1",
            signal_description="Customers pulling product",
            conviction_score=0.85,
            conviction_level=FOUNDER_CONVICTION_HIGH,
        )
        decision = synthesize_decision(sit, [], [high_cs], [])
        assert "ACT ON" in decision.primary_action

    def test_no_signals_produces_customer_talk(self):
        sit = Situation(situation_id="s4", description="test", runway_days=7)
        decision = synthesize_decision(sit, [], [], [])
        assert "CUSTOMER" in decision.primary_action.upper() or "PROVE" in decision.primary_action.upper()

    def test_ignore_list_populated(self):
        sit = Situation(situation_id="s5", description="test", runway_days=7)
        ignored_fire = FireClassification(
            fire_id="f1",
            description="Logo needs work",
            classification=FOUNDER_FIRE_IGNORE,
        )
        decision = synthesize_decision(sit, [], [], [ignored_fire])
        assert "Logo needs work" in decision.ignore_list


# ── Store tests ───────────────────────────────────────────────────────────────


class TestStore:
    """Store must persist and retrieve correctly."""

    def test_append_and_read(self, tmp_path: Path):
        store = FounderBrainStore(path=tmp_path / "test.jsonl")
        decision = FounderDecision(
            decision_id="fd_test",
            situation_id="sit_test",
            primary_action="Ship it",
            confidence=0.8,
        )
        store.append(decision)
        results = store.read_all()
        assert len(results) == 1
        assert results[0].decision_id == "fd_test"

    def test_read_empty_store(self, tmp_path: Path):
        store = FounderBrainStore(path=tmp_path / "empty.jsonl")
        assert store.read_all() == []

    def test_latest(self, tmp_path: Path):
        store = FounderBrainStore(path=tmp_path / "multi.jsonl")
        for i in range(3):
            store.append(FounderDecision(
                decision_id=f"fd_{i}",
                situation_id="sit_test",
                primary_action=f"action_{i}",
            ))
        latest = store.latest()
        assert latest is not None
        assert latest.decision_id == "fd_2"

    def test_count(self, tmp_path: Path):
        store = FounderBrainStore(path=tmp_path / "count.jsonl")
        for i in range(5):
            store.append(FounderDecision(decision_id=f"fd_{i}", situation_id="s"))
        assert store.count() == 5

    def test_read_by_situation(self, tmp_path: Path):
        store = FounderBrainStore(path=tmp_path / "filter.jsonl")
        store.append(FounderDecision(decision_id="fd_1", situation_id="sit_a"))
        store.append(FounderDecision(decision_id="fd_2", situation_id="sit_b"))
        store.append(FounderDecision(decision_id="fd_3", situation_id="sit_a"))
        results = store.read_by_situation("sit_a")
        assert len(results) == 2


# ── Pipeline integration tests ────────────────────────────────────────────────


class TestPipeline:
    """Full pipeline must produce coherent decisions."""

    def test_basic_pipeline_run(self, tmp_path: Path):
        decision = run_founder_brain(
            description="I'm building an AI OSINT tool with $0 and 7 days runway",
            context="Solo founder, technical background, no customers yet",
            constraints=["$0 budget", "7 days", "no team"],
            active_fires=["no revenue", "no users", "logo not done"],
            signals=["AI market exploding", "competitor just raised $5M"],
            stage="pre_revenue",
            runway_days=7,
            store_path=tmp_path / "test_decisions.jsonl",
        )
        assert decision.decision_id.startswith("fd_")
        assert decision.primary_action != ""
        assert decision.confidence > 0.0
        assert decision.time_horizon_hours > 0

    def test_pipeline_ignores_cosmetic_fires(self, tmp_path: Path):
        decision = run_founder_brain(
            description="Building product",
            active_fires=["logo design incomplete", "brand colors not finalized"],
            signals=["customer wants to pay for beta"],
            runway_days=7,
            store_path=tmp_path / "test2.jsonl",
        )
        # Cosmetic fires should end up in ignore list
        assert any("logo" in item.lower() for item in decision.ignore_list)

    def test_pipeline_persists_to_store(self, tmp_path: Path):
        store_path = tmp_path / "persist.jsonl"
        run_founder_brain(
            description="Test persistence",
            signals=["test signal"],
            store_path=store_path,
            persist=True,
        )
        assert store_path.exists()
        store = FounderBrainStore(path=store_path)
        assert store.count() == 1

    def test_pipeline_no_persist(self, tmp_path: Path):
        store_path = tmp_path / "no_persist.jsonl"
        decision = run_founder_brain(
            description="Test no persistence",
            store_path=store_path,
            persist=False,
        )
        assert decision is not None
        assert not store_path.exists()

    def test_format_decision_produces_markdown(self, tmp_path: Path):
        decision = run_founder_brain(
            description="Need to decide what to build",
            signals=["market demand visible"],
            active_fires=["cash running low", "competitor launched"],
            runway_days=7,
            store_path=tmp_path / "fmt.jsonl",
        )
        md = format_decision(decision)
        assert "# 🧠 Founder Brain Decision" in md
        assert "PRIMARY ACTION" in md
        assert decision.primary_action in md

    def test_pipeline_with_exit_pattern(self, tmp_path: Path):
        decision = run_founder_brain(
            description="Large company corporate dev keeps scheduling coffee chats",
            signals=[
                "recruiter outreach to your engineers accelerating",
                "corporate dev coffee chats increasing",
            ],
            active_fires=[],
            stage="revenue",
            runway_days=90,
            store_path=tmp_path / "exit.jsonl",
        )
        # Should detect exit signal pattern
        assert decision.primary_action != ""
