# @domain:   spec-1
# @module:   test_ui
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the Legislative & Judicial Desk view and its read-only API.

GET /desk/legislative                     the page (ui/legislative.html)
GET /api/v1/desk/legislative/status       desk config + local-engine reachability
GET /api/v1/desk/legislative/records      spec1_legislative.jsonl, filterable
GET /api/v1/desk/legislative/brief        spec1_legislative_<date>.md + .meta.json

Offline: files live in tmp_path, the scheduler is stubbed and Ollama is
reported unreachable by tests/conftest.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

UI_FILE = Path(__file__).resolve().parents[1] / "ui" / "legislative.html"


def _rec(run_id, rid, domain, tier, **meta_extra):
    meta = {"state": "OR", "status": "signed", "sponsor": "", "source_url": "https://olis.example/x"}
    meta.update(meta_extra)
    return {
        "record_id": rid, "run_id": run_id, "domain": domain, "desk": "legislative",
        "title": meta.get("title", rid), "summary": f"summary {rid}",
        "published_at": "2026-09-28T12:00:00+00:00",
        "opportunity_priority": "ELEVATED", "outcome_classification": "MONITOR",
        "outcome_confidence": 0.6, "analysis_tier": tier, "llm_reasoning": "routine bill",
        "signal_source": "olis", "metadata": meta,
    }


RECORDS = [
    _rec("run-1", "r1", "state_leg.or.measure", "rule_based", bill="HB 4177", title="Public meetings"),
    _rec("run-2", "r2", "state_leg.or.measure", "llm_verified", bill="SB 5701", title="Appropriations"),
    _rec("run-2", "r3", "state_leg.or.interim_committee", "llm_verified",
         bill="Blue Economy agenda", status="held", sponsor="Blue Economy Task Force",
         committee_code="TFBE", title="Blue Economy — 2026-09-10"),
]

BRIEF_MD = (
    "## LEGISLATIVE & JUDICIAL DESK — 2026-10-25\n\n### Executive Summary\n"
    "- **SB 5701**: appropriations.\n\n---\n\n### PDF Conversion\n\nrun pandoc\n"
)
META = {"run_id": "run-2", "brief": "spec1_legislative_2026-10-25.md",
        "records_tier": "llm_verified", "brief_source": "model",
        "record_tiers": {"llm_verified": 2, "rule_based": 0}, "analysis_tier": "llm_verified",
        "written_at": "2026-10-25T23:43:21+00:00"}


@pytest.fixture()
def desk_dir(tmp_path: Path, monkeypatch) -> Path:
    store = tmp_path / "spec1_legislative.jsonl"
    store.write_text("".join(json.dumps(r) + "\n" for r in RECORDS) + "not json\n", encoding="utf-8")
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    for name in ("spec1_legislative_2026-10-25", "spec1_legislative_latest"):
        (briefs / f"{name}.md").write_text(BRIEF_MD, encoding="utf-8")
        (briefs / f"{name}.meta.json").write_text(json.dumps(META), encoding="utf-8")
    (briefs / "spec1_legislative_2026-10-20.md").write_text("## Older\n", encoding="utf-8")
    monkeypatch.setenv("SPEC1_LEGISLATIVE_STORE", str(store))
    monkeypatch.setenv("SPEC1_BRIEFS_DIR", str(briefs))
    monkeypatch.delenv("SPEC1_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    return tmp_path


def _client():
    with patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"), \
         patch("spec1_api.main.start_scheduler"), \
         patch("spec1_api.main.stop_scheduler"), \
         patch("spec1_api.main.maybe_run_on_start"):
        from spec1_api.main import create_app
        with TestClient(create_app()) as c:
            yield c


@pytest.fixture()
def client(desk_dir):
    yield from _client()


# ── Page ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/desk/legislative", "/desk/legislative/"])
def test_page_is_served(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "SPEC-1 LEGISLATIVE DESK" in r.text
    assert "EVASTARARCANA LLC" in r.text


def test_page_is_offline_no_external_assets():
    html = UI_FILE.read_text(encoding="utf-8")
    for needle in ("fonts.googleapis", "cdn.", "unpkg", "jsdelivr", "<script src", "<link "):
        assert needle not in html, needle
    assert "/api/v1/desk/legislative" in html


def test_page_is_public_when_api_key_set(desk_dir, monkeypatch):
    monkeypatch.setenv("SPEC1_API_KEY", "secret")
    for c in _client():
        assert c.get("/desk/legislative").status_code == 200
        assert c.get("/api/v1/desk/legislative/records").status_code in (401, 403)
        assert c.get("/api/v1/desk/legislative/records", params={"api_key": "secret"}).status_code == 200


def test_triage_desk_links_to_legislative_desk(client):
    assert 'href="/desk/legislative"' in client.get("/").text


# ── Status ────────────────────────────────────────────────────────────────────

def test_status(client):
    r = client.get("/api/v1/desk/legislative/status")
    assert r.status_code == 200
    s = r.json()
    assert s["lookback_days"] == 90
    assert s["lookahead_days"] == 14
    assert s["max_per_run"] == 25
    assert s["engine_model"] == "qwen2.5:3b"
    assert s["engine_reachable"] is False        # conftest blocks Ollama
    assert s["store_exists"] is True


def test_status_engine_follows_ollama_model(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    assert client.get("/api/v1/desk/legislative/status").json()["engine_model"] == "qwen2.5:7b"


# ── Records ───────────────────────────────────────────────────────────────────

def test_records_newest_first_with_counts(client):
    r = client.get("/api/v1/desk/legislative/records")
    assert r.status_code == 200
    d = r.json()
    assert [x["record_id"] for x in d["records"]] == ["r3", "r2", "r1"]
    assert d["counts"] == {"total": 3, "by_kind": {"interim_committee": 1, "measure": 2},
                           "by_tier": {"llm_verified": 2, "rule_based": 1}, "runs": 2}


def test_records_row_shape(client):
    rows = {x["record_id"]: x for x in client.get("/api/v1/desk/legislative/records").json()["records"]}
    m = rows["r1"]
    assert (m["kind"], m["measure_prefix"], m["measure_number"], m["chamber"]) == ("measure", "HB", "4177", "House")
    assert m["status"] == "signed" and m["analysis_tier"] == "rule_based"
    assert m["last_action"].startswith("2026-09-28")
    assert rows["r2"]["chamber"] == "Senate"
    c = rows["r3"]
    assert c["kind"] == "interim_committee"
    assert c["committee_code"] == "TFBE" and c["committee"] == "Blue Economy Task Force"
    assert c["measure_prefix"] == "" and c["chamber"] == ""


@pytest.mark.parametrize("params,expected", [
    ({"kind": "measure"}, ["r2", "r1"]),
    ({"kind": "interim_committee"}, ["r3"]),
    ({"tier": "rule_based"}, ["r1"]),
    ({"run_id": "run-2"}, ["r3", "r2"]),
    ({"q": "blue econ"}, ["r3"]),
    ({"q": "hb 4177"}, ["r1"]),
    ({"limit": 1}, ["r3"]),
])
def test_records_filters(client, params, expected):
    d = client.get("/api/v1/desk/legislative/records", params=params).json()
    assert [x["record_id"] for x in d["records"]] == expected
    assert d["counts"]["total"] == 3                  # counts ignore filters


def test_records_bad_kind_rejected(client):
    assert client.get("/api/v1/desk/legislative/records", params={"kind": "sports"}).status_code == 422


def test_records_missing_store_is_empty(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SPEC1_LEGISLATIVE_STORE", str(tmp_path / "nope.jsonl"))
    d = client.get("/api/v1/desk/legislative/records").json()
    assert d["records"] == [] and d["counts"]["total"] == 0


# ── Brief ─────────────────────────────────────────────────────────────────────

def test_brief_latest(client):
    r = client.get("/api/v1/desk/legislative/brief")
    assert r.status_code == 200
    b = r.json()
    assert b["markdown"].startswith("## LEGISLATIVE & JUDICIAL DESK")
    assert "PDF Conversion" not in b["markdown"]
    assert b["meta"]["analysis_tier"] == "llm_verified"
    assert b["run_stats"] == {"records": 2, "avg_confidence": 0.6,
                              "by_kind": {"measure": 1, "interim_committee": 1},
                              "by_classification": {"MONITOR": 2}}
    assert b["available_dates"] == ["2026-10-25", "2026-10-20"]


def test_brief_by_date_without_sidecar(client):
    b = client.get("/api/v1/desk/legislative/brief", params={"date": "2026-10-20"}).json()
    assert b["markdown"] == "## Older\n"
    assert b["meta"] is None and b["run_stats"] is None


def test_brief_missing_date_404(client):
    assert client.get("/api/v1/desk/legislative/brief", params={"date": "2026-01-01"}).status_code == 404


def test_brief_rejects_path_tricks(client):
    r = client.get("/api/v1/desk/legislative/brief", params={"date": "../../etc/passwd"})
    assert r.status_code == 422


def test_brief_none_yet_404(client, monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("SPEC1_BRIEFS_DIR", str(empty))
    assert client.get("/api/v1/desk/legislative/brief").status_code == 404
