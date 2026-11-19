"""Regression tests: env-relative store/DB paths anchor to spec1_home(), and the
SQLite mirror keeps the e763302 provenance fields (migration 012)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cls_db.database import Database
from cls_db.dual_write import DualWriter
from spec1_core.intelligence.store import resolve_db_path, resolve_store_path


@pytest.fixture()
def home_and_elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    elsewhere = tmp_path / "elsewhere"
    home.mkdir()
    elsewhere.mkdir()
    monkeypatch.setenv("SPEC1_HOME", str(home))
    monkeypatch.chdir(elsewhere)
    return home.resolve(), elsewhere.resolve()


def test_relative_env_paths_anchor_to_spec1_home(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = home_and_elsewhere
    monkeypatch.setenv("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    monkeypatch.setenv("SPEC1_DB_PATH", "spec1.db")
    assert resolve_store_path() == home / "spec1_intelligence.jsonl"
    assert resolve_db_path() == home / "spec1.db"


def test_absolute_env_paths_pass_through(
    home_and_elsewhere: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = (tmp_path / "abs" / "intel.jsonl").resolve()
    db = (tmp_path / "abs" / "x.db").resolve()
    monkeypatch.setenv("SPEC1_STORE_PATH", str(store))
    monkeypatch.setenv("SPEC1_DB_PATH", str(db))
    assert resolve_store_path() == store
    assert resolve_db_path() == db


def test_unset_env_defaults_to_spec1_home(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = home_and_elsewhere
    monkeypatch.delenv("SPEC1_STORE_PATH", raising=False)
    monkeypatch.delenv("SPEC1_DB_PATH", raising=False)
    assert resolve_store_path() == home / "spec1_intelligence.jsonl"
    assert resolve_db_path() == home / "spec1.db"


def test_run_cycle_writes_both_files_under_spec1_home(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec1_core.app.cycle import run_cycle

    home, elsewhere = home_and_elsewhere
    monkeypatch.setenv("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    monkeypatch.setenv("SPEC1_DB_PATH", "spec1.db")

    summary = run_cycle(feeds={}, verbose=False, triage_only=True)

    assert summary["store_path"] == str(home / "spec1_intelligence.jsonl")
    assert (home / "spec1.db").is_file()
    assert not (elsewhere / "spec1.db").exists()
    assert not (elsewhere / "spec1_intelligence.jsonl").exists()


def test_api_dependencies_anchor_relative_env(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec1_api import dependencies

    home, elsewhere = home_and_elsewhere
    monkeypatch.setenv("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    monkeypatch.setenv("SPEC1_DB_PATH", "spec1.db")
    dependencies.get_intel_store.cache_clear()
    dependencies.get_database.cache_clear()
    try:
        assert Path(dependencies.get_intel_store().path) == home / "spec1_intelligence.jsonl"
        dependencies.get_database()
        assert (home / "spec1.db").is_file()
        assert not (elsewhere / "spec1.db").exists()
    finally:
        dependencies.get_intel_store.cache_clear()
        dependencies.get_database.cache_clear()


def test_engine_config_default_store_anchored(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from spec1_core.core.engine import EngineConfig

    home, _ = home_and_elsewhere
    monkeypatch.setenv("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    assert EngineConfig().store_path == home / "spec1_intelligence.jsonl"


def test_provenance_round_trips_jsonl_and_sqlite(tmp_path: Path) -> None:
    record = {
        "record_id": "rec-prov-rt-1",
        "run_id": "run-prov-rt",
        "signal_source": "reuters",
        "source_type": "rss",
        "classification": "INVESTIGATE",
        "confidence": 0.82,
        "environment": "test",
        "schema_version": 2,
        "harvester_version": "0.8.0",
        "raw_sha256": "a" * 64,
        "signal_published_at": "2026-11-17T12:00:00+00:00",
    }
    dw = DualWriter(
        jsonl_path=tmp_path / "intel.jsonl",
        db=Database(tmp_path / "spec1.db"),
        table="intelligence_records",
    )
    dw.write(record)

    (line,) = (tmp_path / "intel.jsonl").read_text(encoding="utf-8").splitlines()
    from_jsonl = json.loads(line)
    from_db = dw.repo.get("rec-prov-rt-1")
    assert from_db is not None
    for key in ("schema_version", "harvester_version", "raw_sha256",
                "signal_published_at", "source_type"):
        assert from_jsonl[key] == record[key]
        assert from_db[key] == record[key], key


def test_mirror_pending_lines_are_key_sorted(tmp_path: Path) -> None:
    dw = DualWriter(
        jsonl_path=tmp_path / "intel.jsonl",
        db=Database(tmp_path / "spec1.db"),
        table="intelligence_records",
    )
    with patch.object(dw.repo, "insert", side_effect=RuntimeError("db locked")):
        dw.write({"record_id": "rec-sort-1", "run_id": "run-1"})
    (line,) = dw.mirror_pending_path.read_text(encoding="utf-8").splitlines()
    assert line == json.dumps(json.loads(line), sort_keys=True)


# ── Non-standard stores get their own <stem>.db (follow-up a) ────────────────

_PAD = (" Investigators reviewed contract records, payment ledgers, committee testimony and"
        " agency correspondence; reporters confirmed dates with court dockets and filings.") * 6
_TEXTS = [
    "Senate oversight committee issued a subpoena on defense fuel contracts." + _PAD,
    "Treasury sanctions designate shipping firms tied to an evasion network." + _PAD,
]


def _offline_harvest(feeds=None, run_id="", environment="production", timeout=15):
    from datetime import datetime, timezone

    from spec1_core.schemas.models import Signal

    return {
        "signals": [
            Signal(signal_id=f"sig-iso-{i}", source="lawfare", source_type="rss", text=t,
                   url=f"https://example.invalid/{i}", author="staff",
                   published_at=datetime(2026, 11, 18, 12, i, tzinfo=timezone.utc),
                   velocity=0.9, engagement=0.8, run_id=run_id, environment=environment)
            for i, t in enumerate(_TEXTS)
        ],
        "errors": {},
    }


def _fingerprint(path: Path) -> list[tuple[str, str, int] | tuple[str, None]]:
    """sha256 + mtime of the DB file and its WAL sidecars (absent ones as None)."""
    import hashlib

    out: list[tuple[str, str, int] | tuple[str, None]] = []
    for f in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        out.append(
            (f.name, hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns)
            if f.exists() else (f.name, None)
        )
    return out


def test_temp_store_cycle_leaves_main_db_untouched(
    home_and_elsewhere: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    import spec1_core.app.cycle as cycle
    from cls_db.migrate import ensure_schema

    home, elsewhere = home_and_elsewhere
    monkeypatch.delenv("SPEC1_DB_PATH", raising=False)
    monkeypatch.delenv("SPEC1_STORE_PATH", raising=False)
    main_db = home / "spec1.db"
    setup = Database(main_db)
    ensure_schema(setup)
    setup.close()  # no open connection may checkpoint into the file later
    before = _fingerprint(main_db)

    monkeypatch.setattr(cycle, "harvest_all", _offline_harvest)
    temp_store = tmp_path / "scratch" / "tmp_test_intelligence.jsonl"
    summary = cycle.run_cycle(store_path=temp_store, verbose=False, triage_only=True)

    assert summary["records_stored"] == len(_TEXTS)
    assert _fingerprint(main_db) == before
    stem_db = temp_store.with_name("tmp_test_intelligence.db")
    with sqlite3.connect(stem_db) as conn:
        assert conn.execute("SELECT count(*) FROM intelligence_records").fetchone()[0] == len(_TEXTS)
    assert not (elsewhere / "spec1.db").exists()


def test_db_path_rules_for_standard_and_custom_stores(
    home_and_elsewhere: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, _ = home_and_elsewhere
    monkeypatch.delenv("SPEC1_DB_PATH", raising=False)
    main = home / "spec1.db"
    assert resolve_db_path(store_path=home / "spec1_intelligence.jsonl") == main
    assert resolve_db_path(store_path=home / "spec1_legislative.jsonl") == main
    assert resolve_db_path() == main

    monkeypatch.setenv("SPEC1_STORE_PATH", "data/spec1_intelligence.jsonl")
    assert resolve_db_path(store_path=resolve_store_path()) == home / "data" / "spec1_intelligence.db"

    custom = tmp_path / "x" / "probe.jsonl"
    assert resolve_db_path(store_path=custom) == custom.with_name("probe.db")
    monkeypatch.setenv("SPEC1_DB_PATH", "explicit.db")
    assert resolve_db_path(store_path=custom) == home / "explicit.db"


def test_mcp_store_path_anchors_relative_env(
    home_and_elsewhere: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    mcp_server = importlib.import_module("mcp_server")
    home, _ = home_and_elsewhere
    monkeypatch.setenv("SPEC1_VERDICTS_PATH", "verdicts.jsonl")
    monkeypatch.delenv("SPEC1_STORE_PATH", raising=False)
    assert mcp_server._store_path("SPEC1_VERDICTS_PATH", "unused.jsonl") == home / "verdicts.jsonl"
    assert mcp_server._store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl") == home / "spec1_intelligence.jsonl"
    absolute = home / "abs" / "v.jsonl"
    monkeypatch.setenv("SPEC1_VERDICTS_PATH", str(absolute))
    assert mcp_server._store_path("SPEC1_VERDICTS_PATH", "unused.jsonl") == absolute
