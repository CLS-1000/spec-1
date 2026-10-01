# @domain:   spec-1
# @module:   spec1_dual_write_config
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Dual-write factory per module. Singleton pattern."""

from __future__ import annotations

from pathlib import Path

_WRITERS: dict = {}


def get_intel_writer(db_path: Path):
    """Intel signals dual-writer."""
    key = "intel"
    if key not in _WRITERS:
        from cls_db.dual_write import make_dual_writer
        _WRITERS[key] = make_dual_writer(
            jsonl_path=Path("data/signals.jsonl"),
            db_path=db_path / "signals.db",
            table="signals",
            pk_field="record_id",
        )
    return _WRITERS[key]


def get_leads_writer(db_path: Path):
    """Leads dual-writer."""
    key = "leads"
    if key not in _WRITERS:
        from cls_db.dual_write import make_dual_writer
        _WRITERS[key] = make_dual_writer(
            jsonl_path=Path("data/leads.jsonl"),
            db_path=db_path / "leads.db",
            table="leads",
            pk_field="record_id",
        )
    return _WRITERS[key]


def get_brief_writer(db_path: Path):
    """Brief dual-writer."""
    key = "brief"
    if key not in _WRITERS:
        from cls_db.dual_write import make_dual_writer
        _WRITERS[key] = make_dual_writer(
            jsonl_path=Path("data/brief.jsonl"),
            db_path=db_path / "brief.db",
            table="brief",
            pk_field="record_id",
        )
    return _WRITERS[key]


def get_psyop_writer(db_path: Path):
    """Psyop signals dual-writer."""
    key = "psyop"
    if key not in _WRITERS:
        from cls_db.dual_write import make_dual_writer
        _WRITERS[key] = make_dual_writer(
            jsonl_path=Path("data/psyop_signals.jsonl"),
            db_path=db_path / "psyop.db",
            table="psyop_signals",
            pk_field="record_id",
        )
    return _WRITERS[key]


def clear_all() -> None:
    """Reset all writers (for testing)."""
    _WRITERS.clear()
