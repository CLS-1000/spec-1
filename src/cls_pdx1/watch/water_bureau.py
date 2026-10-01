# @domain:   citizens_source
# @module:   watch_water_bureau
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Portland Water Bureau watch module.

City bureau — anomaly surface differs from utilities:
  - Budget line items in Portland budget docs
  - City Council votes affecting the bureau
  - Contract awards via Portland procurement
  - Rate increase proposals (goes through council, not PUC)

Signal kinds emitted:
- water_bureau_budget_change
- water_bureau_rate_proposal
- water_bureau_contract_awarded
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_portland_water_bureau"
_SOURCE_URI = "https://www.portland.gov/water"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class WaterBureauWatchModule(WatchModule):
    """Watch module for Portland Water Bureau."""

    entity_id = _ENTITY_ID
    entity_name = "Portland Water Bureau"

    def __init__(self, events: Optional[list[dict]] = None) -> None:
        self._events = events or []

    def collect(self) -> WatchResult:
        result = WatchResult(entity_id=self.entity_id, entity_name=self.entity_name)
        try:
            for event in self._events:
                sig = self._signal_from_event(event)
                if sig:
                    result.signals.append(sig)
        except Exception as exc:
            result.errors.append(f"Water Bureau collect error: {exc}")
            logger.warning("Water Bureau watch error: %s", exc)
        return result

    def _signal_from_event(self, event: dict) -> Optional[Signal]:
        kind_map = {
            "budget": ("water_bureau_budget_change", 2.0),
            "rate": ("water_bureau_rate_proposal", 3.0),
            "contract": ("water_bureau_contract_awarded", 1.5),
        }
        event_type = event.get("type", "").lower()
        description = event.get("description", "")
        source_url = event.get("source_url", _SOURCE_URI)

        for key, (signal_kind, weight) in kind_map.items():
            if key in event_type:
                return Signal(
                    kind=signal_kind,
                    occurred_at=_now(),
                    detected_at=_now(),
                    entity_id=self.entity_id,
                    weight=weight,
                    description=description or f"Portland Water Bureau: {event_type}",
                    provenance=Provenance(
                        source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                        source_name="Portland-Water-Bureau",
                        fetched_at=_now(),
                    ),
                )
        return None
