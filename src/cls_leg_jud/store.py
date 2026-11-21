# @domain:   publisher
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""LegJudBrief persistence — append-only JSONL store."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Iterator, Optional

from cls_leg_jud.schemas import LegJudBrief


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LegJudStore:
    """Thread-safe append-only JSONL store for LegJudBrief records."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else anchor_to_home("leg_jud_briefs.jsonl")
        self._lock = threading.Lock()

    def save(self, brief: LegJudBrief) -> dict:
        """Persist a brief and return the written entry dict."""
        entry = {**brief.to_dict(), "written_at": _now()}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def read_all(self) -> Iterator[dict]:
        """Yield all stored brief dicts in append order."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def latest(self) -> Optional[dict]:
        """Return the most recently written brief, or None if store is empty."""
        last = None
        for record in self.read_all():
            last = record
        return last

    def get_by_run_id(self, run_id: str) -> Optional[dict]:
        """Return the first brief matching run_id, or None."""
        for record in self.read_all():
            if record.get("run_id") == run_id:
                return record
        return None

    def count(self) -> int:
        """Return total number of stored briefs."""
        return sum(1 for _ in self.read_all())

    def clear(self) -> None:
        """Delete the JSONL file, removing all stored briefs."""
        with self._lock:
            if self.path.exists():
                self.path.unlink()
