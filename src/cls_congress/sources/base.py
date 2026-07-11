from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterResult:
    records: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source_name: str = ""

    def ok(self) -> bool:
        return not self.errors


class BaseAdapter(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> AdapterResult:
        ...
