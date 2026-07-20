from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from cls_congress.models import Bill, BillStatus, Provenance, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


_TRANSITIONS: dict[BillStatus, list[BillStatus]] = {
    BillStatus.INTRODUCED: [BillStatus.PASSED_HOUSE, BillStatus.FAILED],
    BillStatus.PASSED_HOUSE: [BillStatus.PASSED_SENATE, BillStatus.FAILED],
    BillStatus.PASSED_SENATE: [BillStatus.ENACTED, BillStatus.FAILED],
    BillStatus.ENACTED: [],
    BillStatus.FAILED: [],
}

_WEIGHTS: dict[BillStatus, float] = {
    BillStatus.PASSED_HOUSE: 2.0,
    BillStatus.PASSED_SENATE: 3.0,
    BillStatus.ENACTED: 4.0,
    BillStatus.FAILED: 1.0,
}


def advance_bill(bill: Bill, new_status: BillStatus, provenance: Provenance) -> tuple[Bill, Optional[Signal]]:
    allowed = _TRANSITIONS.get(bill.status, [])
    if new_status not in allowed:
        return bill, None

    updated = bill.model_copy(update={"status": new_status, "last_action_at": _now().date()})
    signal = Signal(
        kind="bill_state_change",
        occurred_at=_now(),
        detected_at=_now(),
        bill_id=bill.bill_id,
        weight=_WEIGHTS.get(new_status, 1.0),
        description=f"{bill.external_id}: {bill.status.name} -> {new_status.name}",
        provenance=provenance,
    )
    return updated, signal


class BillTracker:
    def __init__(self) -> None:
        self._bills: dict[str, Bill] = {}
        self._signals: list[Signal] = []

    def register(self, bill: Bill) -> None:
        self._bills[bill.bill_id] = bill

    def advance(self, bill_id: str, new_status: BillStatus, provenance: Provenance) -> Optional[Signal]:
        bill = self._bills.get(bill_id)
        if bill is None:
            return None
        updated, signal = advance_bill(bill, new_status, provenance)
        self._bills[bill_id] = updated
        if signal:
            self._signals.append(signal)
        return signal

    def all_bills(self) -> list[Bill]:
        return list(self._bills.values())

    def drain_signals(self) -> list[Signal]:
        signals = self._signals[:]
        self._signals.clear()
        return signals
