# @domain:   spec-1
# @module:   test_pdx1_gates
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.gates."""

from __future__ import annotations

from datetime import date, datetime, timedelta


from titan.gates import (
    anomaly_publication_gate,
    append_only_gate,
    DEFAULT_CORROBORATION_POLICY,
    provenance_gate,
    run_gates,
    signal_freshness_gate,
    tier_corroboration_gate,
    time_bounding_gate,
)
from titan.models import (
    Affiliation,
    Anomaly,
    AnomalyTier,
    ConfidenceTier,
    EdgeType,
    Provenance,
    Signal,
)


def _prov(uri: str = "https://example.com/x") -> Provenance:
    return Provenance(
        source_uri=uri,
        source_name="test",
        fetched_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Provenance gate
# ---------------------------------------------------------------------------


class TestProvenanceGate:
    def test_accepts_record_with_valid_provenance(self):
        signal = Signal(
            kind="donation_made",
            occurred_at=datetime.utcnow(),
            detected_at=datetime.utcnow(),
            provenance=_prov(),
        )
        ok, reason = provenance_gate(signal)
        assert ok
        assert reason is None

    def test_accepts_dict_with_provenance(self):
        record = {
            "kind": "x",
            "provenance": {
                "source_uri": "https://example.com/a",
                "source_name": "t",
                "fetched_at": datetime.utcnow(),
            },
        }
        ok, reason = provenance_gate(record)
        assert ok

    def test_rejects_none(self):
        ok, reason = provenance_gate(None)
        assert not ok
        assert "PROV_" in (reason or "")

    def test_rejects_missing_provenance(self):
        ok, reason = provenance_gate({"kind": "x"})
        assert not ok

    def test_rejects_empty_source_uri(self):
        ok, reason = provenance_gate({"provenance": {"source_uri": ""}})
        assert not ok

    def test_rejects_non_url_source_uri(self):
        ok, reason = provenance_gate({"provenance": {"source_uri": "ftp://x"}})
        assert not ok


# ---------------------------------------------------------------------------
# Append-only gate
# ---------------------------------------------------------------------------


class TestAppendOnlyGate:
    def test_rejects_duplicate_id(self):
        ok, reason = append_only_gate({"abc", "def"}, "abc")
        assert not ok
        assert "abc" in (reason or "")

    def test_accepts_new_id(self):
        ok, reason = append_only_gate({"abc"}, "xyz")
        assert ok


# ---------------------------------------------------------------------------
# Time bounding gate
# ---------------------------------------------------------------------------


class TestTimeBoundingGate:
    def _aff(self, vf, vt):
        return Affiliation(
            official_id="o",
            entity_id="e",
            edge_type=EdgeType.DONATION,
            confidence=ConfidenceTier.HARD_RECORD,
            observed_at=datetime.utcnow(),
            valid_from=vf,
            valid_to=vt,
            provenance=_prov(),
        )

    def test_accepts_open_ended(self):
        ok, _ = time_bounding_gate(self._aff(date(2025, 1, 1), None))
        assert ok

    def test_accepts_valid_range(self):
        ok, _ = time_bounding_gate(self._aff(date(2025, 1, 1), date(2025, 12, 31)))
        assert ok

    def test_rejects_reversed_range(self):
        ok, reason = time_bounding_gate(
            self._aff(date(2025, 12, 31), date(2025, 1, 1))
        )
        assert not ok
        assert "TIME_002" in (reason or "")


# ---------------------------------------------------------------------------
# Tier corroboration gate
# ---------------------------------------------------------------------------


class TestTierCorroborationGate:
    def test_hard_record_needs_one(self):
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.HARD_RECORD, ["https://a/x"]
        )
        assert ok

    def test_reported_needs_two(self):
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.REPORTED, ["https://a/x"]
        )
        assert not ok
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.REPORTED, ["https://a/x", "https://b/y"]
        )
        assert ok

    def test_inferred_effectively_unpublishable(self):
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.INFERRED, ["https://a"] * 10
        )
        assert not ok

    def test_dedupes_sources(self):
        # Same URI twice doesn't satisfy 2-source requirement
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.REPORTED, ["https://a/x", "https://a/x"]
        )
        assert not ok

    def test_custom_policy(self):
        policy = {int(ConfidenceTier.HARD_RECORD): 3}
        ok, _ = tier_corroboration_gate(
            ConfidenceTier.HARD_RECORD, ["https://a"], policy=policy
        )
        assert not ok


# ---------------------------------------------------------------------------
# Anomaly publication gate
# ---------------------------------------------------------------------------


class TestAnomalyPublicationGate:
    def _anom(self, tier):
        return Anomaly(
            entity_id="ent-1",
            tier=tier,
            detected_at=datetime.utcnow(),
            kind="donation_spike",
            description="x",
            baseline_window_days=90,
            provenance=_prov(),
        )

    def test_tier_1_accepted(self):
        ok, _ = anomaly_publication_gate(self._anom(AnomalyTier.TIER_1))
        assert ok

    def test_tier_2_accepted(self):
        ok, _ = anomaly_publication_gate(self._anom(AnomalyTier.TIER_2))
        assert ok

    def test_tier_3_rejected(self):
        ok, reason = anomaly_publication_gate(self._anom(AnomalyTier.TIER_3))
        assert not ok
        assert "ANOM_" in (reason or "")

    def test_tier_4_rejected(self):
        ok, _ = anomaly_publication_gate(self._anom(AnomalyTier.TIER_4))
        assert not ok


# ---------------------------------------------------------------------------
# Signal freshness gate
# ---------------------------------------------------------------------------


class TestSignalFreshnessGate:
    def test_fresh_signal_passes(self):
        s = Signal(
            kind="x",
            occurred_at=datetime.utcnow(),
            detected_at=datetime.utcnow(),
            provenance=_prov(),
        )
        ok, _ = signal_freshness_gate(s)
        assert ok

    def test_stale_signal_rejected(self):
        s = Signal(
            kind="x",
            occurred_at=datetime.utcnow() - timedelta(days=365),
            detected_at=datetime.utcnow() - timedelta(days=365),
            provenance=_prov(),
        )
        ok, reason = signal_freshness_gate(s)
        assert not ok
        assert "FRESH_" in (reason or "")


# ---------------------------------------------------------------------------
# Composite runner
# ---------------------------------------------------------------------------


class TestRunGates:
    def test_all_pass(self):
        all_ok, failures = run_gates((True, None), (True, None))
        assert all_ok
        assert failures == []

    def test_collects_failures(self):
        all_ok, failures = run_gates(
            (True, None), (False, "X_001: bad"), (False, "Y_002: worse")
        )
        assert not all_ok
        assert len(failures) == 2
        assert "X_001: bad" in failures
        assert "Y_002: worse" in failures


# ---------------------------------------------------------------------------
# Policy invariants
# ---------------------------------------------------------------------------


class TestPolicyInvariants:
    def test_default_corroboration_policy_covers_all_tiers(self):
        for tier in ConfidenceTier:
            assert int(tier) in DEFAULT_CORROBORATION_POLICY

    def test_inferred_threshold_is_high(self):
        # Tier 4 must require enough sources to be effectively unpublishable.
        assert DEFAULT_CORROBORATION_POLICY[int(ConfidenceTier.INFERRED)] >= 10
