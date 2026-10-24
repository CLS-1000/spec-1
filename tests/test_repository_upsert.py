"""cls_db.Repository: schema-aware writes and non-clobbering upserts (audit 2026-10-24)."""

from __future__ import annotations

import logging

from cls_db.database import Database
from cls_db.dual_write import make_dual_writer
from cls_db.migrate import ensure_schema
from cls_db.repository import Repository

# A record shaped like the cycle's: more fields than either table has columns for.
CYCLE_RECORD = {
    "record_id": "rec-1", "run_id": "run-1", "signal_id": "sig-1", "signal_source": "nk_news",
    "pattern": "p", "classification": "ESCALATE", "confidence": 0.85,
    "source_weight": 0.7, "analyst_weight": 0.6,
    "gate_results": {"credibility": True}, "hypothesis": "h",
    "signal_excerpt": "Kim Yo Jong threatened...", "llm_reasoning": "Named official.",
    "analysis_tier": "llm_verified",
    "field_no_table_has": "x",
}


def _repo(tmp_path, table: str) -> Repository:
    db = Database(tmp_path / "spec1.db")
    ensure_schema(db)
    return Repository(db, table)


def test_migration_011_columns(tmp_path):
    repo = _repo(tmp_path, "intel_records")
    assert {"signal_excerpt", "llm_reasoning", "analysis_tier"} <= repo.columns()
    assert "analysis_tier" in Repository(repo.db, "intelligence_records").columns()


def test_cycle_record_lands_in_intel_records(tmp_path, caplog):
    repo = _repo(tmp_path, "intel_records")
    with caplog.at_level(logging.WARNING):
        repo.insert_batch([CYCLE_RECORD])
    row = repo.get("rec-1")
    assert row["signal_excerpt"] == "Kim Yo Jong threatened..."
    assert row["llm_reasoning"] == "Named official."
    assert row["analysis_tier"] == "llm_verified"
    # Unknown fields are dropped from the mirror and named once in the log.
    assert "field_no_table_has" in caplog.text


def test_cycle_record_lands_in_intelligence_records_via_dual_write(tmp_path, caplog):
    w = make_dual_writer(tmp_path / "intel.jsonl", tmp_path / "spec1.db", "intelligence_records")
    w.write_batch([CYCLE_RECORD, {**CYCLE_RECORD, "record_id": "rec-2", "analysis_tier": "rule_based"}])
    assert "SQLite batch write failed" not in caplog.text
    tiers = {r["record_id"]: r["analysis_tier"] for r in w.read_db()}
    assert tiers == {"rec-1": "llm_verified", "rec-2": "rule_based"}


def test_insert_does_not_clobber_existing_fields(tmp_path):
    repo = _repo(tmp_path, "intel_records")
    repo.insert({"record_id": "a", "pattern": "orig", "confidence": 0.9, "llm_reasoning": "keep me"})
    repo.insert({"record_id": "a", "pattern": "changed"})
    row = repo.get("a")
    assert row["pattern"] == "changed"
    assert row["confidence"] == 0.9          # INSERT OR REPLACE reset this to 0.0
    assert row["llm_reasoning"] == "keep me"  # ... and this to NULL
    assert repo.count() == 1


def test_batch_with_mixed_fields_does_not_pad_with_null(tmp_path):
    repo = _repo(tmp_path, "intel_records")
    repo.insert({"record_id": "a", "confidence": 0.9, "pattern": "p"})
    repo.insert_batch([{"record_id": "a", "pattern": "p2"}, {"record_id": "b", "confidence": 0.4}])
    assert repo.get("a")["confidence"] == 0.9
    assert repo.get("a")["pattern"] == "p2"
    assert repo.get("b")["confidence"] == 0.4
    assert repo.count() == 2


def test_filter_rejects_unknown_field_and_binds_limit(tmp_path):
    repo = _repo(tmp_path, "intel_records")
    repo.insert_batch([{"record_id": f"r{i}", "classification": "INVESTIGATE"} for i in range(3)])
    assert len(repo.filter("classification", "INVESTIGATE", limit=2)) == 2
    try:
        repo.filter("classification = 'x' OR 1=1 --", "y")
    except ValueError:
        pass
    else:
        raise AssertionError("filter accepted a non-column field name")
