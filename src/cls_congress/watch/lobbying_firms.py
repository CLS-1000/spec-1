from __future__ import annotations

from datetime import datetime, timezone

from cls_congress.models import Provenance, Signal
from cls_congress.watch.base import WatchModule, WatchResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TopLobbyingFirmsWatch(WatchModule):
    entity_id = "watch_lobbying_firms"
    entity_name = "Top Lobbying Firms"

    def __init__(self, names: list[str] | None = None) -> None:
        self._names = names or ["Federal Strategies LLC", "Summit Advocacy Group"]

    def collect(self) -> WatchResult:
        signals = [
            Signal(
                kind="lobbying_firm_activity",
                occurred_at=_now(),
                detected_at=_now(),
                entity_id=f"entity_{name.lower().replace(' ', '_')}",
                weight=1.2,
                description=f"Lobbying watch hit: {name}",
                provenance=Provenance(source_uri="watch://lobbying", source_name="Lobbying Watch", fetched_at=_now()),
            )
            for name in self._names
        ]
        return WatchResult(entity_id=self.entity_id, entity_name=self.entity_name, signals=signals)
