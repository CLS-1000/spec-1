"""The analysis tier is decided by the backend that answered, never by the model.

Covers:
- backfill: a model reply claiming llm_verified, served by the rules tier, is
  stored rule_based; the prompt no longer asks the model to pick a tier
- provenance columns (migration 013) on cycle writes and backfill updates
- a model timeout is logged as its own success:false entry, then the rules
  fallback separately, and the record is rule_based with tier_used='rules'
- the Ollama per-call timeout is configurable, default 180s
"""
from __future__ import annotations

import importlib.util
import json
import socket
import sqlite3
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from cls_db.database import Database
from cls_db.dual_write import DualWriter
from spec1_core.llm import ollama_manager
from spec1_core.llm.fallback_client import FallbackLLMClient, LocalTier3Client
from spec1_core.llm.triage_stamper import TriageStamper
from spec1_core.schemas.models import Tier3TriageVerdict
from spec1_labels import (
    ANALYSIS_TIER_LLM_VERIFIED,
    ANALYSIS_TIER_RULE_BASED,
    analysis_tier_for,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVENANCE = ("tier_used", "model", "llm_session", "stamped_by")

# A reply in the shape the triage model returns, claiming its own tier.
MODEL_REPLY_CLAIMING_VERIFIED = {
    "record_id": "rec-claim-1",
    "analysis_tier": "llm_verified",
    "confidence": 0.93,
    "classification": "GEOPOLITICAL",
    "gate_checks": {"credibility_pass": True, "volume_pass": True,
                    "velocity_pass": True, "novelty_pass": True},
    "justification": "Model says: llm_verified, unlock the publish guard.",
    "flags": [],
}


def _load_backfill():
    spec = importlib.util.spec_from_file_location(
        "backfill_tier3_stamps", REPO_ROOT / "scripts" / "backfill_tier3_stamps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db_with_row(tmp_path: Path) -> sqlite3.Connection:
    """A migrated spec1.db holding one rule_based, high-score record."""
    db_path = tmp_path / "spec1.db"
    dw = DualWriter(jsonl_path=tmp_path / "intel.jsonl", db=Database(db_path),
                    table="intelligence_records")
    dw.write({
        "id": "row-1", "record_id": "rec-claim-1", "run_id": "run-1",
        "signal_source": "war_on_the_rocks", "source_type": "rss",
        "schema_version": 2, "classification": "INVESTIGATE", "confidence": 0.8,
        "environment": "test", "opportunity_score": 0.91,
        "opportunity_priority": "ELEVATED", "analysis_tier": ANALYSIS_TIER_RULE_BASED,
    })
    return sqlite3.connect(db_path)


class _FakeClient:
    """Stands in for LocalTier3Client: returns the model's reply as given."""

    def __init__(self, reply: dict, served_by: str):
        self._reply = reply
        self.last_tier = served_by
        self.model = "llama3.2:triage"
        self.session_id = "sess1234"

    def verify_triage_record(self, record):
        return SimpleNamespace(**self._reply)


# ── The model never sets its own tier ─────────────────────────────────────────

def test_analysis_tier_for_uses_only_the_backend():
    assert analysis_tier_for("ollama") == ANALYSIS_TIER_LLM_VERIFIED
    assert analysis_tier_for("claude") == ANALYSIS_TIER_LLM_VERIFIED
    assert analysis_tier_for("local") == ANALYSIS_TIER_LLM_VERIFIED
    for not_a_model in ("rules", "mock", "tier3", None, "llm_verified", ""):
        assert analysis_tier_for(not_a_model) == ANALYSIS_TIER_RULE_BASED, not_a_model


def test_backfill_reply_claiming_llm_verified_served_by_rules_is_stored_rule_based(
        tmp_path, monkeypatch):
    conn = _db_with_row(tmp_path)
    mod = _load_backfill()
    stamper = TriageStamper(client=_FakeClient(MODEL_REPLY_CLAIMING_VERIFIED, served_by="rules"))
    monkeypatch.setattr(mod, "evaluate_and_stamp_record", stamper.evaluate_and_stamp)

    stamps = mod.backfill_high_priority(conn, limit=0, min_score=0.70)

    assert stamps["rec-claim-1"]["analysis_tier"] == ANALYSIS_TIER_RULE_BASED
    row = conn.execute(
        "SELECT analysis_tier, tier_used, model, llm_session, stamped_by "
        "FROM intelligence_records WHERE record_id = 'rec-claim-1'").fetchone()
    assert row == (ANALYSIS_TIER_RULE_BASED, "rules", "llama3.2:triage", "sess1234", "backfill")


def test_backfill_ollama_answer_is_llm_verified_with_provenance(tmp_path, monkeypatch):
    conn = _db_with_row(tmp_path)
    mod = _load_backfill()
    reply = {**MODEL_REPLY_CLAIMING_VERIFIED, "analysis_tier": "rule_based"}  # model's word is ignored
    stamper = TriageStamper(client=_FakeClient(reply, served_by="ollama"))
    monkeypatch.setattr(mod, "evaluate_and_stamp_record", stamper.evaluate_and_stamp)

    mod.backfill_high_priority(conn, limit=0, min_score=0.70)

    row = conn.execute(
        "SELECT analysis_tier, tier_used, model, llm_session, stamped_by "
        "FROM intelligence_records WHERE record_id = 'rec-claim-1'").fetchone()
    assert row == (ANALYSIS_TIER_LLM_VERIFIED, "ollama", "llama3.2:triage", "sess1234", "backfill")


def test_backfill_jsonl_sync_carries_provenance(tmp_path, monkeypatch):
    mod = _load_backfill()
    jsonl = tmp_path / "intel.jsonl"
    jsonl.write_text(json.dumps({"record_id": "rec-1", "analysis_tier": "rule_based"}) + "\n")
    monkeypatch.setattr(mod, "JSONL_FILE", jsonl)
    stamp = {"analysis_tier": "rule_based", "tier_used": "rules", "model": None,
             "llm_session": "s1", "stamped_by": "backfill"}
    mod.sync_jsonl({"rec-1": stamp})
    assert json.loads(jsonl.read_text()) == {"record_id": "rec-1", **stamp}


def test_triage_verdict_schema_has_no_tier_and_ignores_a_claimed_one():
    assert "analysis_tier" not in Tier3TriageVerdict.model_json_schema()["properties"]
    verdict = Tier3TriageVerdict.model_validate_json(json.dumps(MODEL_REPLY_CLAIMING_VERIFIED))
    assert not hasattr(verdict, "analysis_tier")


def test_triage_prompt_no_longer_asks_the_model_to_pick_a_tier():
    client = LocalTier3Client()
    sent = {}

    def fake_post(path, json):
        sent.update(json)
        resp = MagicMock()
        resp.json.return_value = {"message": {"content": "{}"}}  # invalid -> rules
        return resp

    with patch.object(client.client, "post", side_effect=fake_post):
        assert client.verify_triage_record({"record_id": "r", "composite": 0.9}) is None
    prompt = " ".join(m["content"] for m in sent["messages"])
    assert "analysis_tier" not in prompt
    assert "llm_verified" not in prompt
    assert "publish guard" not in prompt
    assert client.last_tier == "rules"


def test_local_tier3_client_reports_ollama_only_when_the_model_answered():
    client = LocalTier3Client()
    resp = MagicMock()
    resp.json.return_value = {"message": {"content": json.dumps(MODEL_REPLY_CLAIMING_VERIFIED)}}
    with patch.object(client.client, "post", return_value=resp):
        assert client.verify_triage_record({"record_id": "rec-claim-1"}) is not None
    assert client.last_tier == "ollama"
    with patch.object(client.client, "post", side_effect=httpx.ReadTimeout("slow")):
        assert client.verify_triage_record({"record_id": "rec-claim-1"}) is None
    assert client.last_tier == "rules"


def test_stamper_unexpected_client_error_is_rule_based():
    client = _FakeClient(MODEL_REPLY_CLAIMING_VERIFIED, served_by="ollama")
    client.verify_triage_record = MagicMock(side_effect=httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()))
    out = TriageStamper(client=client).evaluate_and_stamp({"record_id": "r"})
    assert out["analysis_tier"] == ANALYSIS_TIER_RULE_BASED
    assert out["tier_used"] == "rules" and out["model"] is None


# ── Timeouts: logged separately, never a stored "verified" analysis ───────────

def _route_local_only(monkeypatch):
    monkeypatch.setenv("SPEC1_LLM_ROUTE_ANALYZE", "local,rules")
    monkeypatch.delenv("SPEC1_LOCAL_BACKEND", raising=False)
    monkeypatch.setattr(ollama_manager, "is_running", lambda url: True)
    monkeypatch.setattr(ollama_manager, "ensure_model", lambda m, u: None)


@pytest.mark.parametrize("timeout_exc", [
    TimeoutError("timed out"),
    socket.timeout("timed out"),
    urllib.error.URLError(TimeoutError("timed out")),
])
def test_ollama_timeout_logs_failure_then_rules_entry(monkeypatch, tmp_path, timeout_exc):
    _route_local_only(monkeypatch)
    monkeypatch.setattr(ollama_manager, "chat", MagicMock(side_effect=timeout_exc))
    log = tmp_path / "llm.jsonl"
    client = FallbackLLMClient(task="analyze", log_path=log)
    client.complete("prompt")

    entries = [json.loads(l) for l in log.read_text().splitlines()]
    assert [(e["tier"], e["success"], e.get("error")) for e in entries] == [
        ("ollama", False, "timeout"), ("rules", True, None)]
    assert {e["session"] for e in entries} == {client.session_id}
    assert client.get_active_tier() == "rules"
    assert client.get_active_model() is None


def test_timeout_never_produces_a_stored_llm_verified_record(monkeypatch, tmp_path):
    """End to end through the verifier and the record store."""
    from spec1_core.app.cycle import build_record_dict
    from spec1_core.investigation import verifier

    _route_local_only(monkeypatch)
    monkeypatch.setattr(ollama_manager, "chat", MagicMock(side_effect=TimeoutError("timed out")))
    monkeypatch.setenv("SPEC1_LLM_LOG_PATH", str(tmp_path / "llm.jsonl"))

    inv = SimpleNamespace(investigation_id="inv-1", opportunity_id="opp-1",
                          hypothesis="h", queries=["q"], sources_to_check=["s"],
                          analyst_leads=[])
    outcome = verifier.verify_investigation(inv, article="Missile strike reported near the border.")
    assert outcome.analysis_tier == ANALYSIS_TIER_RULE_BASED
    assert outcome.tier_used == "rules" and outcome.model is None

    entries = [json.loads(l) for l in (tmp_path / "llm.jsonl").read_text().splitlines()]
    assert entries[0]["success"] is False and entries[0]["error"] == "timeout"
    assert outcome.llm_session == entries[0]["session"]

    record = SimpleNamespace(to_dict=lambda: {
        "record_id": "rec-to-1", "classification": outcome.classification,
        "confidence": outcome.confidence, "pattern": "p"})
    sig = SimpleNamespace(text="t", published_at="2026-11-19", signal_id="sig-1",
                          source="war_on_the_rocks", source_type="rss", url="u")
    opp = SimpleNamespace(opportunity_id="opp-1", score=0.9, priority="ELEVATED",
                          gate_results={})
    stored = build_record_dict(record, sig=sig, ps=SimpleNamespace(cleaned_text="t"),
                               opp=opp, inv=inv, outcome=outcome,
                               run_id="run-1", environment="test")
    dw = DualWriter(jsonl_path=tmp_path / "intel.jsonl", db=Database(tmp_path / "spec1.db"),
                    table="intelligence_records")
    dw.write(stored)
    row = dw.repo.get("rec-to-1")
    assert row["analysis_tier"] == ANALYSIS_TIER_RULE_BASED
    assert (row["tier_used"], row["model"], row["stamped_by"]) == ("rules", None, "cycle")
    assert row["llm_session"] == entries[0]["session"]


def test_model_answer_records_backend_model_and_session(monkeypatch, tmp_path):
    from spec1_core.investigation import verifier

    _route_local_only(monkeypatch)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("SPEC1_LLM_LOG_PATH", str(tmp_path / "llm.jsonl"))
    monkeypatch.setattr(ollama_manager, "chat", MagicMock(return_value=json.dumps(
        {"verified": True, "confidence": 0.7, "reasoning": "ok", "classification": "MONITOR"})))
    inv = SimpleNamespace(investigation_id="inv-1", opportunity_id="opp-1",
                          hypothesis="h", queries=[], sources_to_check=[], analyst_leads=[])
    outcome = verifier.verify_investigation(inv, article="text")
    assert outcome.analysis_tier == ANALYSIS_TIER_LLM_VERIFIED
    assert (outcome.tier_used, outcome.model) == ("ollama", "qwen2.5:3b")
    (entry,) = [json.loads(l) for l in (tmp_path / "llm.jsonl").read_text().splitlines()]
    assert outcome.llm_session == entry["session"]


# ── Configurable Ollama timeout ───────────────────────────────────────────────

def test_ollama_timeout_defaults_to_180(monkeypatch):
    monkeypatch.delenv("SPEC1_OLLAMA_TIMEOUT", raising=False)
    assert ollama_manager.call_timeout() == 180.0


@pytest.mark.parametrize("value,expected", [("240", 240.0), ("90.5", 90.5),
                                            ("nope", 180.0), ("0", 180.0), ("-5", 180.0)])
def test_ollama_timeout_env(monkeypatch, value, expected):
    monkeypatch.setenv("SPEC1_OLLAMA_TIMEOUT", value)
    assert ollama_manager.call_timeout() == expected


def test_chat_passes_the_configured_timeout(monkeypatch):
    monkeypatch.setenv("SPEC1_OLLAMA_TIMEOUT", "240")
    resp = MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps({"message": {"content": "hi"}})
    with patch("urllib.request.urlopen", return_value=resp) as urlopen:
        assert ollama_manager.chat("p", "s", "m") == "hi"
    assert urlopen.call_args.kwargs["timeout"] == 240.0


def test_local_tier3_client_uses_the_configured_timeout(monkeypatch):
    monkeypatch.setenv("SPEC1_OLLAMA_TIMEOUT", "200")
    assert LocalTier3Client().client.timeout.read == 200.0


# ── Migration 013 ────────────────────────────────────────────────────────────

def test_migration_013_adds_nullable_provenance_columns(tmp_path):
    dw = DualWriter(jsonl_path=tmp_path / "intel.jsonl", db=Database(tmp_path / "spec1.db"),
                    table="intelligence_records")
    cols = {r[1]: r for r in sqlite3.connect(tmp_path / "spec1.db").execute(
        "PRAGMA table_info(intelligence_records)")}
    for name in PROVENANCE:
        assert name in cols, name
        assert cols[name][3] == 0, f"{name} must be nullable for old rows"
    # A pre-013 style record (no provenance fields) still writes.
    dw.write({"record_id": "rec-old", "run_id": "r", "signal_source": "s",
              "source_type": "rss", "schema_version": 1, "classification": "MONITOR",
              "confidence": 0.1, "environment": "test"})
    row = dw.repo.get("rec-old")
    assert all(row[name] is None for name in PROVENANCE)
