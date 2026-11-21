"""Record pack + World State Brief writer: facts from the pack, loud failures."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from cls_db.database import Database
from cls_db.dual_write import DualWriter
from spec1_core.briefing import world_state as ws
from spec1_core.briefing.record_pack import (
    RecordPackError,
    build_record_pack,
    topic_proximity_test,
    write_record_pack,
)
from spec1_core.tools import export_record_pack, render_world_state_brief

GATES = {"credibility": True, "volume": True, "velocity": True, "novelty": True}


def _rec(n: int, score: float, written: str, tier: str, **extra) -> dict:
    return {
        "id": f"id-{n}", "record_id": f"rec-{n:04d}", "run_id": "run-test1",
        "signal_id": f"sig-{n:04d}", "signal_source": extra.pop("source", f"src{n % 3}"),
        "source_type": "rss", "schema_version": 2, "classification": "INVESTIGATE",
        "confidence": 0.7, "environment": "test", "opportunity_score": score,
        "opportunity_priority": "ELEVATED" if score >= 0.75 else "STANDARD",
        "gate_results": GATES, "written_at": written, "analysis_tier": tier,
        "signal_excerpt": f"Headline {n} body text.", **extra,
    }


def _log_line(ts: str, tier: str, session: str) -> str:
    return json.dumps({"ts": ts, "session": session, "task": "analyze", "tier": tier,
                       "latency_ms": 1000, "char_count": 10, "success": True})


@pytest.fixture
def store(tmp_path):
    """A migrated DB with 6 pre-013 records and 1 post-013 record, plus a log."""
    db = tmp_path / "spec1.db"
    dw = DualWriter(jsonl_path=tmp_path / "intel.jsonl", db=Database(db),
                    table="intelligence_records")
    rows = [
        _rec(1, 0.96, "2026-11-19T22:00:00.400000+00:00", "llm_verified"),
        _rec(2, 0.91, "2026-11-19T22:01:00.900000+00:00", "llm_verified"),
        _rec(3, 0.80, "2026-11-19T22:02:01.200000+00:00", "llm_verified"),
        _rec(4, 0.70, "2026-11-19T22:03:00.100000+00:00", "rule_based"),    # mock fallback
        _rec(5, 0.88, "2026-11-19T22:09:00.000000+00:00", "llm_verified"),  # no log entry
        _rec(6, 0.65, "2026-11-19T22:05:00.500000+00:00", "llm_verified"),  # log says mock
        _rec(7, 0.60, "2026-11-19T22:06:00.300000+00:00", "llm_verified",
             tier_used="ollama", model="qwen2.5:3b", llm_session="sessCOL", stamped_by="cycle"),
    ]
    for r in rows:
        dw.repo.insert(r)  # keeps written_at (DualWriter.write restamps it)
    log = tmp_path / "llm.jsonl"
    log.write_text("\n".join([
        _log_line("2026-11-19T22:00:00Z", "ollama", "s1"),
        _log_line("2026-11-19T22:01:00Z", "ollama", "s2"),
        _log_line("2026-11-19T22:02:00Z", "ollama", "s3"),
        _log_line("2026-11-19T22:03:00Z", "mock", "s4"),
        _log_line("2026-11-19T22:05:00Z", "mock", "s6"),
        json.dumps({"ts": "2026-11-19T22:00:00Z", "task": "write", "tier": "claude",
                    "session": "x", "success": True}),
    ]) + "\n")
    psyop = tmp_path / "psyop.jsonl"
    excerpts = ([{"signal_id": f"s{i}", "source": "nk_news",
                  "text_snippet": "North Korean missile test near the north coast"}
                 for i in range(3)]
                + [{"signal_id": f"t{i}", "source": "lawfare", "text_snippet": "Court ruling"}
                   for i in range(7)])
    psyop.write_text(json.dumps({
        "run_id": "run-test1", "topic": "north", "score": 2, "classification": "NOISE",
        "patterns_fired": ["NARRATIVE_CLUSTER"], "timestamp": "2026-11-19T22:00:00Z",
        "evidence_chains": [{"pattern_name": "NARRATIVE_CLUSTER", "confidence": 0.95,
                             "supporting_signals": [e["signal_id"] for e in excerpts],
                             "raw_excerpts": excerpts}]}) + "\n")
    return db, log, psyop


def _pack(store, tmp_path) -> Path:
    db, log, psyop = store
    pack = build_record_pack(db, log, run_ids=["run-test1"], psyop_path=psyop,
                             now=datetime(2026, 11, 20, tzinfo=timezone.utc))
    return write_record_pack(pack, tmp_path / "pack.json")


def _by_record(pack: dict) -> dict:
    return {r["record_id"]: r for r in pack["records"]}


# ── Record pack: tier labels ──────────────────────────────────────────────────

def test_pre013_rows_get_log_matched_tiers(store, tmp_path):
    pack = json.loads(_pack(store, tmp_path).read_text())
    recs = _by_record(pack)
    assert recs["rec-0001"]["tier"]["tier_used"] == "ollama"
    assert recs["rec-0001"]["tier"]["source"] == "log_match"
    assert recs["rec-0001"]["tier"]["llm_session"] == "s1"
    assert recs["rec-0003"]["tier"]["tier_used"] == "ollama"   # 1.2 s after the log stamp
    assert recs["rec-0004"]["tier"]["tier_used"] == "rules"     # "mock" in the log
    assert recs["rec-0004"]["usable_for_analysis"] is False
    assert recs["rec-0001"]["usable_for_analysis"] is True


def test_unmatched_and_contradicting_rows_are_tier_unknown(store, tmp_path):
    recs = _by_record(json.loads(_pack(store, tmp_path).read_text()))
    assert recs["rec-0005"]["tier"]["source"] == "unknown"      # nothing logged
    assert recs["rec-0005"]["usable_for_analysis"] is False
    assert recs["rec-0006"]["tier"]["tier_used"] == "unknown"   # log mock vs stored verified
    assert "disagrees" in recs["rec-0006"]["tier"]["note"]


def test_post013_rows_use_the_tier_used_column(store, tmp_path):
    rec = _by_record(json.loads(_pack(store, tmp_path).read_text()))["rec-0007"]
    assert rec["tier"] == {**rec["tier"], "tier_used": "ollama", "model": "qwen2.5:3b",
                           "llm_session": "sessCOL", "source": "column"}


def test_ambiguous_log_match_is_unknown(tmp_path):
    db = tmp_path / "spec1.db"
    dw = DualWriter(jsonl_path=tmp_path / "i.jsonl", db=Database(db), table="intelligence_records")
    dw.repo.insert(_rec(1, 0.9, "2026-11-19T22:00:01.500000+00:00", "llm_verified"))
    log = tmp_path / "llm.jsonl"
    log.write_text(_log_line("2026-11-19T22:00:00Z", "ollama", "a") + "\n"
                   + _log_line("2026-11-19T22:00:01Z", "ollama", "b") + "\n")
    pack = build_record_pack(db, log, run_ids=["run-test1"])
    assert pack["records"][0]["tier"]["source"] == "unknown"
    assert "2 log entries" in pack["records"][0]["tier"]["note"]


def test_empty_window_refuses_to_build(store):
    db, log, _ = store
    with pytest.raises(RecordPackError, match="nothing to brief from"):
        build_record_pack(db, log, run_ids=["run-none"])


def test_pack_never_overwritten(store, tmp_path):
    path = _pack(store, tmp_path)
    with pytest.raises(FileExistsError):
        write_record_pack(json.loads(path.read_text()), path)


def test_export_cli_fails_on_empty_window(store, tmp_path, capsys):
    db, log, psyop = store
    rc = export_record_pack.main(["--db", str(db), "--log", str(log), "--psyop", str(psyop),
                                  "--run-id", "run-none", "--out", str(tmp_path / "p.json")])
    assert rc == 1 and not (tmp_path / "p.json").exists()
    assert "nothing to brief from" in capsys.readouterr().err


# ── Psyop topic test ──────────────────────────────────────────────────────────

def test_topic_test_low_coverage_is_topic_proximity():
    excerpts = [{"source": "a", "text_snippet": "north korea"}] + \
               [{"source": "b", "text_snippet": "unrelated"}] * 3
    t = topic_proximity_test("north", excerpts)
    assert t["verdict"] == "topic_proximity" and t["coverage"] == 0.25


def test_topic_test_scattered_phrases_is_topic_proximity():
    texts = ["north korea", "north atlantic", "north africa", "north sea", "north korean"]
    t = topic_proximity_test("north", [{"source": "a", "text_snippet": x} for x in texts])
    assert t["phrases"]["north korea"] == 2          # korea / korean folded together
    assert t["verdict"] == "topic_proximity"


def test_topic_test_single_subject_says_it_cannot_rule_out_coordination():
    t = topic_proximity_test("north", [{"source": "a", "text_snippet": "North Korean test"}] * 4)
    assert t["verdict"] == "single_subject" and "cannot" in t["reason"]


# ── Brief spec fixtures ───────────────────────────────────────────────────────

def _lead(n: int, rowid: int) -> dict:
    return {
        "title": f"Lead number {n}",
        "rowids": [rowid],
        "question": "What exactly happened and who approved it?",
        "who_to_call": ["Agency press office"],
        "documents": {"foia": ["Agency records on the matter"],
                      "pull_now": ["Public filings on the matter"]},
        "window": {"value": "1 week", "reason": "the peg expires"},
        "confidence": {"level": "MEDIUM", "reason": "single source"},
        "prompt": {
            "step1": ("Draft a 3-paragraph background memo on the matter, citing primary "
                      "public documents, naming the agencies involved, and marking anything "
                      "that comes only from the record as unverified until confirmed."),
            "step2": ("Write 5 yes/no questions for the agency press office, each answerable "
                      "with yes, no or a number, covering totals, dates, approvals and any "
                      "referral to an inspector general."),
            "step3": ("Write a FOIA request draft to the agency FOIA office, in formal FOIA "
                      "language, for all records on the matter from January 1, 2025 to the "
                      "present, and ask that any denial cite the specific exemption for each "
                      "withheld record."),
            "step4": ("Write a 150-word pitch memo for an editor meeting: the story, the "
                      "stakes, what you have, and what you still need."),
        },
    }


def _spec(rowids: dict[str, int]) -> dict:
    return {
        "brief_date": "2026-11-20",
        "writer": "test",
        "executive_summary": ("{{count:records}} records; top {{top:score}} from {{top:source}} "
                              "({{top:record}}); {{count:elevated}} above {{threshold:elevated}}."),
        "elevated_note": "{{count:elevated}} model-tier records crossed the threshold.",
        "elevated": [{"rowid": rowids["rec-0001"], "headline": "Top item",
                      "note": "Scored {{score:%d}}." % rowids["rec-0001"]}],
        "domains": [
            {"name": "Geopolitics", "rowids": [rowids["rec-0002"]],
             "paragraphs": ["Signal {{source:%d}} at {{score:%d}}." % (rowids["rec-0002"],
                                                                      rowids["rec-0002"])],
             "trajectory": {"limits": "Insufficient signal depth."}},
            {"name": "Cyber / Info Ops", "rowids": [],
             "paragraphs": ["Nothing operational."],
             "trajectory": {"limits": "Insufficient signal depth."}},
            {"name": "Psyop / Narrative Analysis", "rowids": [],
             "paragraphs": ["Coverage {{psyop:coverage}}, verdict {{psyop:verdict}}: NOISE."],
             "trajectory": {"limits": "Excerpt text only."}},
        ],
        "leads": [_lead(i, rowids[r]) for i, r in
                  enumerate(("rec-0001", "rec-0002", "rec-0003"), 1)],
        "watch": [{"item": "Follow-up", "rowids": [rowids["rec-0001"]]}],
    }


@pytest.fixture
def brief_paths(store, tmp_path):
    pack_path = _pack(store, tmp_path)
    pack = json.loads(pack_path.read_text())
    rowids = {r["record_id"]: r["rowid"] for r in pack["records"]}
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec(rowids)))
    return spec_path, pack_path, rowids


def _brief(brief_paths, mutate=None) -> ws.Brief:
    spec_path, pack_path, rowids = brief_paths
    brief = ws.load(spec_path, pack_path)
    if mutate:
        mutate(brief.spec, rowids)
    return brief


# ── Validation: loud failures ─────────────────────────────────────────────────

def test_good_brief_validates(brief_paths):
    ws.validate(_brief(brief_paths))


@pytest.mark.parametrize("mutate,expected", [
    (lambda s, r: s["leads"][1]["prompt"].pop("step3"), "step3 is missing"),
    (lambda s, r: s["leads"][0]["prompt"].update(step4="Write a 150-word pitch memo for"),
     "does not end a sentence"),
    (lambda s, r: s["leads"][2]["prompt"].update(
        step3=s["leads"][2]["prompt"]["step3"] + " [Steps 3-4 added by hand.]"),
     "truncation marker"),
    (lambda s, r: s["leads"].pop(), "need 3-5"),
    (lambda s, r: s["leads"][0].pop("who_to_call"), "missing who_to_call"),
    (lambda s, r: s["leads"][0]["documents"].pop("pull_now"), "pull_now"),
    (lambda s, r: s.update(executive_summary="The top score was 0.961."), "bare score '0.961'"),
    (lambda s, r: s["leads"][0].update(rowids=[r["rec-0004"]]), "only model-tier"),
    (lambda s, r: s["leads"][0].update(rowids=[r["rec-0005"]]), "tier unknown"),
    (lambda s, r: s["leads"][0].update(rowids=[999999]), "not in the pack"),
    (lambda s, r: s["elevated"].append({"rowid": r["rec-0007"], "headline": "x"}),
     "below 0.75"),
    (lambda s, r: s["domains"][2].update(paragraphs=["Coverage {{psyop:coverage}}."]),
     "must say NOISE"),
    (lambda s, r: s["domains"].pop(1), "domain briefings must be exactly"),
    (lambda s, r: s.update(elevated_note="{{score:12}} {{bogus:1}}"), "unknown placeholder"),
])
def test_validation_fails_loudly(brief_paths, mutate, expected):
    with pytest.raises(ws.BriefValidationError) as exc:
        ws.validate(_brief(brief_paths, mutate))
    assert any(expected in p for p in exc.value.problems), exc.value.problems


def test_rendered_markdown_is_rechecked_for_cut_steps():
    md = "**LEAD: a**\n> Step 1 — ok.\n> Step 2 — ok.\n> Step 3 — ok.\n"
    with pytest.raises(ws.BriefValidationError, match="Step 4 missing"):
        ws.check_rendered(md, 1)


# ── Rendering ─────────────────────────────────────────────────────────────────

def test_markdown_has_april24_structure_and_pack_facts(brief_paths):
    brief = _brief(brief_paths)
    md = ws.render_markdown(brief)
    for heading in ("### Executive Summary", "### Elevated Signals", "### Domain Briefings",
                    "**Geopolitics**", "**Cyber / Info Ops**", "**Psyop / Narrative Analysis**",
                    "### Story Leads", "### Records counted, not analysed"):
        assert heading in md, heading
    assert md.count("**LEAD: ") == 3
    for s in range(1, 5):
        assert md.count(f"> Step {s} — ") == 3
    assert "0.960" in md and "rec-0001" in md and "sig-0001" in md      # from the pack
    assert "rules tier" in md and "rec-0004" in md                     # counted, labelled
    assert "tier unknown" in md and "rec-0005" in md
    assert ws.PUBLISHER_LINE in md


def test_print_html_has_april28_layout_and_brand(brief_paths):
    page = ws.render_print_html(_brief(brief_paths))
    for marker in ('class="masthead"', "<h1>WORLD STATE BRIEF</h1>", 'class="section-title"',
                   "Trajectory Assessment", "24-Hour Watch List", "Claude Prompt",
                   "Notitia Civica — published by Matthew J. Lakamp"):
        assert marker in page, marker
    assert "EVASTARARCANA" not in page.upper()
    assert "evastararcana" not in page.lower()


def test_outputs_are_versioned_and_never_overwritten(brief_paths, tmp_path):
    brief = _brief(brief_paths)
    out = tmp_path / "out"
    paths = ws.write_outputs(brief, out)
    assert "run-test1" in paths["md"].name and brief.pack_sha256[:8] in paths["md"].name
    assert json.loads(paths["meta"].read_text())["published"] is False
    with pytest.raises(FileExistsError):
        ws.write_outputs(brief, out)


def test_cli_writes_nothing_when_validation_fails(brief_paths, tmp_path, capsys):
    spec_path, pack_path, _ = brief_paths
    spec = json.loads(spec_path.read_text())
    spec["leads"][0]["prompt"]["step4"] = ""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(spec))
    out = tmp_path / "out"
    rc = render_world_state_brief.main(["--spec", str(bad), "--pack", str(pack_path),
                                        "--out-dir", str(out)])
    assert rc == 1 and not out.exists()
    assert "step4 is missing" in capsys.readouterr().err


def test_cli_no_pdf_unless_asked(brief_paths, tmp_path):
    spec_path, pack_path, _ = brief_paths
    with patch.object(render_world_state_brief, "print_pdf") as pdf:
        assert render_world_state_brief.main(["--spec", str(spec_path), "--pack", str(pack_path),
                                              "--out-dir", str(tmp_path / "o")]) == 0
    pdf.assert_not_called()


def test_print_pdf_runs_chromium_in_a_subprocess(tmp_path):
    html_path = tmp_path / "b.html"
    html_path.write_text("<html></html>")
    pdf_path = tmp_path / "b.pdf"

    def fake_run(cmd, **kw):
        assert cmd[0] == "/usr/bin/chromium" and "--headless" in cmd
        assert f"--print-to-pdf={pdf_path}" in cmd
        pdf_path.write_bytes(b"%PDF-1.4")
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    with patch("subprocess.run", side_effect=fake_run):
        assert render_world_state_brief.print_pdf(html_path, pdf_path,
                                                  "/usr/bin/chromium") == pdf_path
    with pytest.raises(FileExistsError):
        render_world_state_brief.print_pdf(html_path, pdf_path, "/usr/bin/chromium")
