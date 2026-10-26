"""analysis_tier stamping, triage-only cycles and the publish guard (audit 2026-10-24).

Decision: rule-based output must never be mistaken for model analysis.
  - every Outcome / stored record carries analysis_tier (llm_verified | rule_based)
  - --triage-only (GitHub Actions) never calls a model and writes no brief/PDF
  - a brief publishes only if its provenance sidecar says llm_verified
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import feedparser
import pytest

from spec1_core.app.cycle import run_cycle
from spec1_core.briefing import writer
from spec1_core.intelligence.store import JsonlStore
from spec1_core.investigation.verifier import verify_investigation
from spec1_core.llm.fallback_client import FallbackLLMClient
from spec1_core.schemas.models import Investigation, Outcome
from spec1_labels import (
    ANALYSIS_TIER_LLM_VERIFIED,
    ANALYSIS_TIER_RULE_BASED,
    BRIEF_RULE_FALLBACK_NOTE,
    BRIEF_SOURCE_HAND_WRITTEN,
    BRIEF_SOURCE_MODEL,
    BRIEF_SOURCE_RULES,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

_VERDICT = json.dumps({"verified": True, "confidence": 0.8, "reasoning": "Named official.",
                       "classification": "ESCALATE"})

_ITEM = """
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>Analysis of Russian military intelligence operations in Ukraine. NATO alliance
      defense strategy and nuclear deterrence reviewed. Cyber warfare threat assessment confirmed by
      Pentagon officials in a detailed security report on alliance operations.</description>
      <pubDate>{pub}</pubDate>
    </item>"""


def _feed():
    pub = format_datetime(datetime.now(timezone.utc) - timedelta(hours=1))
    body = "".join(_ITEM.format(title=t, link=u, pub=pub) for t, u in (
        ("Russia Military Intelligence Update", "https://example.com/t1"),
        ("NATO Defense Posture Review", "https://example.com/t2")))
    return feedparser.parse(
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>{body}</channel></rss>')


def _investigation() -> Investigation:
    return Investigation(investigation_id="inv-1", opportunity_id="opp-1",
                         hypothesis="Something happened", queries=[], sources_to_check=[],
                         analyst_leads=[])


def _outcome(tier: str) -> Outcome:
    return Outcome(outcome_id="o", classification="ESCALATE", confidence=0.8,
                   evidence=["LLM assessment: x"], analysis_tier=tier)


# ── Verifier / fallback client ────────────────────────────────────────────────

def test_outcome_defaults_to_rule_based():
    assert Outcome("o", "INVESTIGATE", 0.5, []).analysis_tier == ANALYSIS_TIER_RULE_BASED


def test_verifier_triage_mode_never_builds_a_client():
    with patch("spec1_core.llm.fallback_client.FallbackLLMClient",
               side_effect=AssertionError("model must not be tried in triage mode")):
        out = verify_investigation(_investigation(), article="text", use_llm=False)
    assert out.analysis_tier == ANALYSIS_TIER_RULE_BASED


@pytest.mark.parametrize("backend,expected", [
    ("local", ANALYSIS_TIER_LLM_VERIFIED),
    ("claude", ANALYSIS_TIER_LLM_VERIFIED),
])
def test_verifier_stamps_real_model_as_verified(monkeypatch, backend, expected):
    monkeypatch.setattr(FallbackLLMClient, "_backend_complete", lambda self, b, p, s: _VERDICT)
    monkeypatch.setattr("spec1_core.llm.fallback_client.resolve_route",
                        lambda task, dev_mode=False: [backend, "mock"])
    out = verify_investigation(_investigation(), article="text")
    assert out.analysis_tier == expected
    assert out.classification == "ESCALATE"


def test_verifier_stamps_tier3_fallback_as_rule_based(monkeypatch):
    def _fail(self, b, p, s):
        raise RuntimeError("down")
    monkeypatch.setattr(FallbackLLMClient, "_backend_complete", _fail)
    out = verify_investigation(_investigation(), article="text")
    assert out.analysis_tier == ANALYSIS_TIER_RULE_BASED


def test_complete_records_the_tier_that_answered(monkeypatch):
    monkeypatch.setattr(FallbackLLMClient, "_backend_complete", lambda self, b, p, s: "{}")
    monkeypatch.setattr("spec1_core.llm.fallback_client.resolve_route",
                        lambda task, dev_mode=False: ["local", "mock"])
    c = FallbackLLMClient(task="analyze")
    c.complete("p")
    # Default local backend is Ollama; it used to stay at its initial "claude".
    assert c.get_active_tier() == "ollama"


# ── Cycle ─────────────────────────────────────────────────────────────────────

def _cycle(tmp_path, **kw) -> dict:
    with patch("spec1_core.signal.harvester.feedparser.parse", return_value=_feed()):
        return run_cycle(store_path=tmp_path / "intel.jsonl", run_id="run-tier", environment="test",
                         feeds={"rand": "https://example.com/feed"}, verbose=False, **kw)


def test_triage_only_cycle(tmp_path):
    with patch("spec1_core.llm.fallback_client.FallbackLLMClient",
               side_effect=AssertionError("triage-only must not try a model")), \
         patch("spec1_core.briefing.generator.generate_brief",
               side_effect=AssertionError("triage-only must not write a brief")):
        stats = _cycle(tmp_path, triage_only=True)
    assert stats["mode"] == "triage_only"
    assert stats["records_stored"] > 0
    records = JsonlStore(tmp_path / "intel.jsonl").read_all()
    assert {r["analysis_tier"] for r in records} == {ANALYSIS_TIER_RULE_BASED}
    assert stats["records_tier"] == ANALYSIS_TIER_RULE_BASED
    assert "brief_path" not in stats and "publication_path" not in stats
    assert not list(writer.BRIEFS_DIR.glob("*.md")) if writer.BRIEFS_DIR.exists() else True


def test_full_cycle_with_model_writes_publishable_sidecar(tmp_path):
    with patch("spec1_core.app.cycle.verify_investigation",
               return_value=_outcome(ANALYSIS_TIER_LLM_VERIFIED)), \
         patch("spec1_core.briefing.generator.generate_brief", return_value=("# Brief\n\nModel text.", "")):
        stats = _cycle(tmp_path)
    records = JsonlStore(tmp_path / "intel.jsonl").read_all()
    assert {r["analysis_tier"] for r in records} == {ANALYSIS_TIER_LLM_VERIFIED}
    meta = writer.read_brief_meta(stats["brief_path"])
    assert meta["analysis_tier"] == ANALYSIS_TIER_LLM_VERIFIED
    assert meta["brief_source"] == BRIEF_SOURCE_MODEL
    assert writer.publish_block_reason(stats["brief_path"]) is None
    # The _latest alias carries the same provenance.
    latest = Path(stats["brief_path"]).with_name("spec1_brief_latest.md")
    assert writer.publish_block_reason(latest) is None


def test_full_cycle_without_model_is_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("spec1_core.app.cycle.verify_investigation",
               return_value=_outcome(ANALYSIS_TIER_RULE_BASED)):
        stats = _cycle(tmp_path)
    meta = writer.read_brief_meta(stats["brief_path"])
    assert meta["records_tier"] == ANALYSIS_TIER_RULE_BASED
    assert meta["brief_source"] == BRIEF_SOURCE_RULES
    assert "rule_based" in writer.publish_block_reason(stats["brief_path"])


def test_hand_written_brief_over_verified_records_publishes(tmp_path, monkeypatch):
    # Kali flow: Qwen verifies the records, no API key so the cycle's own brief
    # is the rule fallback, then Claude writes the brief by hand from the handoff.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("spec1_core.app.cycle.verify_investigation",
               return_value=_outcome(ANALYSIS_TIER_LLM_VERIFIED)):
        stats = _cycle(tmp_path)
    assert writer.publish_block_reason(stats["brief_path"])          # fallback text: blocked
    Path(stats["brief_path"]).write_text("# World State Brief\n\nWritten by hand from the handoff.\n",
                                         encoding="utf-8")
    writer.mark_hand_written(stats["brief_path"])
    assert writer.publish_block_reason(stats["brief_path"]) is None  # hand-written: allowed


def test_marking_the_fallback_text_hand_written_stays_blocked(tmp_path, monkeypatch):
    # Marking is a claim about the text. If the text is still the rule fallback, refuse.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("spec1_core.app.cycle.verify_investigation",
               return_value=_outcome(ANALYSIS_TIER_LLM_VERIFIED)):
        stats = _cycle(tmp_path)
    writer.mark_hand_written(stats["brief_path"])
    assert "rule-based fallback" in writer.publish_block_reason(stats["brief_path"])


def _labelled(tmp_path, text, record_tiers):
    brief = tmp_path / "spec1_brief_2026-10-25.md"
    brief.write_text(text, encoding="utf-8")
    writer.meta_path_for(brief).write_text(json.dumps({
        "run_id": "run-8a88a4bd2e23", "records_tier": ANALYSIS_TIER_LLM_VERIFIED,
        "brief_source": BRIEF_SOURCE_HAND_WRITTEN, "record_tiers": record_tiers,
        "analysis_tier": ANALYSIS_TIER_LLM_VERIFIED}), encoding="utf-8")
    return brief


def test_label_without_verified_records_is_blocked(tmp_path):
    # 2026-10-25: sidecar said llm_verified/hand_written with record_tiers {} and was published.
    brief = _labelled(tmp_path, "# Brief\n\nBody.\n", {})
    assert "no llm_verified records" in writer.publish_block_reason(brief)


def test_rule_based_records_in_counts_are_blocked(tmp_path):
    brief = _labelled(tmp_path, "# Brief\n\nBody.\n",
                      {ANALYSIS_TIER_LLM_VERIFIED: 5, ANALYSIS_TIER_RULE_BASED: 2})
    assert "not llm_verified" in writer.publish_block_reason(brief)


def test_fallback_text_under_verified_label_is_blocked(tmp_path):
    text = ("## SPEC-1 DAILY BRIEF — 2026-10-25\n\n*AI brief unavailable — API call failed. "
            f"{BRIEF_RULE_FALLBACK_NOTE}.*\n")
    brief = _labelled(tmp_path, text, {ANALYSIS_TIER_LLM_VERIFIED: 3})
    assert "rule-based fallback" in writer.publish_block_reason(brief)


@pytest.mark.parametrize("leak", [
    "cannot import name 'X' (/home/mjlak/spec-1/src/spec1_core/llm/fallback_client.py)",
    "saved to C:\\Users\\mjlak\\Downloads\\brief.md",
    "see /Users/matt/notes.md",
])
def test_local_paths_in_brief_are_blocked(tmp_path, leak):
    brief = _labelled(tmp_path, f"# Brief\n\n{leak}\n", {ANALYSIS_TIER_LLM_VERIFIED: 3})
    assert "local file path" in writer.publish_block_reason(brief)


def test_urls_with_home_segments_are_not_paths(tmp_path):
    brief = _labelled(tmp_path, "# Brief\n\nSource: https://example.org/home/user/report\n",
                      {ANALYSIS_TIER_LLM_VERIFIED: 3})
    assert writer.publish_block_reason(brief) is None


def test_hand_written_brief_over_rule_based_records_stays_blocked(tmp_path):
    brief = tmp_path / "spec1_brief_2026-10-24.md"
    brief.write_text("# x\n")
    writer.write_brief_meta(brief, run_id="r", records_tier=ANALYSIS_TIER_RULE_BASED,
                            brief_source=BRIEF_SOURCE_RULES)
    writer.mark_hand_written(brief)
    assert writer.publish_block_reason(brief)


def test_missing_sidecar_is_blocked(tmp_path):
    brief = tmp_path / "spec1_brief_2026-10-24.md"
    brief.write_text("# x\n")
    assert "no provenance sidecar" in writer.publish_block_reason(brief)


# ── Publisher script ──────────────────────────────────────────────────────────

def _inject_module():
    spec = importlib.util.spec_from_file_location(
        "inject_brief_to_template", REPO_ROOT / "scripts" / "inject_brief_to_template.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("tier,expect_rc", [
    (None, 1),                          # no sidecar
    (ANALYSIS_TIER_RULE_BASED, 1),
    (ANALYSIS_TIER_LLM_VERIFIED, 0),
])
def test_publisher_script_guard(tmp_path, tier, expect_rc):
    brief = tmp_path / "spec1_brief_latest.md"
    brief.write_text("# Brief\n\nBody.\n")
    if tier is not None:
        (tmp_path / "spec1_brief_latest.meta.json").write_text(json.dumps(
            {"analysis_tier": tier, "record_tiers": {tier: 3}}))
    template = tmp_path / "t.html"
    template.write_text("<html><body><div class=\"seal\"></div></body></html>")
    out = tmp_path / "out" / "pub.html"
    rc = _inject_module().main(["--brief", str(brief), "--template", str(template),
                                "--out", str(out), "--date", "2026-10-24"])
    assert rc == expect_rc
    assert out.exists() == (expect_rc == 0)


def test_writer_check_cli_exit_codes(tmp_path):
    import subprocess
    import sys
    brief = tmp_path / "spec1_brief_2026-10-24.md"
    brief.write_text("# x\n")
    writer.write_brief_meta(brief, run_id="r", records_tier=ANALYSIS_TIER_RULE_BASED,
                            brief_source=BRIEF_SOURCE_RULES)
    rc = subprocess.run([sys.executable, "-m", "spec1_core.briefing.writer", "--check", str(brief)],
                        cwd=REPO_ROOT, env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": ""},
                        capture_output=True, text=True)
    assert rc.returncode == 1 and "REFUSED" in rc.stdout


# ── Publication issue counter ─────────────────────────────────────────────────

def test_issue_counter_continues_from_restored_issues(tmp_path):
    from spec1_core.tools import publication_generator as pg
    out = tmp_path / "generated" / "briefs"
    out.mkdir(parents=True)
    (out / "spec1_issue_001_2026-10-23.pdf").write_bytes(b"%PDF")
    (out / "spec1_issue_007_2026-10-23.pdf").write_bytes(b"%PDF")
    path = pg.generate_publication(records=[], brief_text="# x", cycle_stats={"run_id": "r"},
                                   output_dir=str(out))
    assert "spec1_issue_008_" in Path(path).name
