# @domain:   citizens_source
# @module:   sources_wa_pdc
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""WA PDC adapter — Washington Public Disclosure Commission.

PDC API: https://data.wa.gov/resource/tijg-9uu3.json (contributions)
WA's disclosure regime is more aggressive than Oregon's — full API, bulk CSV.
Covers Clark County elected officials and Vancouver city races.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from cls_pdx1.models import Affiliation, ConfidenceTier, EdgeType, Jurisdiction, Provenance, _make_id
from cls_pdx1.sources.base import AdapterResult, BaseAdapter

logger = logging.getLogger(__name__)

_SOURCE_URI = "https://data.wa.gov/resource/tijg-9uu3.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_contribution(raw: dict[str, Any], fetched_at: datetime) -> Optional[Affiliation]:
    try:
        recipient = raw.get("filer_name", "").strip()
        contributor = raw.get("contributor_name", "").strip()
        amount_str = str(raw.get("amount", "0")).replace(",", "")
        amount = float(amount_str) if amount_str else 0.0

        date_str = raw.get("receipt_date", raw.get("election_year", ""))
        try:
            txn_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            txn_date = fetched_at.date()

        if not recipient or not contributor:
            return None

        official_id = _make_id("official", recipient, "candidate", str(int(Jurisdiction.CLARK_COUNTY_WA)))
        entity_id = _make_id("entity", contributor)

        return Affiliation(
            official_id=official_id,
            entity_id=entity_id,
            edge_type=EdgeType.DONATION,
            confidence=ConfidenceTier.HARD_RECORD,
            observed_at=fetched_at,
            valid_from=txn_date,
            amount=amount,
            description=f"WA PDC: {contributor} → {recipient} (${amount:,.2f})",
            provenance=Provenance(
                source_uri=_SOURCE_URI,
                source_name="WA-PDC",
                fetched_at=fetched_at,
            ),
        )
    except Exception as exc:
        logger.debug("WA PDC parse error: %s", exc)
        return None


class WaPdcAdapter(BaseAdapter):
    """Parses WA PDC contribution data. Accepts pre-loaded records for testing."""

    source_name = "WA-PDC"

    def __init__(self, records: Optional[list[dict]] = None) -> None:
        self._records = records

    def fetch(self) -> AdapterResult:
        if self._records is not None:
            return self._parse(self._records)
        return AdapterResult(
            source_name=self.source_name,
            errors=["WA PDC HTTP fetch not implemented — provide records list"],
        )

    def _parse(self, data: list[dict]) -> AdapterResult:
        fetched_at = _now()
        records: list[Affiliation] = []
        errors: list[str] = []
        for raw in data:
            aff = _parse_contribution(raw, fetched_at)
            if aff:
                records.append(aff)
        logger.info("WA PDC: parsed %d affiliations", len(records))
        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
