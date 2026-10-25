# @domain:   spec-1
# @module:   test_leg_jud_desk
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the Legislative & Judicial Desk v2.1 — bridge, OLIS interim, writer, desk cycle."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cls_leg_jud import bridge
from cls_osint.schemas import StateLegRecord
from cls_pdx1.sources import olis
from cls_pdx1.sources.olis import OlisAdapter
from spec1_core.schemas.models import Outcome, Signal
from spec1_labels import ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED

NOW = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=90)
UNTIL = NOW + timedelta(days=14)
PACIFIC = olis._OLIS_TZ


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raw_measure(prefix="HB", number=4177, modified="2026-09-28T10:00:00", **extra) -> dict:
    raw = {
        "MeasurePrefix": prefix,
        "MeasureNumber": number,
        "RelatingClause": "Restates the serial communications prohibitions.",
        "CurrentLocation": "Chapter Number Assigned",
        "ChapterNumber": 12,
        "ChiefSponsor": "Rep Example",
        "SessionKey": "2026R1",
        "CreatedDate": "2026-01-16T16:54:28",
        "ModifiedDate": modified,
    }
    raw.update(extra)
    return raw


def _bills(*raws: dict):
    return OlisAdapter(bill_data=list(raws)).fetch().records


def _meeting(code="SVEMFW", when=NOW - timedelta(days=10), items=None) -> dict:
    return {
        "session_key": "2025I1",
        "committee_code": code,
        "committee_name": "Veterans, Emergency Management, Federal and World Affairs",
        "meeting_date": when,
        "status": "Scheduled",
        "agenda_url": f"https://olis.example/{code}",
        "items": items if items is not None else [
            {"text": "Ukraine Update", "measure": ""},
            {"text": "Rural electric cooperatives", "measure": "SB 1582"},
        ],
    }


def _state_rec(state="CA", source="openstates", filed=None) -> StateLegRecord:
    filed = filed or (NOW - timedelta(days=5)).date().isoformat()
    return StateLegRecord(
        record_id=StateLegRecord.make_id(state, f"{state} SB 1", filed),
        state=state, bill_id=f"{state} SB 1", title="Lobbying Disclosure Act.",
        sponsor="Sen. Example", chamber="SENATE", status="ENACTED",
        summary="Requires disclosure.", disclosure_regime="FULL", disclosure_gap=False,
        filed_at=filed, source_url="https://example.org/bill", metadata={"source": source},
    )


def _counts() -> dict:
    return {"dropped_no_date": 0, "dropped_stale": 0, "dropped_synthetic": 0,
            "dropped_empty_agenda": 0}


def _collect(**kwargs):
    defaults = dict(
        run_id="run-t", now=NOW,
        olis_fetch=lambda: (_bills(_raw_measure()), []),
        interim_fetch=lambda since, until: [_meeting()],
        state_fetch=lambda: [_state_rec()],
    )
    defaults.update(kwargs)
    return bridge.collect_candidates(**defaults)


# ── OLIS parser ───────────────────────────────────────────────────────────────

def test_olis_bill_carries_last_action_and_introduced_dates():
    bill = _bills(_raw_measure())[0]
    assert bill.last_action_at.isoformat() == "2026-09-28"
    assert bill.introduced_at.isoformat() == "2026-01-16"


def test_olis_bill_without_dates_still_parses():
    bill = _bills(_raw_measure(modified=None, CreatedDate=None))[0]
    assert bill.last_action_at is None and bill.introduced_at is None


# ── Bridge: OLIS measures ─────────────────────────────────────────────────────

def test_measure_signal_shape():
    sigs = bridge.olis_measure_signals(_bills(_raw_measure()), since=SINCE, run_id="r",
                                       environment="test", counts=_counts())
    assert len(sigs) == 1
    s = sigs[0]
    assert isinstance(s, Signal)
    assert s.source == "olis" and s.source_type == "legislative"
    assert s.metadata["domain"] == "state_leg.or.measure"
    assert s.metadata["priority"] == "ELEVATED"          # chapter number → signed
    assert s.metadata["bill"] == "HB 4177"
    assert s.url.endswith("/2026R1/Measures/Overview/HB4177")
    assert "prohibitions.." not in s.text
    assert s.published_at.date().isoformat() == "2026-09-28"


def test_measure_stale_and_undated_are_dropped():
    counts = _counts()
    bills = _bills(_raw_measure(number=1, modified="2026-01-02T00:00:00"),
                   _raw_measure(number=2, modified=None, CreatedDate=None))
    assert bridge.olis_measure_signals(bills, since=SINCE, run_id="r",
                                       environment="t", counts=counts) == []
    assert counts["dropped_stale"] == 1 and counts["dropped_no_date"] == 1


def test_measure_signal_id_is_stable_and_changes_with_new_action():
    a = bridge.olis_measure_signals(_bills(_raw_measure()), since=SINCE, run_id="r1",
                                    environment="t", counts=_counts())[0]
    b = bridge.olis_measure_signals(_bills(_raw_measure()), since=SINCE, run_id="r2",
                                    environment="t", counts=_counts())[0]
    c = bridge.olis_measure_signals(_bills(_raw_measure(modified="2026-10-01T09:00:00")),
                                    since=SINCE, run_id="r3", environment="t", counts=_counts())[0]
    assert a.signal_id == b.signal_id
    assert a.signal_id != c.signal_id


# ── Bridge: interim committees ────────────────────────────────────────────────

def test_interim_signal_shape():
    s = bridge.olis_interim_signals([_meeting()], since=SINCE, until=UNTIL, run_id="r",
                                    environment="t", counts=_counts())[0]
    assert s.source == "olis_interim"
    assert s.metadata["domain"] == "state_leg.or.interim_committee"
    assert s.metadata["priority"] == "STANDARD"           # agenda names a measure
    assert s.metadata["bill"] == "SB 1582"
    assert s.metadata["status"] == "held"
    assert "Ukraine Update" in s.text and "SB 1582: Rural electric" in s.text


def test_interim_upcoming_meeting_is_scheduled_and_kept():
    upcoming = datetime.now(timezone.utc) + timedelta(days=3)
    s = bridge.olis_interim_signals(
        [_meeting(when=upcoming, items=[{"text": "Wildfire funding", "measure": ""}])],
        since=SINCE, until=datetime.now(timezone.utc) + timedelta(days=14), run_id="r",
        environment="t", counts=_counts())[0]
    assert s.metadata["status"] == "scheduled"
    assert s.metadata["priority"] == "MONITOR"            # no measure on the agenda
    assert "scheduled for" in s.text


def test_interim_empty_agenda_and_out_of_window_dropped():
    counts = _counts()
    out = bridge.olis_interim_signals(
        [_meeting(items=[]), _meeting(when=NOW - timedelta(days=200))],
        since=SINCE, until=UNTIL, run_id="r", environment="t", counts=counts)
    assert out == []
    assert counts["dropped_empty_agenda"] == 1 and counts["dropped_stale"] == 1


# ── Bridge: other states ──────────────────────────────────────────────────────

def test_state_leg_synthetic_dropped_real_kept():
    counts = _counts()
    out = bridge.state_leg_signals([_state_rec("CA"), _state_rec("TX", source="synthetic")],
                                   since=SINCE, run_id="r", environment="t", counts=counts)
    assert [s.metadata["state"] for s in out] == ["CA"]
    assert out[0].metadata["domain"] == "state_leg.ca.bill"
    assert out[0].metadata["priority"] == "ELEVATED"
    assert counts["dropped_synthetic"] == 1


def test_state_leg_stale_dropped():
    counts = _counts()
    old = (NOW - timedelta(days=400)).date().isoformat()
    assert bridge.state_leg_signals([_state_rec(filed=old)], since=SINCE, run_id="r",
                                    environment="t", counts=counts) == []
    assert counts["dropped_stale"] == 1


# ── Bridge: orchestration ─────────────────────────────────────────────────────

def test_collect_merges_sources_priority_first():
    sigs, report = _collect()
    assert report["per_source"] == {"olis": 1, "olis_interim": 1, "state_legislative": 1}
    assert [s.metadata["priority"] for s in sigs] == ["ELEVATED", "ELEVATED", "STANDARD"]
    assert report["errors"] == []


def test_collect_dedups_seen_and_applies_limit():
    first, _ = _collect()
    sigs, report = _collect(seen_ids={first[0].signal_id}, limit=1)
    assert first[0].signal_id not in {s.signal_id for s in sigs}
    assert len(sigs) == 1
    assert report["counts"]["dropped_seen"] == 1
    assert report["counts"]["dropped_over_limit"] == 1


def test_collect_survives_a_dead_source():
    def boom():
        raise ConnectionError("OLIS down")
    sigs, report = _collect(olis_fetch=boom)
    assert report["per_source"]["olis"] == 0
    assert report["per_source"]["olis_interim"] == 1
    assert any("OLIS down" in e for e in report["errors"])
    assert sigs


# ── OLIS interim fetch (HTTP mocked) ──────────────────────────────────────────

def _odata(rows):
    resp = MagicMock()
    resp.json.return_value = {"value": rows}
    return resp


def test_fetch_interim_meetings_joins_agenda_and_cleans_text():
    meetings = [{"CommitteeCode": "EB", "MeetingDate": "2026-09-10T08:00:00",
                 "MeetingStatus": "Scheduled", "AgendaUrl": "https://olis.example/EB"}]
    items = [
        {"CommitteCode": "EB", "MeetingDate": "2026-09-10T08:00:00", "PrintOrder": 2,
         "Comments": "<b>Wildfire Funding Request</b>", "MeasurePrefix": None, "MeasureNumber": None},
        {"CommitteCode": "EB", "MeetingDate": "2026-09-10T08:00:00", "PrintOrder": 1,
         "Comments": "<u>Invited Speakers Only</u>", "MeasurePrefix": None, "MeasureNumber": None},
        {"CommitteCode": "EB", "MeetingDate": "2026-09-10T08:00:00", "PrintOrder": 3,
         "Comments": "", "MeasurePrefix": "HB", "MeasureNumber": 4036},
    ]
    committees = [{"CommitteeCode": "EB", "CommitteeName": "Emergency Board"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("CommitteeMeetings"):
            return _odata(meetings)
        if url.endswith("CommitteeAgendaItems"):
            return _odata(items)
        return _odata(committees)

    with patch.object(olis.requests, "get", side_effect=fake_get) as get:
        out = olis.fetch_interim_meetings("2025I1", SINCE, UNTIL)
    m = out[0]
    assert m["committee_name"] == "Emergency Board"
    assert m["meeting_date"].tzinfo == PACIFIC
    assert m["items"] == [{"text": "Wildfire Funding Request", "measure": ""},
                          {"text": "", "measure": "HB 4036"}]
    window = get.call_args_list[0].kwargs["params"]["$filter"]
    assert "SessionKey eq '2025I1'" in window and "MeetingDate ge datetime'" in window


def test_latest_interim_session_key_falls_back_offline():
    import requests
    with patch.object(olis.requests, "get", side_effect=requests.ConnectionError("down")):
        assert olis.latest_interim_session_key() == "2025I1"


def test_latest_interim_session_key_picks_newest_interim():
    rows = [{"SessionKey": "2026R1"}, {"SessionKey": "2025S1"}, {"SessionKey": "2025I1"}]
    with patch.object(olis.requests, "get", return_value=_odata(rows)):
        assert olis.latest_interim_session_key() == "2025I1"


# ── Writer prefix ─────────────────────────────────────────────────────────────

def test_write_brief_prefix_uses_own_files_and_index(tmp_path, monkeypatch):
    from spec1_core.briefing import writer
    monkeypatch.setattr(writer, "BRIEFS_DIR", tmp_path)
    path = writer.write_brief("# Leg", "run-x", "2026-10-25T12:00:00+00:00", prefix="spec1_legislative")
    assert path.endswith("spec1_legislative_2026-10-25.md")
    names = {p.name for p in tmp_path.iterdir()}
    assert {"spec1_legislative_latest.md", "spec1_legislative_prompts_2026-10-25.md",
            "spec1_legislative_index.jsonl"} <= names
    assert "brief_index.jsonl" not in names and "spec1_brief_latest.md" not in names

    writer.write_brief_meta(path, run_id="run-x", records_tier=ANALYSIS_TIER_LLM_VERIFIED,
                            brief_source="model", latest_name="spec1_legislative_latest.md")
    assert (tmp_path / "spec1_legislative_latest.meta.json").exists()
    assert not (tmp_path / "spec1_brief_latest.meta.json").exists()


# ── Scorer helper ─────────────────────────────────────────────────────────────

def test_composite_score_matches_score_signal():
    from spec1_core.signal.parser import parse_signal
    from spec1_core.signal.scorer import composite_score, evaluate_gates, score_signal
    sig = bridge.olis_measure_signals(_bills(_raw_measure()), since=SINCE, run_id="r",
                                      environment="t", counts=_counts())[0]
    ps = parse_signal(sig)
    ev = evaluate_gates(sig, ps)
    opp = score_signal(sig, ps)
    assert opp is None or opp.score == composite_score(ev)
    assert 0.0 <= composite_score(ev) <= 1.0


# ── Desk cycle ────────────────────────────────────────────────────────────────

def _fake_collect(**kwargs):
    sigs, report = _collect(run_id=kwargs["run_id"], seen_ids=kwargs.get("seen_ids"),
                            limit=kwargs.get("limit"))
    return sigs, report


def _verified(inv, article="", source="", use_llm=True):
    tier = ANALYSIS_TIER_LLM_VERIFIED if use_llm else ANALYSIS_TIER_RULE_BASED
    return Outcome(outcome_id="out-1", classification="INVESTIGATE", confidence=0.7,
                   evidence=["LLM assessment: bill materially changes disclosure."],
                   analysis_tier=tier)


@pytest.fixture
def desk_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEC1_LEG_JUD_PATH", str(tmp_path / "leg_jud_briefs.jsonl"))
    from spec1_core.app import legislative_desk
    monkeypatch.setattr(legislative_desk, "verify_investigation", _verified)
    return tmp_path


def test_desk_stores_records_and_writes_legislative_brief(desk_env):
    from spec1_core.app import legislative_desk
    from spec1_core.briefing import generator, writer
    store = desk_env / "spec1_legislative.jsonl"
    calls = []

    def fake_generate(records, stats, mode="standard"):
        calls.append(mode)
        stats["brief_backend"] = "local"
        return "## LEGISLATIVE BRIEF\nBody.", "## SYSTEM PROMPT\n\n---\n\n## USER PROMPT\n"

    with patch.object(generator, "generate_brief", side_effect=fake_generate):
        stats = legislative_desk.run_legislative_desk(
            store_path=store, run_id="run-leg1", verbose=False, collect=_fake_collect)

    assert stats["records_stored"] == 3
    assert stats["records_tier"] == ANALYSIS_TIER_LLM_VERIFIED
    assert calls == ["legislative"]
    rows = [json.loads(line) for line in store.read_text().splitlines()]
    assert {r["domain"] for r in rows} == {
        "state_leg.or.measure", "state_leg.or.interim_committee", "state_leg.ca.bill"}
    assert all(r["desk"] == "legislative" and r["gate_results"]["bypassed"] for r in rows)
    assert all(r["analysis_tier"] == ANALYSIS_TIER_LLM_VERIFIED for r in rows)

    brief_path = Path(stats["brief_path"])
    assert brief_path.name.startswith("spec1_legislative_")
    assert brief_path.parent == writer.BRIEFS_DIR
    meta = json.loads(Path(stats["brief_meta_path"]).read_text())
    assert meta["analysis_tier"] == ANALYSIS_TIER_LLM_VERIFIED
    assert not (writer.BRIEFS_DIR / "spec1_brief_latest.md").exists()

    leg = [json.loads(line) for line in (desk_env / "leg_jud_briefs.jsonl").read_text().splitlines()]
    assert leg[-1]["run_id"] == "run-leg1" and leg[-1]["eligible_records"] == 3


def test_desk_second_run_skips_stored_candidates(desk_env):
    from spec1_core.app import legislative_desk
    store = desk_env / "spec1_legislative.jsonl"
    legislative_desk.run_legislative_desk(store_path=store, run_id="r1", verbose=False,
                                          collect=_fake_collect)
    stats = legislative_desk.run_legislative_desk(store_path=store, run_id="r2", verbose=False,
                                                  collect=_fake_collect)
    assert stats["records_stored"] == 0
    assert stats["signals_skipped_seen"] == 3
    assert "brief_path" not in stats


def test_desk_triage_only_is_rule_based_and_writes_no_brief(desk_env):
    from spec1_core.app import legislative_desk
    from spec1_core.briefing import generator
    with patch.object(generator, "generate_brief") as gen:
        stats = legislative_desk.run_legislative_desk(
            store_path=desk_env / "leg.jsonl", run_id="r", verbose=False,
            triage_only=True, collect=_fake_collect)
    gen.assert_not_called()
    assert stats["records_tier"] == ANALYSIS_TIER_RULE_BASED
    assert stats["analysis_tiers"][ANALYSIS_TIER_RULE_BASED] == 3
    assert "brief_path" not in stats


def test_run_cycle_dispatches_legislative_desk(monkeypatch):
    from spec1_core.app import cycle, legislative_desk
    seen = {}

    def spy(**kwargs):
        seen.update(kwargs)
        return {"records_stored": 0}

    monkeypatch.setattr(legislative_desk, "run_legislative_desk", spy)
    cycle.run_cycle(desk="legislative", since_days=90, max_signals=5, verbose=False)
    assert seen["store_path"] == cycle.LEGISLATIVE_STORE_PATH
    assert seen["since_days"] == 90 and seen["max_signals"] == 5


def test_run_cycle_rejects_unknown_desk():
    from spec1_core.app import cycle
    with pytest.raises(ValueError):
        cycle.run_cycle(desk="sports", verbose=False)
