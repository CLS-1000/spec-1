# @domain:   publisher
# @module:   store
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Lead persistence — JSONL store for Lead objects, with optional SQLite dual-write."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Iterator, Optional

from cls_leads.schemas import Lead


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LeadStore:
    """Thread-safe JSONL store for Lead records, with optional SQLite dual-write.

    Modes:
    - **JSONL-only** (``LeadStore(path)``) — default; append-only file.
    - **Dual-write** (``LeadStore(path, db=database)``) — writes to both JSONL
      and the ``leads`` SQLite table via :class:`cls_db.dual_write.DualWriter`.
      JSONL remains the source of truth; SQLite failures are logged and non-fatal.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        db: Optional["Database"] = None,  # noqa: F821
    ) -> None:
        self.path = Path(path) if path is not None else anchor_to_home("leads.jsonl")
        self._lock = threading.Lock()
        self._dual_writer = None
        if db is not None:
            from cls_db.dual_write import DualWriter

            self._dual_writer = DualWriter(
                jsonl_path=self.path,
                db=db,
                table="leads",
                pk_field="lead_id",
            )

    def save(self, lead: Lead) -> dict:
        """Append a single lead to the store."""
        if self._dual_writer is not None:
            return self._dual_writer.write(lead.to_dict())
        entry = {**lead.to_dict(), "written_at": _now()}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def save_batch(self, leads: list[Lead]) -> list[dict]:
        """Append multiple leads atomically."""
        if not leads:
            return []
        if self._dual_writer is not None:
            return self._dual_writer.write_batch([lead.to_dict() for lead in leads])
        now = _now()
        written: list[dict] = []
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                for lead in leads:
                    entry = {**lead.to_dict(), "written_at": now}
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

    def by_priority(self, priority: str) -> Iterator[dict]:
        for rec in self.read_all():
            if rec.get("priority") == priority:
                yield rec

    def by_category(self, category: str) -> Iterator[dict]:
        for rec in self.read_all():
            if rec.get("category") == category:
                yield rec

    def latest(self, n: int = 10) -> list[dict]:
        return list(self.read_all())[-n:]

    def count(self) -> int:
        return sum(1 for _ in self.read_all())

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
