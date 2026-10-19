"""Hand-off path: cycle data → one file → Claude in chat writes the brief. No API key."""

from __future__ import annotations

import sys

from spec1_core.briefing import generator, writer
from spec1_core.briefing.generator import build_brief_prompts, generate_brief, handoff_doc
from spec1_core.tools import generate_brief as tool

RECORDS = [
    {"run_id": "run-h1", "record_id": "r1", "signal_source": "rand", "classification": "ESCALATE",
     "confidence": 0.8, "signal_url": "https://example.org/a", "written_at": "2026-10-19T20:40:00+00:00",
     "summary": "Sanctions evasion via ship-to-ship transfer."},
    {"run_id": "run-h1", "record_id": "r2", "signal_source": "csis", "classification": "MONITOR",
     "confidence": 0.4, "signal_url": "https://example.org/b", "written_at": "2026-10-19T20:40:00+00:00",
     "summary": "Fuel depot activity near the border."},
]
STATS = {"run_id": "run-h1", "finished_at": "2026-10-19T20:40:00+00:00", "records_stored": 2}


def test_handoff_carries_the_same_prompts_the_api_gets():
    sys_prompt, user_prompt = build_brief_prompts(RECORDS, STATS)
    doc = handoff_doc(RECORDS, STATS)
    assert sys_prompt.strip() in doc
    assert user_prompt.strip() in doc
    assert "run-h1" in doc


def test_no_key_still_returns_prompts(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    brief, prompts = generate_brief(RECORDS, STATS)
    assert brief  # rule-based fallback
    assert "## SYSTEM PROMPT" in prompts and "## USER PROMPT" in prompts


def test_handoff_does_not_need_the_anthropic_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # import would fail
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert handoff_doc(RECORDS, STATS)
    assert generate_brief(RECORDS, STATS)[0]


def test_write_handoff_dated_and_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(writer, "BRIEFS_DIR", tmp_path)
    path = writer.write_handoff("doc", "2026-10-19T20:40:00+00:00")
    assert path.endswith("spec1_handoff_2026-10-19.md")
    assert (tmp_path / "spec1_handoff_latest.md").read_text() == "doc"


def test_cli_handoff_writes_file_and_skips_claude(tmp_path, monkeypatch):
    import json
    store = tmp_path / "intel.jsonl"
    store.write_text("\n".join(json.dumps(r) for r in RECORDS))
    called = []
    monkeypatch.setattr(generator, "generate_brief", lambda *a, **k: called.append(1))
    rc = tool.main(["--intel", str(store), "--run-id", "run-h1", "--out-dir", str(tmp_path), "--handoff"])
    assert rc == 0 and not called
    assert "## 2. This run" in (tmp_path / "spec1_handoff_run-h1.md").read_text()
