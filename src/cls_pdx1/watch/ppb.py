# @domain:   citizens_source
# @module:   watch_ppb
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Portland Police Bureau watch module.

City bureau. Monitors:
  - Budget line items and council votes
  - Oversight board decisions (COCL, PCCEP)
  - Contract awards (technology, training, equipment)
  - Policy changes

Signal kinds emitted:
- ppb_budget_change
- ppb_oversight_decision
- ppb_contract_awarded
- ppb_policy_change
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_portland_police_bureau"
_SOURCE_URI = "https://www.portland.gov/police"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class PpbWatchModule(WatchModule):
    """Watch module for Portland Police Bureau."""

    entity_id = _ENTITY_ID
    entity_name = "Portland Police Bureau"

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
            result.errors.append(f"PPB collect error: {exc}")
            logger.warning("PPB watch error: %s", exc)
        return result

    _KIND_MAP = {
        "budget": ("ppb_budget_change", 2.0),
        "oversight": ("ppb_oversight_decision", 2.5),
        "contract": ("ppb_contract_awarded", 1.5),
        "policy": ("ppb_policy_change", 2.0),
    }

    def _signal_from_event(self, event: dict) -> Optional[Signal]:
        event_type = event.get("type", "").lower()
        description = event.get("description", "")
        source_url = event.get("source_url", _SOURCE_URI)
        for key, (signal_kind, weight) in self._KIND_MAP.items():
            if key in event_type:
                return Signal(
                    kind=signal_kind,
                    occurred_at=_now(),
                    detected_at=_now(),
                    entity_id=self.entity_id,
                    weight=weight,
                    description=description or f"PPB: {event_type}",
                    provenance=Provenance(
                        source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                        source_name="PPB",
                        fetched_at=_now(),
                    ),
                )
        return None
