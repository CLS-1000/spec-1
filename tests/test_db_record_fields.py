"""New record fields must reach the SQLite mirror, not just JSONL."""

from __future__ import annotations

from cls_db.dual_write import make_dual_writer

RECORD = {
    "record_id": "rec-1", "run_id": "run-1", "signal_source": "nk_news",
    "classification": "ESCALATE", "confidence": 0.85,
    "signal_excerpt": "Kim Yo Jong threatened...", "llm_reasoning": "Named official, direct threat.",
}


def test_excerpt_and_reasoning_land_in_sqlite(tmp_path, caplog):
    w = make_dual_writer(tmp_path / "intel.jsonl", tmp_path / "spec1.db", "intelligence_records")
    w.write(RECORD)
    assert "SQLite write failed" not in caplog.text
    assert w.count_db() == 1
    row = w.read_db()[0]
    assert row["signal_excerpt"] == "Kim Yo Jong threatened..."
    assert row["llm_reasoning"] == "Named official, direct threat."


def test_migration_upgrades_an_existing_db(tmp_path):
    db_path = tmp_path / "spec1.db"
    make_dual_writer(tmp_path / "a.jsonl", db_path, "intelligence_records")  # already at 010
    w = make_dual_writer(tmp_path / "b.jsonl", db_path, "intelligence_records")  # re-open: no re-apply
    w.write(RECORD)
    assert w.count_db() == 1
