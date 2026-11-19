# @domain:   machine
# @module:   dual_write
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Dual-write layer — writes to both JSONL and SQLite atomically.

Wraps the existing JSONL stores with a SQLite repository so every write
goes to both backends simultaneously.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from cls_db.database import Database
from cls_db.migrate import ensure_schema
from cls_db.repository import Repository

if TYPE_CHECKING:
    from cls_db.indexed_queries import IndexedQueryLayer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DualWriter:
    """Writes a record dict to both a JSONL file and a SQLite table."""

    def __init__(
        self,
        jsonl_path: Path,
        db: Database,
        table: str,
        pk_field: str = "record_id",
    ) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.db = db
        self.repo = Repository(db, table, pk_field)
        self.table = table
        self.pk_field = pk_field
        self.mirror_pending_path = self.jsonl_path.with_name(
            f"{self.jsonl_path.stem}_mirror_pending.jsonl"
        )
        self._lock = threading.Lock()
        ensure_schema(db)

    def _record_mirror_pending(self, entries: list[dict], exc: Exception) -> None:
        self.mirror_pending_path.parent.mkdir(parents=True, exist_ok=True)
        failed_at = _now()
        with self.mirror_pending_path.open("a", encoding="utf-8") as fh:
            for entry in entries:
                marker = {
                    self.pk_field: entry.get(self.pk_field),
                    "table": self.table,
                    "failed_at": failed_at,
                    "error": str(exc),
                }
                fh.write(json.dumps(marker, sort_keys=True) + "\n")

    def mirror_pending_count(self) -> int:
        if not self.mirror_pending_path.exists():
            return 0
        with self.mirror_pending_path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

    def write(self, record: dict) -> dict:
        """Write a single record to both JSONL and SQLite."""
        entry = {**record, "written_at": _now()}
        with self._lock:
            # JSONL write
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            # SQLite write
            try:
                self.repo.insert(entry)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning("SQLite write failed (non-fatal): %s", _e)
                self._record_mirror_pending([entry], _e)
        return entry

    def write_batch(self, records: list[dict]) -> list[dict]:
        """Write multiple records to both backends."""
        if not records:
            return []
        now = _now()
        entries = [{**r, "written_at": now} for r in records]
        with self._lock:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                for entry in entries:
                    fh.write(json.dumps(entry) + "\n")
            try:
                self.repo.insert_batch(entries)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning("SQLite batch write failed (non-fatal): %s", _e)
                self._record_mirror_pending(entries, _e)
        return entries

    def append(self, record: dict) -> dict:
        """Alias for write() — matches JsonlStore interface."""
        return self.write(record)

    def append_batch(self, records: list[dict]) -> list[dict]:
        """Alias for write_batch() — matches JsonlStore interface."""
        return self.write_batch(records)

    def read_jsonl(self) -> list[dict]:
        """Read all records from JSONL (source of truth)."""
        if not self.jsonl_path.exists():
            return []
        records: list[dict] = []
        with self.jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def read_db(self, limit: Optional[int] = None) -> list[dict]:
        """Read records from SQLite."""
        return self.repo.all(limit=limit)

    def count_jsonl(self) -> int:
        return len(self.read_jsonl())

    def count_db(self) -> int:
        return self.repo.count()

    # ------------------------------------------------------------------
    # Scalable read helpers
    # ------------------------------------------------------------------


    def read_chunked(self, limit: int = 1000):
        """Iterate over JSONL in forward-only chunks without loading the whole file.

        Yields successive ``list[dict]`` pages. Each page contains at most
        ``limit`` records. Delegates to :class:`cls_db.cursor_reader.JSONLCursorReader`.
        """
        from cls_db.cursor_reader import JSONLCursorReader

        # Pass pk_field so cursor tokens are unique even when written_at is
        # shared across batch-written records.
        reader = JSONLCursorReader(
            self.jsonl_path,
            chunk_size=limit,
            id_field=self.repo.pk_field,
            ts_field=getattr(self.repo, "ts_field", "written_at"),
        )
        yield from reader.read_all_chunked(limit=limit)

    def indexed_queries(self) -> "IndexedQueryLayer":
        """Return an :class:`cls_db.indexed_queries.IndexedQueryLayer` for this writer's table.

        Provides composable, limit-enforced queries over the SQLite backend.
        """
        from cls_db.indexed_queries import IndexedQueryLayer

        return IndexedQueryLayer(self.repo)


def make_dual_writer(
    jsonl_path: Path,
    db_path: Path,
    table: str,
    pk_field: str = "record_id",
) -> DualWriter:
    """Factory function — creates a DualWriter for the given paths and table."""
    db = Database(db_path)
    ensure_schema(db)
    return DualWriter(jsonl_path=jsonl_path, db=db, table=table, pk_field=pk_field)
