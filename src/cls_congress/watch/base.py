from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from cls_congress.models import Signal


@dataclass
class WatchResult:
    entity_id: str
    entity_name: str
    signals: list[Signal] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors


class WatchModule(ABC):
    entity_id: str = ""
    entity_name: str = ""

    @abstractmethod
    def collect(self) -> WatchResult:
        ...
