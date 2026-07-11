# @domain:   publisher
# @module:   tools_backfill_jsonl_to_db
# @loc:      gh_main
# @status:   stable
# @depends:  NONE
# TODO: back-import from spec1_engine — migrate to spec1_core equivalent

"""JSONL → SQLite backfill / migration tool.

Reads one or more JSONL files and inserts every record into the corresponding
SQLite table.  Safe to re-run — ``INSERT OR REPLACE`` semantics mean that
records already present in SQLite are updated in-place (idempotent).

Parity verification mode (``--verify``) counts records in both backends and
reports mismatches without writing any data.

Usage examples::

    # Backfill the intelligence store
    PYTHONPATH=src python -m spec1_engine.tools.backfill_jsonl_to_db \\
        --jsonl spec1_intelligence.jsonl \\
        --table intel_records \\
        --pk record_id

    # Backfill leads with a custom DB path
    PYTHONPATH=src python -m spec1_engine.tools.backfill_jsonl_to_db \\
        --jsonl leads.jsonl \\
        --table leads \\
        --pk lead_id \\
        --db spec1.db

    # Verify parity only (no writes)
    PYTHONPATH=src python -m spec1_engine.tools.backfill_jsonl_to_db \\
        --jsonl verdicts.jsonl \\
        --table verdicts \\
        --pk verdict_id \\
        --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _iter_jsonl(path: Path):
    """Yield parsed dicts from a JSONL file, skipping blank/invalid lines."""
    if not path.exists():
        logger.error("JSONL file not found: %s", path)
        return
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Line %d: JSON decode error — %s", lineno, exc)


def backfill(
    jsonl_path: Path,
    db_path: Path,
    table: str,
    pk_field: str = "record_id",
    batch_size: int = 500,
) -> dict:
    """Insert all records from *jsonl_path* into *table* in *db_path*.

    Returns a summary dict with ``inserted``, ``skipped``, and ``errors``.
    """
    from cls_db.database import Database
    from cls_db.migrate import ensure_schema
    from cls_db.repository import Repository

    db = Database(db_path)
    ensure_schema(db)
    repo = Repository(db, table, pk_field)

    inserted = 0
    errors = 0
    batch: list[dict] = []

    def _flush(b: list[dict]) -> tuple[int, int]:
        """Return (inserted_count, error_count) for the batch."""
        try:
            repo.insert_batch(b)
            return len(b), 0
        except Exception as exc:
            logger.warning("Batch insert failed (%d records): %s", len(b), exc)
            # Fall back to per-record inserts
            ok = 0
            errs = 0
            for rec in b:
                try:
                    repo.insert(rec)
                    ok += 1
                except Exception as rec_exc:
                    logger.warning(
                        "Record insert failed [%s=%s]: %s",
                        pk_field, rec.get(pk_field), rec_exc,
                    )
                    errs += 1
            return ok, errs

    for record in _iter_jsonl(jsonl_path):
        batch.append(record)
        if len(batch) >= batch_size:
            ok, errs = _flush(batch)
            inserted += ok
            errors += errs
            batch = []

    if batch:
        ok, errs = _flush(batch)
        inserted += ok
        errors += errs

    db_count = repo.count()
    return {
        "jsonl_path": str(jsonl_path),
        "db_path": str(db_path),
        "table": table,
        "inserted": inserted,
        "errors": errors,
        "db_count_after": db_count,
    }


def verify_parity(
    jsonl_path: Path,
    db_path: Path,
    table: str,
) -> dict:
    """Count records in both backends and report mismatches.

    Does **not** write any data — no schema migrations are run.  If the
    database or table does not exist, the DB count is reported as 0.
    """
    from cls_db.database import Database
    from cls_db.repository import Repository

    jsonl_count = sum(1 for _ in _iter_jsonl(jsonl_path))

    if not db_path.exists():
        db_count = 0
    else:
        db = Database(db_path)
        repo = Repository(db, table)
        try:
            db_count = repo.count()
        except Exception:
            # Table may not exist yet — treat as 0.
            db_count = 0

    in_sync = jsonl_count == db_count
    return {
        "jsonl_path": str(jsonl_path),
        "db_path": str(db_path),
        "table": table,
        "jsonl_count": jsonl_count,
        "db_count": db_count,
        "in_sync": in_sync,
        "delta": jsonl_count - db_count,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backfill JSONL records into SQLite (idempotent).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--jsonl",
        required=True,
        type=Path,
        help="Path to the source JSONL file.",
    )
    p.add_argument(
        "--table",
        required=True,
        help="SQLite table name to write into.",
    )
    p.add_argument(
        "--pk",
        default="record_id",
        dest="pk_field",
        help="Primary key field name (default: record_id).",
    )
    p.add_argument(
        "--db",
        default=None,
        type=Path,
        dest="db_path",
        help="SQLite database path (default: spec1.db in the CWD).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Records per insert batch (default: 500).",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="Verify parity only — no writes.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    db_path: Path = args.db_path or Path("spec1.db")

    if args.verify:
        result = verify_parity(args.jsonl, db_path, args.table)
        status = "✓ IN SYNC" if result["in_sync"] else "✗ MISMATCH"
        print(
            f"{status}  table={result['table']}"
            f"  jsonl={result['jsonl_count']}"
            f"  db={result['db_count']}"
            f"  delta={result['delta']}"
        )
        return 0 if result["in_sync"] else 1

    result = backfill(
        jsonl_path=args.jsonl,
        db_path=db_path,
        table=args.table,
        pk_field=args.pk_field,
        batch_size=args.batch_size,
    )
    print(
        f"✓ Backfill complete"
        f"  table={result['table']}"
        f"  inserted={result['inserted']}"
        f"  db_count={result['db_count_after']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
