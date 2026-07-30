# @domain:   citizens_source
# @module:   watch_base
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Watch module base — abstract interface for PDX-1i entity monitors.

Each watch module tracks one entity (PGE, TriMet, PPB, etc.) and emits
Signal records when observable events occur. collect() must never raise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from cls_pdx1.models import Signal


@dataclass
class WatchResult:
    """Output of one collect() call — signals emitted and errors encountered."""

    entity_id: str
    entity_name: str
    signals: list[Signal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return len(self.errors) == 0


class WatchModule(ABC):
    """Contract for entity watch modules. One module per watched entity."""

    entity_id: str = ""
    entity_name: str = ""

    @abstractmethod
    def collect(self) -> WatchResult:
        """Emit signals for this entity. Must not raise — return errors in WatchResult."""
        ...


# entity_id → WatchModule subclass; populated by @register_watch
WATCH_REGISTRY: dict[str, type[WatchModule]] = {}


def register_watch(cls: type[WatchModule]) -> type[WatchModule]:
    """Decorator: register a WatchModule subclass in WATCH_REGISTRY."""
    WATCH_REGISTRY[cls.entity_id] = cls
    return cls
