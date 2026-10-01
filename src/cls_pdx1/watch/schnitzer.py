# @domain:   citizens_source
# @module:   watch_schnitzer
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Schnitzer family network watch module.

Tracks: Schnitzer Steel, Schnitzer Properties, Harsch Investment Properties,
and the broader family philanthropic network. Heavy presence in Portland real
estate, construction, and political donations.

Signal kinds emitted:
- schnitzer_donation_spike
- schnitzer_property_transaction
- schnitzer_lobbying_registered
- schnitzer_board_appointment
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Provenance, Signal
from cls_pdx1.watch.base import WatchModule, WatchResult, register_watch

logger = logging.getLogger(__name__)

_ENTITY_ID = "entity_schnitzer_family_network"
_SOURCE_URI = "https://sos.oregon.gov/elections/Pages/orestar.aspx"

# Known Schnitzer family entities — used for co-mention detection
SCHNITZER_ALIASES = frozenset(
    {
        "schnitzer steel",
        "schnitzer properties",
        "harsch investment",
        "harsch investment properties",
        "schnitzer family",
        "jordan schnitzer",
        "harold schnitzer",
        "arlene schnitzer",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@register_watch
class SchnitzerWatchModule(WatchModule):
    """Watch module for the Schnitzer family network."""

    entity_id = _ENTITY_ID
    entity_name = "Schnitzer Family Network"

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
            result.errors.append(f"Schnitzer collect error: {exc}")
            logger.warning("Schnitzer watch error: %s", exc)
        return result

    _KIND_MAP = {
        "donation": ("schnitzer_donation_spike", 2.5),
        "property": ("schnitzer_property_transaction", 2.0),
        "lobbying": ("schnitzer_lobbying_registered", 2.0),
        "board": ("schnitzer_board_appointment", 2.5),
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
                    description=description or f"Schnitzer: {event_type}",
                    provenance=Provenance(
                        source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                        source_name="ORESTAR",
                        fetched_at=_now(),
                    ),
                )
        return None
