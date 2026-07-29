#!/usr/bin/env python3
"""Restore live JSONL and SQLite stores from git history.

The intelligence export was removed from the public repo for security reasons
(commit 6ee0d39) but remains accessible in git history. This script:

1. Extracts spec1_intelligence_export.json from the commit before the purge
2. Writes spec1_intelligence.jsonl (one record per line)
3. Creates spec1.db and backfills intel_records table

Run from the repo root:
    python scripts/restore_stores.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PURGE_COMMIT = "6ee0d39"
EXPORT_PATH = "spec1_intelligence_export.json"
JSONL_PATH = Path("spec1_intelligence.jsonl")
DB_PATH = Path("spec1.db")

INTEL_COLS = {
    "record_id", "pattern", "classification", "confidence",
    "source_weight", "analyst_weight", "run_id", "written_at",
}


def _git_show(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}~1:{path}"],
        capture_output=True,
        check=True,
    )
    return result.stdout


def restore_jsonl(records: list[dict]) -> int:
    with JSONL_PATH.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return len(records)


def restore_sqlite(records: list[dict]) -> int:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from cls_db.database import Database
    from cls_db.migrate import run_migrations
    from cls_db.repository import Repository

    db = Database(DB_PATH)
    run_migrations(db)
    repo = Repository(db, "intel_records", "record_id")

    projected = [{k: v for k, v in r.items() if k in INTEL_COLS} for r in records]
    for i in range(0, len(projected), 500):
        repo.insert_batch(projected[i : i + 500])
    return repo.count()


def main() -> None:
    print(f"Extracting {EXPORT_PATH} from {PURGE_COMMIT}~1 ...")
    raw = _git_show(PURGE_COMMIT, EXPORT_PATH)
    records: list[dict] = json.loads(raw)
    print(f"  {len(records)} records loaded")

    n_jsonl = restore_jsonl(records)
    print(f"  Wrote {n_jsonl} lines → {JSONL_PATH}")

    n_db = restore_sqlite(records)
    print(f"  SQLite intel_records: {n_db}")

    print("\nDone. Run `get_stats` via MCP to confirm.")


if __name__ == "__main__":
    main()
