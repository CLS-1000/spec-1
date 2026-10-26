# @domain:   spec-1
# @module:   test_narrative_desk_api
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the Narrative & Publisher Desk (/desk/narrative, /api/v1/narrative/*).

Offline: stores and briefs live in tmp_path, generate_brief is patched (the
background task runs inside the TestClient request), the scheduler is stubbed
and tests/conftest.py blocks Ollama and the Claude API.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from spec1_api import narrative_store as ns
from spec1_api.routers import narrative_desk

UI = Path(__file__).resolve().parents[1] / "ui"
DATE = "2026-10-25"
DRAFT_MD = (
    "## LEGISLATIVE BRIEF — Oregon closes the interim\n\n"
    "*Ten measures and four committees, verified locally.*\n\n"
    "The interim session moved appropriations bills to chapter.\n\n"
    "### Executive Summary\n- **SB 5701** signed.\n"
)
TEMPLATE = (
    "<html><head><title>NOTITIA CIVICA — Civic Intelligence Brief — X</title>"
    '<link href="https://fonts.googleapis.com/css2?family=X" rel="stylesheet">'
    "<script>alert(1)</script></head><body><p>template body</p></body></html>"
)


def _rec(run_id, rid, tier="llm_verified", conf=0.7, written=f"{DATE}T23:36:17+00:00", **extra):
    return {"record_id": rid, "run_id": run_id, "analysis_tier": tier, "outcome_confidence": conf,
            "outcome_classification": "MONITOR", "signal_source": "olis", "written_at": written,
            "domain": "state_leg.or.measure", "metadata": {"bill": "SB 5701", "status": "signed"},
            **extra}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    std = tmp_path / "spec1_intelligence.jsonl"
    std.write_text("".join(json.dumps(r) + "\n" for r in [
        _rec("run-std-old", "s0", written=f"{DATE}T06:00:00+00:00"),
        _rec("run-std", "s1"), _rec("run-std", "s2", conf=0.6),
    ]), encoding="utf-8")
    leg = tmp_path / "spec1_legislative.jsonl"
    leg.write_text("".join(json.dumps(r) + "\n" for r in [
        _rec("run-leg", "l1"), _rec("run-leg", "l2", tier="llm_verified", conf=0.5),
    ]), encoding="utf-8")
    tpl = tmp_path / "civic-intelligence-brief.html"
    tpl.write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setenv("SPEC1_BRIEFS_DIR", str(briefs))
    monkeypatch.setenv("SPEC1_STORE_PATH", str(std))
    monkeypatch.setenv("SPEC1_LEGISLATIVE_STORE", str(leg))
    monkeypatch.setenv("SPEC1_PUBLISH_LOG", str(tmp_path / "publish_log.jsonl"))
    monkeypatch.setenv("SPEC1_NOTITIA_TEMPLATE", str(tpl))
    monkeypatch.delenv("SPEC1_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    narrative_desk._jobs.clear()
    yield tmp_path
    narrative_desk._jobs.clear()


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
def client(env):
    yield from _client()


def _fake_generate(markdown=DRAFT_MD, backend="local", calls=None):
    def fake(records, stats, mode="standard"):
        if calls is not None:
            calls.append((mode, len(records), stats["run_id"]))
        if backend:
            stats["brief_backend"] = backend
        else:
            stats["brief_fallback"] = True
        return markdown, "## SYSTEM PROMPT\n\n---\n\n## USER PROMPT\n"
    return fake


def _generate(client, desk="legislative", voice="notitia_civica", backend="local", calls=None):
    with patch("spec1_core.briefing.generator.generate_brief",
               side_effect=_fake_generate(backend=backend, calls=calls)):
        r = client.post("/api/v1/narrative/generate", json={"desk": desk, "voice": voice, "date": DATE})
    assert r.status_code == 202, r.text
    job = client.get(f"/api/v1/narrative/jobs/{r.json()['job_id']}").json()
    return r.json(), job


def _log(env) -> list[dict]:
    path = env / "publish_log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ── generate + jobs ───────────────────────────────────────────────────────────

def test_generate_creates_job_and_draft(client, env):
    started, job = _generate(client)
    assert started["status"] == "pending" and started["run_id"] == "run-leg"
    assert job["status"] == "completed" and job["error"] is None
    draft = Path(job["draft_path"])
    assert draft.parent == env / "briefs" / "drafts"
    assert draft.name == f"spec1_brief_{DATE}_notitia_civica_run-leg.md"
    meta = json.loads(draft.with_name(draft.stem + ".meta.json").read_text())
    assert meta["voice"] == "notitia_civica" and meta["mode"] == "legislative"
    assert meta["desk"] == "legislative" and meta["model"] == "qwen2.5:3b"
    assert meta["brief_backend"] == "local" and meta["brief_source"] == "model"
    assert meta["analysis_tier"] == "llm_verified" and meta["avg_confidence"] == 0.6
    assert [e["event"] for e in _log(env)] == ["draft_generated"]


@pytest.mark.parametrize("voice,mode", [("standard", "standard"), ("world_state", "geopolitics"),
                                        ("notitia_civica", "legislative")])
def test_voice_maps_to_existing_prompt_mode(client, voice, mode):
    calls = []
    _generate(client, desk="standard", voice=voice, calls=calls)
    assert calls == [(mode, 2, "run-std")]          # newest run on the date, not run-std-old


def test_generation_never_touches_canonical_briefs(client, env):
    canonical = env / "briefs" / f"spec1_brief_{DATE}.md"
    canonical.write_text("published text\n")
    before = hashlib.sha256(canonical.read_bytes()).hexdigest()
    _generate(client)
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == before
    assert not (env / "briefs" / "spec1_brief_latest.md").exists()


def test_generate_rejects_second_job_while_running(client):
    narrative_desk._jobs["busy"] = {"job_id": "busy", "status": "running", "desk": "standard",
                              "voice": "standard", "date": DATE, "run_id": "x", "created_at": ""}
    r = client.post("/api/v1/narrative/generate", json={"desk": "standard", "voice": "standard", "date": DATE})
    assert r.status_code == 409


def test_generate_404_without_records(client):
    r = client.post("/api/v1/narrative/generate", json={"desk": "standard", "voice": "standard",
                                                       "date": "2020-01-01"})
    assert r.status_code == 404


def test_generate_validates_inputs(client):
    for body in ({"voice": "tabloid"}, {"desk": "sports"}, {"date": "../../etc"}):
        assert client.post("/api/v1/narrative/generate", json=body).status_code == 422


def test_failed_generation_is_reported(client, env):
    with patch("spec1_core.briefing.generator.generate_brief", side_effect=RuntimeError("ollama down")):
        r = client.post("/api/v1/narrative/generate", json={"desk": "legislative", "voice": "standard", "date": DATE})
    job = client.get(f"/api/v1/narrative/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "failed" and "ollama down" in job["error"]
    assert not (env / "briefs" / "drafts").exists() or not list((env / "briefs" / "drafts").glob("*.md"))


def test_unknown_job_404(client):
    assert client.get("/api/v1/narrative/jobs/nope").status_code == 404


# ── drafts ────────────────────────────────────────────────────────────────────

def test_draft_index_and_detail(client):
    _, job = _generate(client)
    listing = client.get("/api/v1/narrative/drafts").json()
    assert listing["total"] == 1
    item = listing["drafts"][0]
    assert item["draft_id"] == job["draft_id"] and item["publishable"] and not item["released"]
    d = client.get(f"/api/v1/narrative/drafts/{job['draft_id']}").json()
    assert d["frontmatter"] == {"hed": "LEGISLATIVE BRIEF — Oregon closes the interim",
                                "dek": "Ten measures and four committees, verified locally.",
                                "lead": "The interim session moved appropriations bills to chapter."}
    assert d["readiness"]["publishable"] is True and d["readiness"]["llm_verified"] == 2


@pytest.mark.parametrize("bad", ["..%2F..%2Fetc%2Fpasswd", "%2e%2e", "..", "spec1_brief_x",
                                 f"{DATE}_standard_..", f"{DATE}_tabloid_run"])
def test_draft_traversal_ids_rejected(client, bad):
    _generate(client)
    r = client.get(f"/api/v1/narrative/drafts/{bad}")
    assert r.status_code in (404, 422)
    assert "root:" not in r.text


def test_patch_edits_are_separate_from_draft(client):
    _, job = _generate(client)
    path = Path(job["draft_path"])
    before = path.read_bytes()
    r = client.patch(f"/api/v1/narrative/drafts/{job['draft_id']}", json={"hed": "Oregon’s quiet interim"})
    assert r.status_code == 200 and r.json()["edits"]["hed"] == "Oregon’s quiet interim"
    assert path.read_bytes() == before
    d = client.get(f"/api/v1/narrative/drafts/{job['draft_id']}").json()
    assert d["edited_markdown"].startswith("## Oregon’s quiet interim")


def test_evidence_returns_run_records(client):
    _, job = _generate(client)
    ev = client.get(f"/api/v1/narrative/drafts/{job['draft_id']}/evidence").json()
    assert ev["desk"] == "legislative" and ev["run_id"] == "run-leg" and ev["total"] == 2
    assert ev["records"][0]["measure_prefix"] == "SB"


# ── export ────────────────────────────────────────────────────────────────────

def test_export_preview_is_offline(client):
    _, job = _generate(client)
    x = client.get(f"/api/v1/narrative/drafts/{job['draft_id']}/export").json()
    assert x["files"] == [f"spec1_brief_{DATE}.md", f"spec1_brief_{DATE}.meta.json", "spec1_brief_latest.md",
                          "spec1_brief_latest.meta.json", f"spec1_brief_{DATE}.published.json"]
    assert x["preview_available"] is True
    html = x["preview_html"].lower()
    assert "<script" not in html and "<link" not in html and "googleapis" not in html
    assert "notitia civica" in html


def test_export_without_template(client, env, monkeypatch):
    _, job = _generate(client)
    monkeypatch.setenv("SPEC1_NOTITIA_TEMPLATE", str(env / "missing.html"))
    x = client.get(f"/api/v1/narrative/drafts/{job['draft_id']}/export").json()
    assert x["preview_available"] is False and x["preview_html"] is None and x["files"]


# ── publish ───────────────────────────────────────────────────────────────────

def _publish(client, draft_id, **kw):
    body = {"draft_id": draft_id, "analyst_signature": "MJL", **kw}
    return client.post("/api/v1/narrative/publish", json=body)


def test_publish_promotes_and_writes_receipt(client, env):
    _, job = _generate(client)
    client.patch(f"/api/v1/narrative/drafts/{job['draft_id']}", json={"dek": "Edited dek."})
    r = _publish(client, job["draft_id"])
    assert r.status_code == 200, r.text
    receipt = r.json()["receipt"]
    briefs = env / "briefs"
    canonical = briefs / f"spec1_brief_{DATE}.md"
    assert "*Edited dek.*" in canonical.read_text()
    assert (briefs / "spec1_brief_latest.md").read_text() == canonical.read_text()
    assert receipt["brief_sha256"] == hashlib.sha256(canonical.read_bytes()).hexdigest()
    assert receipt["meta_sha256"] == hashlib.sha256(
        (briefs / f"spec1_brief_{DATE}.meta.json").read_bytes()).hexdigest()
    assert receipt["analyst_signature"] == "MJL" and receipt["voice"] == "notitia_civica"
    assert receipt["model"] == "qwen2.5:3b" and receipt["supersedes"] is None
    assert receipt["git_commit"]
    on_disk = json.loads((briefs / f"spec1_brief_{DATE}.published.json").read_text())
    assert on_disk == receipt
    from spec1_core.briefing.writer import publish_block_reason
    assert publish_block_reason(canonical) is None      # the workflow's guard accepts it
    assert [e["event"] for e in _log(env)] == ["draft_generated", "brief_released"]
    assert client.get("/api/v1/narrative/drafts").json()["drafts"][0]["released"] is True


def test_publish_refuses_rule_based_draft(client, env):
    _, job = _generate(client, backend=None)      # rule-based fallback brief
    r = _publish(client, job["draft_id"])
    assert r.status_code == 409 and "publish gate refused" in r.json()["detail"]
    assert not (env / "briefs" / f"spec1_brief_{DATE}.md").exists()


def test_publish_refuses_low_confidence(client, env, monkeypatch):
    leg = env / "spec1_legislative.jsonl"
    leg.write_text(json.dumps(_rec("run-leg", "l1", conf=0.4)) + "\n")
    _, job = _generate(client)
    r = _publish(client, job["draft_id"])
    assert r.status_code == 409 and "below 0.55" in r.json()["detail"]


def test_publish_requires_signature(client):
    _, job = _generate(client)
    assert _publish(client, job["draft_id"], analyst_signature="").status_code == 422
    assert _publish(client, job["draft_id"], analyst_signature="   ").status_code == 422


def test_publish_unknown_draft_404(client):
    assert _publish(client, f"{DATE}_standard_nope").status_code == 404
    assert _publish(client, "../../etc/passwd").status_code == 404


def test_publish_refuses_when_date_already_released(client, env):
    _, job = _generate(client)
    assert _publish(client, job["draft_id"]).status_code == 200
    r = _publish(client, job["draft_id"])
    assert r.status_code == 409 and "already has a published release" in r.json()["detail"]


def test_force_archives_previous_release_then_replaces(client, env):
    _, job = _generate(client)
    first = _publish(client, job["draft_id"]).json()["receipt"]
    briefs = env / "briefs"
    old_text = (briefs / f"spec1_brief_{DATE}.md").read_text()
    client.patch(f"/api/v1/narrative/drafts/{job['draft_id']}", json={"hed": "Revised hed"})
    r = _publish(client, job["draft_id"], force=True)
    assert r.status_code == 200
    second = r.json()["receipt"]
    archive = briefs / "releases" / DATE / "r1"
    assert (archive / f"spec1_brief_{DATE}.md").read_text() == old_text
    assert json.loads((archive / f"spec1_brief_{DATE}.published.json").read_text()) == first
    assert second["supersedes"]["brief_sha256"] == first["brief_sha256"]
    assert second["supersedes"]["archived_to"].endswith(str(Path("releases") / DATE / "r1"))
    assert "Revised hed" in (briefs / f"spec1_brief_{DATE}.md").read_text()


# ── status, page, auth ────────────────────────────────────────────────────────

def test_status(client):
    s = client.get("/api/v1/narrative/status").json()
    assert s["engine_model"] == "qwen2.5:3b" and s["engine_reachable"] is False
    assert s["min_confidence"] == 0.55 and s["job_running"] is None


@pytest.mark.parametrize("path", ["/desk/narrative", "/desk/narrative/"])
def test_page_served(client, path):
    r = client.get(path)
    assert r.status_code == 200 and "SPEC-1 NARRATIVE DESK" in r.text and "EVASTARARCANA LLC" in r.text


def test_page_is_offline():
    html = (UI / "narrative.html").read_text(encoding="utf-8")
    for needle in ("fonts.googleapis", "cdn.", "unpkg", "jsdelivr", "<script src", "<link "):
        assert needle not in html, needle
    assert 'sandbox=""' in html and "allow-scripts" not in html


@pytest.mark.parametrize("page", ["index.html", "legislative.html", "narrative.html"])
def test_shared_nav_on_every_desk(page):
    html = (UI / page).read_text(encoding="utf-8")
    for href in ('href="/"', 'href="/desk/legislative"', 'href="/desk/narrative"'):
        assert href in html, (page, href)


def test_page_public_but_writes_need_key(env, monkeypatch):
    monkeypatch.setenv("SPEC1_API_KEY", "secret")
    for c in _client():
        assert c.get("/desk/narrative").status_code == 200
        body = {"desk": "standard", "voice": "standard", "date": DATE}
        assert c.post("/api/v1/narrative/generate", json=body).status_code in (401, 403)
        assert c.post("/api/v1/narrative/publish", json={"draft_id": "x", "analyst_signature": "a"}).status_code in (401, 403)


# ── store helpers ─────────────────────────────────────────────────────────────

def test_apply_edits_inserts_missing_dek_and_lead():
    md = "## Hed only\n\n### Section\n- item\n"
    out = ns.apply_edits(md, {"dek": "New dek", "lead": "New lead."})
    assert out.splitlines()[0] == "## Hed only"
    assert "*New dek*" in out and "New lead." in out and "- item" in out


def test_template_instruction_leak_blocks_release(client, env):
    leaked = DRAFT_MD + "\n### Federal\n[Records from Congressional adapters. Organize by chamber, then by member.]\n"
    with patch("spec1_core.briefing.generator.generate_brief",
               side_effect=_fake_generate(markdown=leaked)):
        r = client.post("/api/v1/narrative/generate", json={"desk": "legislative", "voice": "notitia_civica", "date": DATE})
    draft_id = client.get(f"/api/v1/narrative/jobs/{r.json()['job_id']}").json()["draft_id"]
    gate = client.get(f"/api/v1/narrative/drafts/{draft_id}").json()["readiness"]
    assert gate["publishable"] is False and "template instruction" in gate["reasons"][0]
    assert _publish(client, draft_id).status_code == 409
    assert not (env / "briefs" / f"spec1_brief_{DATE}.md").exists()


def test_template_leaks_ignores_ordinary_brackets():
    assert ns.template_leaks("- **SB 5701** [signed]\nSee [source](https://x.org) here.\n") == []
    assert ns.template_leaks("[3-5 bullets. Each bullet: one sentence, names the subject.]") != []
