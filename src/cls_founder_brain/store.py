# @domain:   product
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Append-only JSONL store for cls_founder_brain decisions.

Follows spec-1 convention: append-only, no deletion, no mutation.
Each entry is one FounderDecision with full provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from cls_founder_brain.schemas import FounderDecision


_DEFAULT_STORE_PATH = "founder_brain_decisions.jsonl"


class FounderBrainStore:
    """Append-only JSONL persistence for FounderDecision records."""

    def __init__(self, path: Optional[str | Path] = None):
        self._path = Path(path) if path else Path(_DEFAULT_STORE_PATH)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, decision: FounderDecision) -> None:
        """Append a decision to the store."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict()) + "\n")

    def read_all(self) -> list[FounderDecision]:
        """Read all decisions from the store."""
        if not self._path.exists():
            return []
        decisions = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    decisions.append(FounderDecision.from_dict(json.loads(line)))
        return decisions

    def read_by_situation(self, situation_id: str) -> list[FounderDecision]:
        """Read all decisions for a specific situation."""
        return [d for d in self.read_all() if d.situation_id == situation_id]

    def latest(self) -> Optional[FounderDecision]:
        """Get the most recent decision."""
        all_decisions = self.read_all()
        return all_decisions[-1] if all_decisions else None

    def count(self) -> int:
        """Count total decisions stored."""
        if not self._path.exists():
            return 0
        with open(self._path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
