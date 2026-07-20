from __future__ import annotations

from datetime import datetime, timezone

from cls_congress.models import Bill, BillStatus, Chamber, Provenance, Signal
from cls_congress.sources.base import AdapterResult, BaseAdapter
from cls_osint.adapters import congressional


def _now() -> datetime:
    return datetime.now(timezone.utc)


_STATUS_MAP = {
    "INTRODUCED": BillStatus.INTRODUCED,
    "PASSED_HOUSE": BillStatus.PASSED_HOUSE,
    "PASSED_SENATE": BillStatus.PASSED_SENATE,
    "ENACTED": BillStatus.ENACTED,
    "FAILED": BillStatus.FAILED,
}


class CongressGovAdapter(BaseAdapter):
    source_name = "congress_gov"

    def __init__(self, *, timeout: int = 15) -> None:
        self._timeout = timeout

    def fetch(self) -> AdapterResult:
        errors: list[str] = []
        records: list[Bill | Signal] = []

        try:
            congress_records = congressional.collect(timeout=self._timeout)
        except Exception as exc:
            return AdapterResult(records=[], errors=[f"Congress adapter failed: {exc}"], source_name=self.source_name)

        for rec in congress_records:
            chamber = Chamber.SENATE if str(rec.chamber).upper().startswith("SEN") else Chamber.HOUSE
            status = _STATUS_MAP.get(str(rec.status).upper(), BillStatus.INTRODUCED)
            bill_id = Bill.make_id(rec.bill_id or rec.record_id, chamber)
            prov = Provenance(source_uri=rec.url or congressional.CONGRESS_RSS_URL, source_name="Congress.gov", fetched_at=_now())

            bill = Bill(
                bill_id=bill_id,
                external_id=rec.bill_id or rec.record_id,
                title=rec.title,
                chamber=chamber,
                status=status,
                source_url=rec.url or congressional.CONGRESS_RSS_URL,
                introduced_at=rec.date.date() if rec.date else None,
                last_action_at=rec.date.date() if rec.date else None,
                tags=rec.tags,
                metadata={"record_type": rec.record_type},
            )
            signal = Signal(
                kind="bill_status_observed",
                occurred_at=rec.date,
                detected_at=_now(),
                bill_id=bill_id,
                weight=2.0 if status in (BillStatus.PASSED_HOUSE, BillStatus.PASSED_SENATE, BillStatus.ENACTED) else 1.0,
                description=f"{bill.external_id}: {status.name}",
                provenance=prov,
            )
            records.extend([bill, signal])

        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
