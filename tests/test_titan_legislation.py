# @domain:   spec-1
# @module:   test_pdx1_legislation
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.legislation — bill state machine."""

from __future__ import annotations

from datetime import datetime, timezone


from titan.models import Bill, BillStatus, Jurisdiction, Provenance, _make_id
from titan.legislation.bills import BillTracker, advance_bill


def _prov():
    return Provenance(
        source_uri="https://oregonlegislature.gov/",
        source_name="OLIS",
        fetched_at=datetime.now(timezone.utc),
    )


def _bill(status: BillStatus = BillStatus.INTRODUCED) -> Bill:
    bid = _make_id("bill", str(int(Jurisdiction.STATE_OREGON)), "HB 1000")
    return Bill(
        bill_id=bid,
        external_id="HB 1000",
        title="Test Bill",
        jurisdiction=Jurisdiction.STATE_OREGON,
        chamber="House",
        status=status,
        source_url="https://oregonlegislature.gov/bills/HB1000",
        provenance=_prov(),
    )


class TestAdvanceBill:
    def test_valid_transition_produces_signal(self):
        bill = _bill(BillStatus.INTRODUCED)
        updated, signal = advance_bill(bill, BillStatus.IN_COMMITTEE, _prov())
        assert updated.status == BillStatus.IN_COMMITTEE
        assert signal is not None
        assert signal.kind == "bill_state_change"

    def test_invalid_transition_returns_none(self):
        bill = _bill(BillStatus.INTRODUCED)
        updated, signal = advance_bill(bill, BillStatus.SIGNED, _prov())
        assert updated.status == BillStatus.INTRODUCED  # unchanged
        assert signal is None

    def test_terminal_state_no_transition(self):
        bill = _bill(BillStatus.SIGNED)
        _, signal = advance_bill(bill, BillStatus.IN_COMMITTEE, _prov())
        assert signal is None

    def test_signal_carries_bill_id(self):
        bill = _bill()
        _, signal = advance_bill(bill, BillStatus.IN_COMMITTEE, _prov())
        assert signal is not None
        assert signal.bill_id == bill.bill_id

    def test_signal_weight_higher_for_signed(self):
        bill = _bill(BillStatus.ENROLLED)
        _, signed_sig = advance_bill(bill, BillStatus.SIGNED, _prov())
        intro_bill = _bill(BillStatus.INTRODUCED)
        _, committee_sig = advance_bill(intro_bill, BillStatus.IN_COMMITTEE, _prov())
        assert signed_sig is not None and committee_sig is not None
        assert signed_sig.weight > committee_sig.weight

    def test_failed_transition_valid(self):
        bill = _bill(BillStatus.IN_COMMITTEE)
        updated, signal = advance_bill(bill, BillStatus.FAILED, _prov())
        assert updated.status == BillStatus.FAILED
        assert signal is not None


class TestBillTracker:
    def test_register_and_get(self):
        tracker = BillTracker()
        bill = _bill()
        tracker.register(bill)
        assert tracker.get(bill.bill_id) is not None

    def test_advance_updates_status(self):
        tracker = BillTracker()
        bill = _bill()
        tracker.register(bill)
        sig = tracker.advance(bill.bill_id, BillStatus.IN_COMMITTEE, _prov())
        assert sig is not None
        assert tracker.get(bill.bill_id).status == BillStatus.IN_COMMITTEE

    def test_advance_unknown_id_returns_none(self):
        tracker = BillTracker()
        result = tracker.advance("nonexistent", BillStatus.IN_COMMITTEE, _prov())
        assert result is None

    def test_drain_signals_clears_buffer(self):
        tracker = BillTracker()
        bill = _bill()
        tracker.register(bill)
        tracker.advance(bill.bill_id, BillStatus.IN_COMMITTEE, _prov())
        signals = tracker.drain_signals()
        assert len(signals) == 1
        assert tracker.drain_signals() == []

    def test_active_bills_excludes_terminal(self):
        tracker = BillTracker()
        active = _bill(BillStatus.IN_COMMITTEE)
        signed_bill = Bill(
            bill_id=_make_id("bill", str(int(Jurisdiction.STATE_OREGON)), "HB 2000"),
            external_id="HB 2000",
            title="Signed Bill",
            jurisdiction=Jurisdiction.STATE_OREGON,
            chamber="House",
            status=BillStatus.SIGNED,
            source_url="https://oregonlegislature.gov/",
            provenance=_prov(),
        )
        tracker.register(active)
        tracker.register(signed_bill)
        active_bills = tracker.active_bills()
        assert len(active_bills) == 1
        assert active_bills[0].bill_id == active.bill_id
