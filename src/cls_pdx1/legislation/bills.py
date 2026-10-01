# @domain:   citizens_source
# @module:   legislation_bills
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Bill state machine and tracker.

Every state transition produces a Signal that feeds the publication trigger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Bill, BillStatus, Provenance, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Valid forward transitions in the bill lifecycle.
_TRANSITIONS: dict[BillStatus, list[BillStatus]] = {
    BillStatus.INTRODUCED: [BillStatus.IN_COMMITTEE, BillStatus.FAILED, BillStatus.DEAD],
    BillStatus.IN_COMMITTEE: [BillStatus.PASSED_COMMITTEE, BillStatus.FAILED, BillStatus.DEAD],
    BillStatus.PASSED_COMMITTEE: [BillStatus.PASSED_ONE_CHAMBER, BillStatus.FAILED],
    BillStatus.PASSED_ONE_CHAMBER: [BillStatus.PASSED_BOTH_CHAMBERS, BillStatus.FAILED],
    BillStatus.PASSED_BOTH_CHAMBERS: [BillStatus.ENROLLED],
    BillStatus.ENROLLED: [BillStatus.SIGNED, BillStatus.VETOED],
    BillStatus.SIGNED: [],
    BillStatus.VETOED: [BillStatus.OVERRIDDEN, BillStatus.FAILED],
    BillStatus.OVERRIDDEN: [],
    BillStatus.FAILED: [],
    BillStatus.DEAD: [],
}

# Signal weight assigned per transition — terminal events carry more weight.
_TRANSITION_WEIGHT: dict[BillStatus, float] = {
    BillStatus.IN_COMMITTEE: 0.5,
    BillStatus.PASSED_COMMITTEE: 1.0,
    BillStatus.PASSED_ONE_CHAMBER: 2.0,
    BillStatus.PASSED_BOTH_CHAMBERS: 3.0,
    BillStatus.ENROLLED: 1.5,
    BillStatus.SIGNED: 4.0,
    BillStatus.VETOED: 3.0,
    BillStatus.OVERRIDDEN: 4.0,
    BillStatus.FAILED: 1.0,
    BillStatus.DEAD: 0.5,
}


def advance_bill(
    bill: Bill,
    new_status: BillStatus,
    provenance: Provenance,
) -> tuple[Bill, Optional[Signal]]:
    """Transition a bill to a new status. Returns updated bill + Signal if transition valid."""
    allowed = _TRANSITIONS.get(bill.status, [])
    if new_status not in allowed:
        return bill, None

    updated = bill.model_copy(
        update={"status": new_status, "last_action_at": _now().date()}
    )
    signal = Signal(
        kind="bill_state_change",
        occurred_at=_now(),
        detected_at=_now(),
        bill_id=bill.bill_id,
        weight=_TRANSITION_WEIGHT.get(new_status, 1.0),
        description=(
            f"{bill.external_id} ({bill.jurisdiction.name}): "
            f"{bill.status.name} → {new_status.name}"
        ),
        provenance=provenance,
    )
    return updated, signal


class BillTracker:
    """In-memory registry of tracked bills with transition history."""

    def __init__(self) -> None:
        self._bills: dict[str, Bill] = {}
        self._signals: list[Signal] = []

    def register(self, bill: Bill) -> None:
        self._bills[bill.bill_id] = bill

    def advance(
        self,
        bill_id: str,
        new_status: BillStatus,
        provenance: Provenance,
    ) -> Optional[Signal]:
        bill = self._bills.get(bill_id)
        if bill is None:
            return None
        updated, signal = advance_bill(bill, new_status, provenance)
        self._bills[bill_id] = updated
        if signal:
            self._signals.append(signal)
        return signal

    def get(self, bill_id: str) -> Optional[Bill]:
        return self._bills.get(bill_id)

    def all_bills(self) -> list[Bill]:
        return list(self._bills.values())

    def drain_signals(self) -> list[Signal]:
        signals = self._signals[:]
        self._signals.clear()
        return signals

    def active_bills(self) -> list[Bill]:
        terminal = {BillStatus.SIGNED, BillStatus.FAILED, BillStatus.DEAD, BillStatus.OVERRIDDEN}
        return [b for b in self._bills.values() if b.status not in terminal]
