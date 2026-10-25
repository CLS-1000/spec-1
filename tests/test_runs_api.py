# @domain:   spec-1
# @module:   test_runs_api
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the read-only runs index and /api/v1/runs routes (Triage Desk)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from spec1_api import runs_index

CYCLE_LOG = """\
============================================================
  SPEC-1 Intelligence Engine — Cycle Start
  run_id    : run-aaa
============================================================

[1/7] Harvesting RSS feeds...
      - nk_news: https://www.nknews.org/feed/
      - yonhap: https://en.yna.co.kr/RSS/news.xml
      Harvested 10 signals from 2 feeds

Run Summary:
  run_id: run-aaa
  started_at: 2026-10-24T16:28:27+00:00
  signals_harvested: 10
  signals_parsed: 9
  opportunities_found: 2
  outcomes_verified: 2
  records_stored: 2
  signals_skipped_seen: 5
  mode: triage_only
  errors: []
  finished_at: 2026-10-24T16:28:38+00:00
"""


def _gate(run_id, signal_id, source, passed, velocity=0.75):
    return {
        "run_id": run_id, "signal_id": signal_id, "source": source,
        "decision": "passed" if passed else "blocked",
        "failed_gates": [] if passed else ["velocity"],
        "gates": {
            "credibility": {"value": 0.85, "threshold": 0.65, "passed": True},
            "volume": {"value": 0.6, "threshold": 0.3, "passed": True},
            "velocity": {"value": velocity, "threshold": 0.5, "passed": passed},
            "novelty": {"value": 3, "threshold": 1, "passed": True, "score": 0.65},
        },
    }


def _rec(run_id, rid, sid, source, score, tier, **extra):
    rec = {
        "record_id": rid, "run_id": run_id, "signal_id": sid, "signal_source": source,
        "opportunity_score": score, "opportunity_priority": "STANDARD",
        "outcome_classification": "INVESTIGATE", "confidence": 0.6, "source_weight": 0.85,
        "gate_results": {"credibility": True, "volume": True, "velocity": True, "novelty": True},
        "written_at": "2026-10-24T16:28:38+00:00",
    }
    if tier is not None:
        rec["analysis_tier"] = tier
    rec.update(extra)
    return rec


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    logs = tmp_path / "logs"
    briefs = tmp_path / "briefs"
    logs.mkdir()
    briefs.mkdir()
    (logs / "cycle_20261024T162827Z.log").write_text(CYCLE_LOG, encoding="utf-8")
    (logs / "pdx1_2026_1024_191904.json").write_text(json.dumps({
        "run_id": "pdx1_2026_1024_191904",
        "started_at": "2026-10-25T02:19:04+00:00",
        "signals_harvested": 40, "signals_parsed": 38, "records_stored": 1,
        "baseline_seeded": 12,
        "adapters": [
            {"name": "ORESTAR", "parsed": 20, "status": "ok"},
            {"name": "PGE", "parsed": 0, "errors": ["timeout"]},
        ],
    }), encoding="utf-8")
    store = tmp_path / "spec1_intelligence.jsonl"
    recs = [
        _rec("run-aaa", "rec-1", "s1", "nk_news", 0.72, "rule_based"),
        _rec("run-aaa", "rec-2", "s2", "yonhap", 0.81, "rule_based"),
        _rec("run-old", "rec-3", "s3", "nk_news", 0.50, None),
        _rec("pdx1_2026_1024_191904", "rec-4", "s4", "ORESTAR", 0.90, "llm_verified",
             anomaly_tier="TIER_1"),
    ]
    store.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    gates = [
        _gate("run-aaa", "s1", "nk_news", True),
        _gate("run-aaa", "s2", "yonhap", True),
        _gate("run-aaa", "s9", "yonhap", False, velocity=0.25),
    ]
    (tmp_path / "spec1_intelligence_gate_decisions.jsonl").write_text(
        "".join(json.dumps(g) + "\n" for g in gates), encoding="utf-8")
    (briefs / "spec1_brief_2026-10-24.meta.json").write_text(json.dumps({
        "run_id": "run-aaa", "analysis_tier": "rule_based", "records_tier": "rule_based",
    }), encoding="utf-8")
    monkeypatch.setenv("SPEC1_STORE_PATH", str(store))
    monkeypatch.setenv(runs_index.RUN_LOG_DIR_ENV, str(logs))
    monkeypatch.setenv("SPEC1_BRIEFS_DIR", str(briefs))
    monkeypatch.delenv("SPEC1_GATE_LOG_PATH", raising=False)
    monkeypatch.delenv("SPEC1_API_KEY", raising=False)
    return tmp_path


@pytest.fixture()
def client(data_dir):
    with patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"), \
         patch("spec1_api.main.start_scheduler"), \
         patch("spec1_api.main.stop_scheduler"), \
         patch("spec1_api.main.maybe_run_on_start"):
        from spec1_api.main import create_app
        with TestClient(create_app()) as c:
            yield c


# ── runs_index unit tests ─────────────────────────────────────────────────────

def test_parse_cycle_log_reads_run_summary(data_dir):
    s = runs_index.parse_cycle_log(data_dir / "logs" / "cycle_20261024T162827Z.log")
    assert s["run_id"] == "run-aaa"
    assert s["signals_harvested"] == 10
    assert s["errors"] == []
    assert s["feeds"] == ["nk_news", "yonhap"]


def test_parse_cycle_log_without_summary_returns_none(tmp_path):
    p = tmp_path / "cycle_x.log"
    p.write_text("no summary here\n", encoding="utf-8")
    assert runs_index.parse_cycle_log(p) is None


@pytest.mark.parametrize("tiers,state", [
    (["llm_verified", "llm_verified"], runs_index.GUARD_ARMED),
    (["llm_verified", "rule_based"], runs_index.GUARD_TRIAGE),
    (["rule_based", None], runs_index.GUARD_BLOCKED),
    ([], runs_index.GUARD_BLOCKED),
])
def test_guard_status(tiers, state):
    recs = [{"analysis_tier": t} if t else {} for t in tiers]
    assert runs_index.guard_status(recs)["state"] == state


# ── API tests ────────────────────────────────────────────────────────────────

def test_list_runs_newest_first(client):
    r = client.get("/api/v1/runs")
    assert r.status_code == 200
    ids = [x["run_id"] for x in r.json()["runs"]]
    assert ids[0] == "pdx1_2026_1024_191904"
    assert set(ids) == {"pdx1_2026_1024_191904", "run-aaa", "run-old"}


def test_list_runs_guard_states(client):
    runs = {x["run_id"]: x for x in client.get("/api/v1/runs").json()["runs"]}
    assert runs["pdx1_2026_1024_191904"]["guard"]["state"] == "armed"
    assert runs["run-aaa"]["guard"]["state"] == "triage"
    assert runs["run-old"]["guard"]["state"] == "blocked"


def test_get_run_metadata_and_funnel(client):
    r = client.get("/api/v1/runs/run-aaa")
    assert r.status_code == 200
    body = r.json()
    assert body["harvested"] == 10 and body["parsed"] == 9
    assert body["written_opportunities"] == 2
    keys = [s["key"] for s in body["funnel"]]
    assert keys == ["ingest", "normalize", "rule_gates", "scoring",
                    "graph_dedupe", "handoff", "audit_store"]
    gates = next(s for s in body["funnel"] if s["key"] == "rule_gates")
    assert gates["count"] == 2 and gates["blocked"] == 1
    assert body["brief_meta"]["analysis_tier"] == "rule_based"


def test_get_run_adapter_stats_from_gate_log(client):
    adapters = {a["name"]: a for a in client.get("/api/v1/runs/run-aaa").json()["adapters"]}
    assert adapters["yonhap"] == {"name": "yonhap", "parsed": 2, "passed": 1,
                                  "blocked": 1, "status": "yield"}


def test_get_run_declared_adapters(client):
    body = client.get("/api/v1/runs/pdx1_2026_1024_191904").json()
    assert body["baseline_seeded"] == 12
    adapters = {a["name"]: a for a in body["adapters"]}
    assert adapters["ORESTAR"]["status"] == "ok"
    assert adapters["PGE"]["status"] == "error"


def test_get_run_404(client):
    assert client.get("/api/v1/runs/nope").status_code == 404
    assert client.get("/api/v1/runs/nope/records").status_code == 404


def test_records_joined_with_gate_log(client):
    recs = client.get("/api/v1/runs/run-aaa/records").json()["records"]
    assert [r["record_id"] for r in recs] == ["rec-2", "rec-1"]  # composite desc
    r = recs[0]
    assert r["gate_status"] == "pass"
    assert [g["gate"] for g in r["gates"]] == ["A", "B", "C", "D"]
    assert r["scoring"]["velocity"] == 0.75
    assert r["scoring"]["novelty"] == 0.65
    assert r["provenance"]["run_id"] == "run-aaa"
    assert r["raw"]["record_id"] == "rec-2"


def test_records_filters(client):
    base = "/api/v1/runs/run-aaa/records"
    assert client.get(base, params={"source": "nk_news"}).json()["total"] == 1
    assert client.get(base, params={"min_weight": 0.8}).json()["total"] == 1
    assert client.get(base, params={"tier": "llm_verified"}).json()["total"] == 0
    assert client.get(base, params={"tier": "bogus"}).status_code == 422


def test_records_unverified_tier_and_tier1(client):
    old = client.get("/api/v1/runs/run-old/records", params={"tier": "unverified"}).json()
    assert old["total"] == 1 and old["records"][0]["analysis_tier"] is None
    assert old["records"][0]["scoring"]["velocity"] is None  # no gate-log entry
    pdx = client.get("/api/v1/runs/pdx1_2026_1024_191904/records",
                     params={"tier1_only": True}).json()
    assert pdx["total"] == 1 and pdx["records"][0]["tier1"] is True


def test_runs_index_writes_nothing(data_dir, client):
    before = sorted((p.name, p.stat().st_size) for p in data_dir.rglob("*") if p.is_file())
    client.get("/api/v1/runs")
    client.get("/api/v1/runs/run-aaa/records")
    after = sorted((p.name, p.stat().st_size) for p in data_dir.rglob("*") if p.is_file())
    assert before == after
