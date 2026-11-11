from __future__ import annotations
from datetime import date, datetime, timezone
# @domain:   spec-1
# @module:   test_pdx1_models
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.models."""




from titan.models import (
    Affiliation,
    Anomaly,
    AnomalyTier,
    Bill,
    BillStatus,
    ConfidenceTier,
    EdgeType,
    Entity,
    Issue,
    Jurisdiction,
    Official,
    Provenance,
    Sector,
    Signal,
    _make_id,
)


def _prov() -> Provenance:
    return Provenance(
        source_uri="https://example.com/source",
        source_name="test",
        fetched_at=datetime.now(timezone.utc),
    )


class TestProvenance:
    def test_fields(self):
        p = _prov()
        assert p.source_uri.startswith("https://")
        assert p.source_name == "test"
        assert isinstance(p.fetched_at, datetime)


class TestOfficial:
    def test_make_id_deterministic(self):
        id1 = Official.make_id("Jane Doe", "Mayor", Jurisdiction.CITY_PORTLAND)
        id2 = Official.make_id("Jane Doe", "Mayor", Jurisdiction.CITY_PORTLAND)
        assert id1 == id2
        assert id1.startswith("official_")

    def test_construction(self):
        off = Official(
            official_id=Official.make_id("Jane Doe", "Mayor", Jurisdiction.CITY_PORTLAND),
            name="Jane Doe",
            role="Mayor",
            jurisdiction=Jurisdiction.CITY_PORTLAND,
            provenance=_prov(),
        )
        assert off.status == "active"
        assert off.party is None


class TestEntity:
    def test_make_id(self):
        eid = Entity.make_id("Portland General Electric")
        assert eid.startswith("entity_")

    def test_sector_tags(self):
        ent = Entity(
            entity_id=Entity.make_id("PGE"),
            canonical_name="Portland General Electric",
            kind="company",
            sectors=[Sector.UTILITY, Sector.ENERGY],
            provenance=_prov(),
        )
        assert Sector.UTILITY in ent.sectors


class TestAffiliation:
    def test_auto_id_generated(self):
        aff = Affiliation(
            official_id="off_abc",
            entity_id="ent_xyz",
            edge_type=EdgeType.DONATION,
            confidence=ConfidenceTier.HARD_RECORD,
            observed_at=datetime.now(timezone.utc),
            valid_from=date(2024, 1, 1),
            provenance=_prov(),
        )
        assert aff.affiliation_id.startswith("aff_")

    def test_open_ended_valid_to(self):
        aff = Affiliation(
            official_id="off_abc",
            entity_id="ent_xyz",
            edge_type=EdgeType.BOARD_SEAT,
            confidence=ConfidenceTier.HARD_RECORD,
            observed_at=datetime.now(timezone.utc),
            valid_from=date(2023, 6, 1),
            valid_to=None,
            provenance=_prov(),
        )
        assert aff.valid_to is None


class TestBill:
    def test_make_id(self):
        bid = Bill.make_id(Jurisdiction.STATE_OREGON, "HB 1234")
        assert bid.startswith("bill_")

    def test_default_status(self):
        bill = Bill(
            bill_id=Bill.make_id(Jurisdiction.STATE_OREGON, "HB 9999"),
            external_id="HB 9999",
            title="An Act",
            jurisdiction=Jurisdiction.STATE_OREGON,
            chamber="House",
            source_url="https://oregonlegislature.gov/bills/HB9999",
            provenance=_prov(),
        )
        assert bill.status == BillStatus.INTRODUCED


class TestSignal:
    def test_auto_id(self):
        s = Signal(
            kind="donation_made",
            occurred_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            provenance=_prov(),
        )
        assert s.signal_id.startswith("sig_")

    def test_default_weight(self):
        s = Signal(
            kind="x",
            occurred_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            provenance=_prov(),
        )
        assert s.weight == 1.0


class TestAnomaly:
    def test_auto_id(self):
        a = Anomaly(
            entity_id="ent_pge",
            tier=AnomalyTier.TIER_1,
            detected_at=datetime.now(timezone.utc),
            kind="donation_spike",
            description="3-sigma spike",
            provenance=_prov(),
        )
        assert a.anomaly_id.startswith("anom_")

    def test_tiers_ordered(self):
        assert AnomalyTier.TIER_1 < AnomalyTier.TIER_2
        assert AnomalyTier.TIER_2 < AnomalyTier.TIER_3
        assert AnomalyTier.TIER_3 < AnomalyTier.TIER_4


class TestIssue:
    def test_make_id(self):
        iid = Issue.make_id(1, datetime.now(timezone.utc))
        assert iid.startswith("issue_")

    def test_empty_sections(self):
        issue = Issue(
            issue_id=Issue.make_id(1, datetime.now(timezone.utc)),
            issue_number=1,
            title="Test",
            published_at=datetime.now(timezone.utc),
        )
        assert issue.sections == []


class TestConfidenceTier:
    def test_int_conversion(self):
        assert int(ConfidenceTier.HARD_RECORD) == 1
        assert int(ConfidenceTier.REPORTED) == 2
        assert int(ConfidenceTier.INFERRED) == 3

    def test_ordering(self):
        assert ConfidenceTier.HARD_RECORD < ConfidenceTier.REPORTED
        assert ConfidenceTier.REPORTED < ConfidenceTier.INFERRED


class TestMakeId:
    def test_deterministic(self):
        assert _make_id("x", "a", "b") == _make_id("x", "a", "b")

    def test_prefix(self):
        assert _make_id("foo", "bar").startswith("foo_")

    def test_different_inputs_different_ids(self):
        assert _make_id("x", "a") != _make_id("x", "b")
