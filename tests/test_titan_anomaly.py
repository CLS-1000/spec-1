# @domain:   spec-1
# @module:   test_pdx1_anomaly
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.anomaly — rolling baseline detector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


from titan.anomaly import RollingBaseline, _tier_from_sigma
from titan.models import AnomalyTier, Provenance, Signal


def _now():
    return datetime.now(timezone.utc)


def _prov():
    return Provenance(
        source_uri="https://example.com/x",
        source_name="test",
        fetched_at=_now(),
    )


def _signal(entity_id: str, weight: float = 1.0, days_ago: float = 0.0) -> Signal:
    ts = _now() - timedelta(days=days_ago)
    return Signal(
        kind="test_event",
        occurred_at=ts,
        detected_at=ts,
        entity_id=entity_id,
        weight=weight,
        provenance=_prov(),
    )


class TestTierFromSigma:
    def test_tier_1_at_3sigma(self):
        assert _tier_from_sigma(3.0) == AnomalyTier.TIER_1

    def test_tier_1_above_3sigma(self):
        assert _tier_from_sigma(5.0) == AnomalyTier.TIER_1

    def test_tier_2_at_2sigma(self):
        assert _tier_from_sigma(2.0) == AnomalyTier.TIER_2

    def test_tier_2_between_2_and_3(self):
        assert _tier_from_sigma(2.5) == AnomalyTier.TIER_2

    def test_tier_3_at_1sigma(self):
        assert _tier_from_sigma(1.0) == AnomalyTier.TIER_3

    def test_tier_4_below_1sigma(self):
        assert _tier_from_sigma(0.5) == AnomalyTier.TIER_4

    def test_tier_4_at_zero(self):
        assert _tier_from_sigma(0.0) == AnomalyTier.TIER_4


class TestRollingBaseline:
    def test_empty_baseline_returns_zero_stats(self):
        bl = RollingBaseline()
        mean, std = bl.stats("ent-1")
        assert mean == 0.0
        assert std == 0.0

    def test_signals_outside_window_excluded(self):
        bl = RollingBaseline(window_days=30)
        bl.ingest(_signal("ent-1", weight=100.0, days_ago=60))
        mean, std = bl.stats("ent-1")
        assert mean == 0.0

    def test_signals_within_window_included(self):
        bl = RollingBaseline(window_days=90)
        bl.ingest(_signal("ent-1", weight=5.0, days_ago=1))
        bl.ingest(_signal("ent-1", weight=3.0, days_ago=2))
        mean, std = bl.stats("ent-1")
        assert mean > 0.0

    def test_ignores_signal_without_entity(self):
        bl = RollingBaseline()
        s = Signal(
            kind="no_entity",
            occurred_at=_now(),
            detected_at=_now(),
            provenance=_prov(),
        )
        bl.ingest(s)
        assert bl.stats("ent-x") == (0.0, 0.0)

    def test_no_anomaly_when_below_1sigma(self):
        bl = RollingBaseline()
        for i in range(30):
            bl.ingest(_signal("ent-1", weight=1.0, days_ago=float(i)))
        # current value close to mean — should not detect
        result = bl.evaluate("ent-1", 1.0, "test_kind", _prov())
        assert result is None

    def test_anomaly_detected_on_spike(self):
        bl = RollingBaseline()
        # Build a stable baseline
        for i in range(30):
            bl.ingest(_signal("ent-1", weight=1.0, days_ago=float(i + 1)))
        # Massive spike
        result = bl.evaluate("ent-1", 100.0, "test_kind", _prov())
        assert result is not None
        assert result.tier in (AnomalyTier.TIER_1, AnomalyTier.TIER_2)

    def test_first_spike_from_zero_baseline_is_tier1(self):
        bl = RollingBaseline()
        result = bl.evaluate("ent-new", 5.0, "test_kind", _prov())
        assert result is not None
        assert result.tier == AnomalyTier.TIER_1

    def test_anomaly_carries_entity_id(self):
        bl = RollingBaseline()
        result = bl.evaluate("ent-abc", 10.0, "kind", _prov())
        assert result is not None
        assert result.entity_id == "ent-abc"

    def test_anomaly_window_days_matches_baseline(self):
        bl = RollingBaseline(window_days=45)
        result = bl.evaluate("ent-x", 10.0, "kind", _prov())
        assert result is not None
        assert result.baseline_window_days == 45
