"""Regression tests: psyop default store anchored to spec1_home(); main JSONL
writes are key-sorted (deterministic bytes for the same record)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cls_db.database import Database
from cls_db.dual_write import DualWriter
from spec1_core.intelligence.store import JsonlStore


def _assert_sorted_lines(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    for line in lines:
        assert line == json.dumps(json.loads(line), sort_keys=True)
    return [json.loads(line) for line in lines]


def test_psyop_default_store_lands_under_spec1_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec1_core.psyop import scorer

    home, elsewhere = tmp_path / "home", tmp_path / "elsewhere"
    home.mkdir()
    elsewhere.mkdir()
    monkeypatch.setenv("SPEC1_HOME", str(home))
    monkeypatch.chdir(elsewhere)
    # conftest patches an absolute temp path in; restore the shipped relative default.
    monkeypatch.setattr(scorer, "_DEFAULT_STORE_PATH", Path("data/psyop_signals.jsonl"))
    monkeypatch.setattr(scorer, "_store", None)

    signal = {
        "topic": "t", "entities": ["A"], "sources": ["s"], "fara_matches": [],
        "legislation_matches": [], "narrative_markets": ["m1", "m2"],
        "consensus_velocity": 0.0, "origin_traceable": True,
    }
    scorer.score_psyop(signal)

    written = home.resolve() / "data" / "psyop_signals.jsonl"
    assert written.is_file()
    assert not (elsewhere / "data").exists()


def test_dual_writer_jsonl_lines_are_key_sorted(tmp_path: Path) -> None:
    dw = DualWriter(
        jsonl_path=tmp_path / "intel.jsonl",
        db=Database(tmp_path / "spec1.db"),
        table="intelligence_records",
    )
    record = {"run_id": "r", "record_id": "rec-1", "confidence": 0.5,
              "classification": "c", "signal_source": "s", "zeta": 1, "alpha": 2}
    dw.write(record)
    dw.write_batch([{**record, "record_id": "rec-2"}, {**record, "record_id": "rec-3"}])
    rows = _assert_sorted_lines(tmp_path / "intel.jsonl")
    assert [r["record_id"] for r in rows] == ["rec-1", "rec-2", "rec-3"]


def test_jsonl_store_lines_are_key_sorted(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "intel.jsonl")
    store.append({"record_id": "rec-1", "zeta": 1, "alpha": 2})
    store.append_batch([{"record_id": "rec-2", "b": 1, "a": 2}])
    rows = _assert_sorted_lines(tmp_path / "intel.jsonl")
    assert [r["record_id"] for r in rows] == ["rec-1", "rec-2"]
