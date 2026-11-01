# @domain:   spec-1
# @module:   test_pdx1_triggers
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.triggers — publication trigger evaluator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


from titan.models import Anomaly, AnomalyTier, Provenance, Signal
from titan.triggers import TriggerPolicy, TriggerState, evaluate_trigger


def _now():
    return datetime.now(timezone.utc)


def _prov():
    return Provenance(source_uri="https://example.com/x", source_name="t", fetched_at=_now())


def _signal(weight: float = 1.0) -> Signal:
    return Signal(
        kind="test",
        occurred_at=_now(),
        detected_at=_now(),
        weight=weight,
        provenance=_prov(),
    )


def _anomaly(tier: AnomalyTier) -> Anomaly:
    return Anomaly(
        entity_id="ent-1",
        tier=tier,
        detected_at=_now(),
        kind="test_spike",
        description="x",
        provenance=_prov(),
    )


class TestTriggerState:
    def test_empty_weight_is_zero(self):
        state = TriggerState()
        assert state.accumulated_weight() == 0.0

    def test_adds_signal_weights(self):
        state = TriggerState()
        state.add_signal(_signal(2.5))
        state.add_signal(_signal(1.0))
        assert state.accumulated_weight() == 3.5

    def test_has_no_tier1_initially(self):
        state = TriggerState()
        assert not state.has_tier1_anomaly()

    def test_detects_tier1_anomaly(self):
        state = TriggerState()
        state.add_anomaly(_anomaly(AnomalyTier.TIER_1))
        assert state.has_tier1_anomaly()

    def test_tier2_does_not_set_tier1_flag(self):
        state = TriggerState()
        state.add_anomaly(_anomaly(AnomalyTier.TIER_2))
        assert not state.has_tier1_anomaly()

    def test_days_since_none_when_no_prior_issue(self):
        state = TriggerState()
        assert state.days_since_last_issue() is None

    def test_days_since_counts_correctly(self):
        state = TriggerState()
        state.last_published_at = _now() - timedelta(days=7)
        days = state.days_since_last_issue()
        assert days is not None
        assert 6.9 < days < 7.1


class TestEvaluateTrigger:
    def test_no_signals_no_publish(self):
        result = evaluate_trigger(TriggerState())
        assert not result.should_publish

    def test_weight_threshold_triggers(self):
        policy = TriggerPolicy(signal_weight_threshold=5.0, min_spacing_days=0)
        state = TriggerState()
        for _ in range(5):
            state.add_signal(_signal(1.0))
        result = evaluate_trigger(state, policy)
        assert result.should_publish

    def test_below_threshold_no_publish(self):
        policy = TriggerPolicy(signal_weight_threshold=10.0, min_spacing_days=0)
        state = TriggerState()
        state.add_signal(_signal(1.0))
        result = evaluate_trigger(state, policy)
        assert not result.should_publish

    def test_min_spacing_blocks_early_publish(self):
        policy = TriggerPolicy(signal_weight_threshold=1.0, min_spacing_days=5)
        state = TriggerState()
        state.last_published_at = _now() - timedelta(days=2)
        state.add_signal(_signal(100.0))
        result = evaluate_trigger(state, policy)
        assert not result.should_publish

    def test_tier1_auto_triggers(self):
        policy = TriggerPolicy(
            signal_weight_threshold=100.0, min_spacing_days=0, tier1_auto_trigger=True
        )
        state = TriggerState()
        state.add_anomaly(_anomaly(AnomalyTier.TIER_1))
        result = evaluate_trigger(state, policy)
        assert result.should_publish
        assert "TIER_1" in result.reason

    def test_floor_cadence_triggers(self):
        policy = TriggerPolicy(
            signal_weight_threshold=100.0, min_spacing_days=0, max_silence_days=7
        )
        state = TriggerState()
        state.last_published_at = _now() - timedelta(days=10)
        result = evaluate_trigger(state, policy)
        assert result.should_publish
        assert "floor" in result.reason

    def test_result_counts_pending(self):
        state = TriggerState()
        state.add_signal(_signal(1.0))
        state.add_signal(_signal(1.0))
        result = evaluate_trigger(state)
        assert result.pending_signal_count == 2
