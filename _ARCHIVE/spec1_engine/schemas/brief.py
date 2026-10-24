"""schemas/brief.py — World State Brief value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

SectionKind = Literal[
    "congress_trade",
    "fara_proximity",
    "model_legislation",
    "sector_signal",
]


@dataclass(frozen=True)
class BriefSection:
    kind: SectionKind
    valid: bool                  # True iff all 4 gates passed (>0.40 each)
    payload: Mapping[str, Any]   # type-checked by section kind in the analyst layer


@dataclass(frozen=True)
class WorldStateBrief:
    synopsis: str                # 1-line state-of-the-day from the Editor analyst
    sections: tuple[BriefSection, ...]
