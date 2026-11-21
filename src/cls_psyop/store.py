# @domain:   product
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Psyop score persistence — JSONL store, with optional SQLite dual-write."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Iterator, Optional

from cls_psyop.schemas import PsyopScore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PsyopStore:
    """Thread-safe JSONL store for PsyopScore records, with optional SQLite dual-write.

    Modes:
    - **JSONL-only** (``PsyopStore(path)``) — default; append-only file.
    - **Dual-write** (``PsyopStore(path, db=database)``) — writes to both JSONL
      and the ``psyop_scores`` SQLite table via :class:`cls_db.dual_write.DualWriter`.
      JSONL remains the source of truth; SQLite failures are non-fatal.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        db: Optional["Database"] = None,  # noqa: F821
    ) -> None:
        self.path = Path(path) if path is not None else anchor_to_home("psyop_scores.jsonl")
        self._lock = threading.Lock()
        self._dual_writer = None
        if db is not None:
            from cls_db.dual_write import DualWriter

            self._dual_writer = DualWriter(
                jsonl_path=self.path,
                db=db,
                table="psyop_scores",
                pk_field="score_id",
            )

    def save(self, score: PsyopScore) -> dict:
        if self._dual_writer is not None:
            return self._dual_writer.write(score.to_dict())
        entry = {**score.to_dict(), "written_at": _now()}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def save_batch(self, scores: list[PsyopScore]) -> list[dict]:
        if not scores:
            return []
        if self._dual_writer is not None:
            return self._dual_writer.write_batch([s.to_dict() for s in scores])
        now = _now()
        written: list[dict] = []
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                for score in scores:
                    entry = {**score.to_dict(), "written_at": now}
                    fh.write(json.dumps(entry) + "\n")
                    written.append(entry)
        return written

    def read_all(self) -> Iterator[dict]:
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

    def by_classification(self, classification: str) -> Iterator[dict]:
        for rec in self.read_all():
            if rec.get("classification") == classification:
                yield rec

    def by_pattern(self, pattern_id: str) -> Iterator[dict]:
        for rec in self.read_all():
            if pattern_id in rec.get("patterns_matched", []):
                yield rec

    def count(self) -> int:
        return sum(1 for _ in self.read_all())

    def latest(self, n: int = 10) -> list[dict]:
        return list(self.read_all())[-n:]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
