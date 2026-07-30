# @domain:   citizens_source
# @module:   sources_base
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Abstract base for all PDX-1i source adapters."""

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
        return len(self.errors) == 0


class BaseAdapter(ABC):
    """All source adapters implement this interface."""

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self) -> AdapterResult:
        """Fetch raw records from the source. Must not raise — log and return errors."""
        ...
