"""Regression tests for Phase 1 persistence & store path hardening."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from cls_db.database import Database
from cls_db.dual_write import DualWriter
from cls_db.migrate_jsonl_to_db import backfill_jsonl_to_db, verify_parity
from spec1_core.app.cycle import run_cycle
from spec1_core.intelligence.store import resolve_store_path
from spec1_core.tools.dedup_store import dedup_jsonl_store


def test_backfill_twice_leaves_jsonl_unchanged(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "intel.jsonl"
    db_path = tmp_path / "spec1.db"

    records = [
        {"record_id": "rec-1", "run_id": "run-1", "signal_id": "sig-1", "signal_source": "reuters", "source_weight": 0.85, "analyst_weight": 0.9, "pattern": "p1", "classification": "NOISE", "confidence": 0.2},
        {"record_id": "rec-1", "run_id": "run-1", "signal_id": "sig-1", "signal_source": "reuters", "source_weight": 0.85, "analyst_weight": 0.9, "pattern": "p1", "classification": "NOISE", "confidence": 0.2},
        {"record_id": "rec-2", "run_id": "run-1", "signal_id": "sig-2", "signal_source": "ap_news", "source_weight": 0.9, "analyst_weight": 0.9, "pattern": "p2", "classification": "INVESTIGATE", "confidence": 0.8},
    ]
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    before_bytes = jsonl_path.read_bytes()

    res1 = backfill_jsonl_to_db(jsonl_path, db_path, table="intelligence_records")
    res2 = backfill_jsonl_to_db(jsonl_path, db_path, table="intelligence_records")

    assert res1["inserted"] == 2
    assert res2["inserted"] == 0
    assert jsonl_path.read_bytes() == before_bytes
    assert len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 3

    parity = verify_parity(jsonl_path, db_path, table="intelligence_records")
    assert parity["unique_jsonl_count"] == 2
    assert parity["db_count"] == 2
    assert parity["parity"] is True


def test_resolve_store_path_independent_of_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPEC1_STORE_PATH", raising=False)
    monkeypatch.setenv("SPEC1_HOME", str(tmp_path))

    other_dir = tmp_path / "subdir"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    resolved = resolve_store_path()
    assert resolved == (tmp_path / "spec1_intelligence.jsonl").resolve()
    assert resolved.is_absolute()

    override = tmp_path / "custom" / "override.jsonl"
    monkeypatch.setenv("SPEC1_STORE_PATH", str(override))
    assert resolve_store_path() == override.resolve()


def test_dedup_jsonl_store_non_destructive(tmp_path: Path) -> None:
    src = tmp_path / "spec1_intelligence.jsonl"
    lines = [
        json.dumps({"record_id": "rec-a", "v": 1}),
        json.dumps({"record_id": "rec-b", "v": 1}),
        json.dumps({"record_id": "rec-a", "v": 2}),
        json.dumps({"record_id": "rec-c", "v": 1}),
        json.dumps({"record_id": "rec-b", "v": 2}),
    ]
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    orig_bytes = src.read_bytes()

    report = dedup_jsonl_store(src)
    out = Path(report["output_path"])

    assert src.read_bytes() == orig_bytes
    assert out == tmp_path / "spec1_intelligence.dedup.jsonl"
    assert report["total_lines"] == 5
    assert report["kept_count"] == 3
    assert report["dropped_count"] == 2
    assert report["dropped_line_numbers"] == [3, 5]

    kept = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["record_id"] for r in kept] == ["rec-a", "rec-b", "rec-c"]
    assert kept[0]["v"] == 1
    assert kept[1]["v"] == 1


def test_dual_writer_records_mirror_pending_on_sqlite_failure(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "intel.jsonl"
    db = Database(tmp_path / "spec1.db")
    dw = DualWriter(jsonl_path=jsonl_path, db=db, table="intelligence_records")

    with patch.object(dw.repo, "insert", side_effect=RuntimeError("db locked")):
        dw.write({"record_id": "rec-fail-1", "run_id": "run-1"})

    with patch.object(dw.repo, "insert_batch", side_effect=RuntimeError("disk io")):
        dw.write_batch([
            {"record_id": "rec-fail-2", "run_id": "run-1"},
            {"record_id": "rec-fail-3", "run_id": "run-1"},
        ])

    assert dw.mirror_pending_count() == 3
    pending_lines = [
        json.loads(line)
        for line in dw.mirror_pending_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [p["record_id"] for p in pending_lines] == ["rec-fail-1", "rec-fail-2", "rec-fail-3"]


def test_run_cycle_exposes_mirror_pending_and_store_path(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "cycle_intel.jsonl"
    monkeypatch.setenv("SPEC1_STORE_PATH", str(store))
    monkeypatch.setenv("SPEC1_DB_PATH", str(tmp_path / "cycle.db"))

    summary = run_cycle(feeds={}, verbose=False, triage_only=True)
    assert summary["store_path"] == str(store.resolve())
    assert summary["mirror_pending"] == 0
