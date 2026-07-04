from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cls_congress.anomaly import RollingBaseline, _tier_from_sigma
from cls_congress.models import AnomalyTier, Provenance, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prov() -> Provenance:
    return Provenance(source_uri="https://example.com", source_name="test", fetched_at=_now())


def _signal(entity_id: str, weight: float = 1.0, days_ago: float = 0.0) -> Signal:
    ts = _now() - timedelta(days=days_ago)
    return Signal(kind="event", occurred_at=ts, detected_at=ts, entity_id=entity_id, weight=weight, provenance=_prov())


def test_tier_thresholds():
    assert _tier_from_sigma(3.1) == AnomalyTier.TIER_1
    assert _tier_from_sigma(2.1) == AnomalyTier.TIER_2
    assert _tier_from_sigma(1.1) == AnomalyTier.TIER_3
    assert _tier_from_sigma(0.1) == AnomalyTier.TIER_4


def test_zero_baseline_spike_is_anomaly():
    baseline = RollingBaseline()
    anomaly = baseline.evaluate("ent-1", 5.0, "kind", _prov())
    assert anomaly is not None
    assert anomaly.tier == AnomalyTier.TIER_1


def test_uniform_baseline_spike_generates_anomaly():
    baseline = RollingBaseline()
    for day in range(10):
        baseline.ingest(_signal("ent-1", weight=1.0, days_ago=day + 1))

    anomaly = baseline.evaluate("ent-1", 100.0, "kind", _prov())
    assert anomaly is not None
    assert anomaly.entity_id == "ent-1"
