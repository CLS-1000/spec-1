# @domain:   citizens_source
# @module:   watch_pge
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""PGE watch module — Portland General Electric.

Monitors: PUC rate cases, lobbying registrations, board changes, donation patterns.
PGE is a public company — SEC EDGAR supplements PUC filings.

Signal kinds emitted:
- pge_rate_case_filed
- pge_lobbying_registered
- pge_board_change
- pge_donation_spike
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_pge_portland_general_electric"
_PUC_URI = "https://apps.puc.state.or.us/edockets/"
_SEC_URI = "https://www.sec.gov/cgi-bin/browse-edgar"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class PgeWatchModule(WatchModule):
    """Watch module for Portland General Electric."""

    entity_id = _ENTITY_ID
    entity_name = "Portland General Electric"

    def __init__(self, rate_cases: Optional[list[dict]] = None) -> None:
        self._rate_cases = rate_cases or []

    def collect(self) -> WatchResult:
        result = WatchResult(entity_id=self.entity_id, entity_name=self.entity_name)
        try:
            for case in self._rate_cases:
                sig = self._signal_from_rate_case(case)
                if sig:
                    result.signals.append(sig)
        except Exception as exc:
            result.errors.append(f"PGE collect error: {exc}")
            logger.warning("PGE watch error: %s", exc)
        return result

    def _signal_from_rate_case(self, case: dict) -> Optional[Signal]:
        case_no = case.get("case_number", "")
        filing_type = case.get("filing_type", "rate_case")
        description = case.get("description", "")
        source_url = case.get("source_url", _PUC_URI)

        if not case_no:
            return None

        return Signal(
            kind="pge_rate_case_filed",
            occurred_at=_now(),
            detected_at=_now(),
            entity_id=self.entity_id,
            weight=3.0,
            description=f"PGE {filing_type} {case_no}: {description}",
            provenance=Provenance(
                source_uri=source_url if source_url.startswith("http") else _PUC_URI,
                source_name="OR-PUC",
                fetched_at=_now(),
            ),
        )
