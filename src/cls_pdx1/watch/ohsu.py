# @domain:   citizens_source
# @module:   watch_ohsu
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""OHSU watch module — Oregon Health & Science University.

OHSU board is appointed by the governor. Monitors:
  - Board appointments (governor-appointed, direct political tie)
  - Major construction / real-estate contracts
  - Legislative budget allocations (OHA + OHSU funding)
  - Foundation board (IRS 990 surface)

Signal kinds emitted:
- ohsu_board_appointment
- ohsu_contract_awarded
- ohsu_budget_allocation
- ohsu_foundation_transaction
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_ohsu"
_SOURCE_URI = "https://www.ohsu.edu/about/board-of-directors"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class OhsuWatchModule(WatchModule):
    """Watch module for OHSU."""

    entity_id = _ENTITY_ID
    entity_name = "OHSU"

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
            result.errors.append(f"OHSU collect error: {exc}")
            logger.warning("OHSU watch error: %s", exc)
        return result

    _KIND_MAP = {
        "board": ("ohsu_board_appointment", 3.0),
        "contract": ("ohsu_contract_awarded", 2.0),
        "budget": ("ohsu_budget_allocation", 2.5),
        "foundation": ("ohsu_foundation_transaction", 1.5),
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
                    description=description or f"OHSU: {event_type}",
                    provenance=Provenance(
                        source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                        source_name="OHSU",
                        fetched_at=_now(),
                    ),
                )
        return None
