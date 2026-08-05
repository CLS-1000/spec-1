# @domain:   spec-1
# @module:   test_brief_gate
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the publishable-brief gate.

The gate is what stops a failed cycle from reaching the publication repo.
``generate_brief()`` never raises — it returns a stub and the cycle exits 0 —
so these cases are the only thing distinguishing a real brief from a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the .github/scripts directory is importable for testing
SCRIPTS_DIR = Path(__file__).parent.parent / ".github" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_brief_publishable import (  # noqa: E402
    DEFAULT_MAX_WORDS,
    DEFAULT_MIN_WORDS,
    check,
    main,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "spec1_brief_2026-08-04.md"
    path.write_text(text, encoding="utf-8")
    return path


def _real_brief(words: int = 900) -> str:
    return "## SPEC-1 DAILY BRIEF — 2026-08-04\n\n" + " ".join(["signal"] * words)


def test_real_brief_passes(tmp_path):
    ok, reason = check(_write(tmp_path, _real_brief()), DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert ok
    assert "looks real" in reason


def test_fallback_marker_is_rejected(tmp_path):
    """The exact stub _fallback_brief() emits."""
    brief = (
        "## SPEC-1 DAILY BRIEF — 2026-08-04\n\n"
        "[Brief generation failed. Raw stats: {'run_id': 'run-abc', 'records_stored': 513}]"
    )
    ok, reason = check(_write(tmp_path, brief), DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert not ok
    assert "fallback brief" in reason
    assert "ANTHROPIC_API_KEY" in reason


def test_fallback_rejected_even_when_dump_is_long(tmp_path):
    """Regression: the 2026-08-04 fallback was 32,971 words.

    Word count alone would not have caught it as "too short" — it has to be
    caught by the marker, and by the ceiling.
    """
    brief = (
        "## SPEC-1 DAILY BRIEF — 2026-08-04\n\n"
        "[Brief generation failed. Raw stats: {'records': "
        + " ".join(["x"] * 32_000)
        + "}]"
    )
    ok, reason = check(_write(tmp_path, brief), DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert not ok
    assert "fallback brief" in reason


def test_oversized_dump_rejected_without_marker(tmp_path):
    """A dump that loses the marker is still not a brief — MAX_TOKENS forbids it."""
    ok, reason = check(
        _write(tmp_path, _real_brief(words=DEFAULT_MAX_WORDS + 1)),
        DEFAULT_MIN_WORDS,
        DEFAULT_MAX_WORDS,
    )
    assert not ok
    assert "ceiling" in reason


def test_stub_below_floor_rejected(tmp_path):
    ok, reason = check(_write(tmp_path, "## Brief\n\ntoo short"), DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert not ok
    assert "floor" in reason


def test_missing_file_rejected(tmp_path):
    ok, reason = check(tmp_path / "absent.md", DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert not ok
    assert "wrote nothing" in reason


def test_boundaries_are_inclusive(tmp_path):
    """Exactly at the floor and ceiling is acceptable, not rejected."""
    at_floor = _write(tmp_path, " ".join(["w"] * DEFAULT_MIN_WORDS))
    assert check(at_floor, DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)[0]

    at_ceiling = _write(tmp_path, " ".join(["w"] * DEFAULT_MAX_WORDS))
    assert check(at_ceiling, DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)[0]


def test_main_exits_nonzero_on_failure(tmp_path, capsys):
    path = _write(tmp_path, "## Brief\n\n[Brief generation failed. Raw stats: {}]")
    assert main([str(path)]) == 1
    assert "::error::" in capsys.readouterr().out


def test_main_soft_mode_reports_without_failing(tmp_path, capsys):
    path = _write(tmp_path, "## Brief\n\n[Brief generation failed. Raw stats: {}]")
    assert main([str(path), "--soft"]) == 0
    out = capsys.readouterr().out
    assert "publishable=false" in out


def test_main_succeeds_on_real_brief(tmp_path, capsys):
    path = _write(tmp_path, _real_brief())
    assert main([str(path)]) == 0
    assert "publishable=true" in capsys.readouterr().out


def test_main_rejects_inverted_thresholds(tmp_path):
    path = _write(tmp_path, _real_brief())
    assert main([str(path), "--min-words", "500", "--max-words", "100"]) == 2


def test_step_output_written_when_under_actions(tmp_path, monkeypatch, capsys):
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    main([str(_write(tmp_path, _real_brief()))])
    written = out_file.read_text(encoding="utf-8")
    assert "publishable=true" in written
    assert "reason=" in written


@pytest.mark.parametrize("encoding_break", [b"\xff\xfe invalid", b"\x80\x81"])
def test_undecodable_bytes_do_not_crash(tmp_path, encoding_break):
    """A corrupt write should fail the gate, not raise."""
    path = tmp_path / "spec1_brief_2026-08-04.md"
    path.write_bytes(encoding_break)
    ok, _ = check(path, DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS)
    assert not ok
