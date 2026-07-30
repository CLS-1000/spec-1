# @domain:   citizens_source
# @module:   watch_trimet
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""TriMet watch module.

TriMet's board is appointed by the governor. Monitors:
  - Board appointments / departures
  - Major contract awards (capital projects)
  - Fare/service change proposals
  - Budget actions

Signal kinds emitted:
- trimet_board_appointment
- trimet_contract_awarded
- trimet_fare_change_proposed
- trimet_service_change
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_trimet"
_SOURCE_URI = "https://trimet.org/about/boardofdir.htm"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class TrimetWatchModule(WatchModule):
    """Watch module for TriMet."""

    entity_id = _ENTITY_ID
    entity_name = "TriMet"

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
            result.errors.append(f"TriMet collect error: {exc}")
            logger.warning("TriMet watch error: %s", exc)
        return result

    _KIND_MAP = {
        "board": ("trimet_board_appointment", 2.5),
        "contract": ("trimet_contract_awarded", 2.0),
        "fare": ("trimet_fare_change_proposed", 3.0),
        "service": ("trimet_service_change", 2.0),
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
                    description=description or f"TriMet: {event_type}",
                    provenance=Provenance(
                        source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                        source_name="TriMet",
                        fetched_at=_now(),
                    ),
                )
        return None
