# @domain:   machine
# @module:   repository
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Generic CRUD repository for cls_db.

Provides typed insert/select/delete over SQLite tables.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from cls_db.database import Database

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(value: Any) -> Any:
    """Serialize lists/dicts to JSON strings for SQLite storage."""
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_dict(row: dict) -> dict:
    """Deserialize JSON string fields back to Python objects."""
    result: dict = {}
    for k, v in row.items():
        if isinstance(v, str) and v and v[0] in ("{", "["):
            try:
                result[k] = json.loads(v)
            except json.JSONDecodeError:
                result[k] = v
        else:
            result[k] = v
    return result


class Repository:
    """Generic repository for a single SQLite table."""

    def __init__(self, db: Database, table: str, pk_field: str = "record_id") -> None:
        self.db = db
        self.table = table
        self.pk_field = pk_field
        self._columns: Optional[frozenset[str]] = None
        self._warned_dropped: set[str] = set()

    # ── Schema awareness ──────────────────────────────────────────────────────

    def columns(self) -> frozenset[str]:
        """Column names of this table (cached; empty if the table doesn't exist)."""
        if not self._columns:  # re-check while empty: the table may be created later
            rows = self.db.fetchall(f"PRAGMA table_info({self.table})")
            self._columns = frozenset(r["name"] for r in rows)
        return self._columns

    def _fit(self, entry: dict) -> dict:
        """Keep only fields this table has a column for.

        JSONL is the source of truth; the SQLite mirror stores what its schema
        can hold. A record carrying a field the table lacks used to make the
        whole write fail. Dropped fields are logged once per table so a missing
        migration is visible instead of silent.
        """
        cols = self.columns()
        if not cols:
            return entry  # unknown schema: let SQLite report the real error
        dropped = sorted(k for k in entry if k not in cols)
        new = [k for k in dropped if k not in self._warned_dropped]
        if new:
            self._warned_dropped.update(new)
            logger.warning("%s: no column for %s — kept in JSONL only", self.table, ", ".join(new))
        return {k: v for k, v in entry.items() if k in cols}

    def _check_field(self, field: str) -> None:
        cols = self.columns()
        if cols and field not in cols:
            raise ValueError(f"{self.table} has no column {field!r}")

    # ── Writes ────────────────────────────────────────────────────────────────

    def _upsert(self, entry: dict) -> None:
        """Insert *entry*, or update only the fields it carries if the PK exists.

        Never ``INSERT OR REPLACE``: that deletes the old row and rewrites it,
        so any column the new entry doesn't mention was reset to NULL/default.
        """
        pk = entry.get(self.pk_field)
        exists = pk is not None and self.db.fetchone(
            f"SELECT 1 FROM {self.table} WHERE {self.pk_field} = ?", (pk,)  # nosec B608 — table/pk are code constants
        )
        if exists:
            fields = [k for k in entry if k != self.pk_field]
            if not fields:
                return
            assignments = ", ".join(f"{k} = ?" for k in fields)
            self.db.execute(
                f"UPDATE {self.table} SET {assignments} WHERE {self.pk_field} = ?",  # nosec B608 — columns checked by _fit
                tuple(entry[k] for k in fields) + (pk,),
            )
        else:
            columns = ", ".join(entry)
            placeholders = ", ".join("?" for _ in entry)
            self.db.execute(
                f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})",  # nosec B608 — columns checked by _fit
                tuple(entry.values()),
            )

    def insert(self, record: dict) -> dict:
        """Insert a record; if its PK already exists, update only the fields given.

        Fields the table has no column for are left out (see ``_fit``).
        """
        entry = {k: _serialize(v) for k, v in record.items()}
        if "written_at" not in entry and "created_at" not in entry:
            entry["written_at"] = _now()
        self._upsert(self._fit(entry))
        return record

    def insert_batch(self, records: list[dict]) -> int:
        """Insert multiple records (same rules as ``insert``); return count written.

        Records in one batch may carry different fields; each row is written
        with exactly the fields it has, so nothing is padded with NULL.
        """
        if not records:
            return 0
        now = _now()
        for rec in records:
            entry = {k: _serialize(v) for k, v in rec.items()}
            if "written_at" not in entry:
                entry["written_at"] = now
            self._upsert(self._fit(entry))
        return len(records)

    def get(self, pk_value: str) -> Optional[dict]:
        """Fetch a single record by primary key."""
        row = self.db.fetchone(
            f"SELECT * FROM {self.table} WHERE {self.pk_field} = ?",
            (pk_value,),
        )
        return _row_to_dict(row) if row else None

    def all(self, limit: Optional[int] = None, offset: int = 0) -> list[dict]:
        """Return all records, optionally limited."""
        sql = f"SELECT * FROM {self.table} ORDER BY rowid"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = (limit, offset)
        rows = self.db.fetchall(sql, params)
        return [_row_to_dict(r) for r in rows]

    def filter(self, field: str, value: Any, limit: Optional[int] = None) -> list[dict]:
        """Return records matching field = value. *field* must be a column."""
        self._check_field(field)
        sql = f"SELECT * FROM {self.table} WHERE {field} = ?"
        params: tuple = (_serialize(value),)
        if limit is not None:
            sql += " LIMIT ?"
            params += (int(limit),)
        rows = self.db.fetchall(sql, params)
        return [_row_to_dict(r) for r in rows]

    def count(self) -> int:
        row = self.db.fetchone(f"SELECT COUNT(*) as n FROM {self.table}")
        return row["n"] if row else 0

    def delete(self, pk_value: str) -> None:
        self.db.execute(
            f"DELETE FROM {self.table} WHERE {self.pk_field} = ?",
            (pk_value,),
        )

    def latest(self, n: int = 10) -> list[dict]:
        """Return the last n records by rowid."""
        rows = self.db.fetchall(
            f"SELECT * FROM {self.table} ORDER BY rowid DESC LIMIT ?",
            (n,),
        )
        return [_row_to_dict(r) for r in reversed(rows)]
