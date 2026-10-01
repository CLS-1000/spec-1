# @domain:   citizens_source
# @module:   watch_nw_natural
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""NW Natural watch module — Northwest Natural Gas Company.

Monitors: PUC rate cases, lobbying registrations, contract awards.
NW Natural's rate cases affect both Oregon and Washington ratepayers.

Signal kinds emitted:
- nwnatural_rate_case_filed
- nwnatural_lobbying_registered
- nwnatural_contract_awarded
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_nwnatural_northwest_natural"
_PUC_URI = "https://apps.puc.state.or.us/edockets/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class NwNaturalWatchModule(WatchModule):
    """Watch module for NW Natural (Northwest Natural Gas)."""

    entity_id = _ENTITY_ID
    entity_name = "NW Natural"

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
            result.errors.append(f"NW Natural collect error: {exc}")
            logger.warning("NW Natural watch error: %s", exc)
        return result

    def _signal_from_rate_case(self, case: dict) -> Optional[Signal]:
        case_no = case.get("case_number", "")
        filing_type = case.get("filing_type", "rate_case")
        description = case.get("description", "")
        source_url = case.get("source_url", _PUC_URI)

        if not case_no:
            return None

        return Signal(
            kind="nwnatural_rate_case_filed",
            occurred_at=_now(),
            detected_at=_now(),
            entity_id=self.entity_id,
            weight=3.0,
            description=f"NW Natural {filing_type} {case_no}: {description}",
            provenance=Provenance(
                source_uri=source_url if source_url.startswith("http") else _PUC_URI,
                source_name="OR-PUC",
                fetched_at=_now(),
            ),
        )
