# @domain:    machine
# @module:    migrate_jsonl_to_db
# @loc:      gh_main
# @status:    stable
# @depends:  NONE

"""Backfill JSONL -> SQLite. Idempotent, safe to re-run without mutating JSONL."""

from __future__ import annotations

from pathlib import Path

from cls_db.dual_write import make_dual_writer


def backfill_jsonl_to_db(
    jsonl_path: Path,
    db_path: Path,
    table: str,
    pk_field: str = "record_id",
    skip_existing: bool = True,
) -> dict:
    """Migrate JSONL records into SQLite ONLY (never writes back to JSONL).

    Deduplicates candidate records by ``pk_field`` (keeping first occurrence)
    before inserting via ``Repository.insert_batch``.

    Returns {jsonl_count, unique_jsonl_count, db_count_before, db_count_after, inserted, skipped}
    """
    dw = make_dual_writer(jsonl_path, db_path, table, pk_field)

    db_count_before = dw.count_db()
    jsonl_records = dw.read_jsonl()

    existing_pks: set = set()
    if skip_existing:
        existing = dw.read_db(limit=None)
        existing_pks = {rec.get(pk_field) for rec in existing if rec.get(pk_field) is not None}

    seen_in_jsonl: set = set()
    to_insert: list[dict] = []
    for rec in jsonl_records:
        pk = rec.get(pk_field)
        if pk is not None:
            if pk in seen_in_jsonl:
                continue
            seen_in_jsonl.add(pk)
            if skip_existing and pk in existing_pks:
                continue
        to_insert.append(rec)

    if to_insert:
        dw.repo.insert_batch(to_insert)

    db_count_after = dw.count_db()

    return {
        "jsonl_count": len(jsonl_records),
        "unique_jsonl_count": len(seen_in_jsonl),
        "db_count_before": db_count_before,
        "db_count_after": db_count_after,
        "inserted": len(to_insert),
        "skipped": len(jsonl_records) - len(to_insert),
    }


def verify_parity(jsonl_path: Path, db_path: Path, table: str, pk_field: str = "record_id") -> dict:
    """Check unique JSONL PK count == SQLite row count.

    Returns {jsonl_count, unique_jsonl_count, db_count, parity, delta}
    """
    dw = make_dual_writer(jsonl_path, db_path, table, pk_field)

    jsonl_records = dw.read_jsonl()
    unique_pks = {r.get(pk_field) for r in jsonl_records if r.get(pk_field) is not None}
    unique_count = len(unique_pks) if unique_pks else len(jsonl_records)
    db_count = dw.count_db()

    return {
        "jsonl_count": len(jsonl_records),
        "unique_jsonl_count": unique_count,
        "db_count": db_count,
        "parity": unique_count == db_count,
        "delta": unique_count - db_count,
    }
