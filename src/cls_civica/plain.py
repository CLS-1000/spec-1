# @domain:   civica
# @module:   civica_plain
# @status:   mvp

"""Turn a proc_track replay into a plain-language card.

Deterministic, no LLM. Every sentence on a card is a `claim` that cites the
official action rows (MeasureHistoryId) it rests on, so the publication gate
can check that nothing on the page is unsourced (DESIGN_INTENT §4: neutrality
is accountability to evidence, not tone).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from cls_civica import labels as L

# proc_track state -> how a resident would say it. {ch} = chamber, {po} = presiding officer.
_STEP_WORDS = {
    "introduced": "Introduced in the {ch}",
    "committee": "Sent to a {ch} committee",
    "public_hearing": "Public hearing held in a {ch} committee",
    "work_session": "{ch} committee met to work on it",
    "second_reading": "Second reading on the {ch} floor",
    "third_reading": "Final reading on the {ch} floor",
    "passed": "Passed the {ch}",
    "failed": "Voted down in the {ch}",
    "tabled": "Set aside (tabled) in the {ch}",
    "adopted": "Adopted by the {ch}",
    "signed_by_presiding": "Signed by the {po}",
    "vetoed": "Vetoed by the Governor",
    "veto_sustained": "Veto stood: the Legislature did not override it",
    "line_item_veto_sustained": "The vetoed parts stayed out: the Legislature did not override them",
    "overridden": "Legislature overrode the Governor's veto",
    "enacted": "Signed into law by the Governor",
}

# proc_track rule_id -> wording, where the rule says more than the state it lands in
# (e.g. a do-pass recommendation returns the bill to "committee" state).
_RULE_WORDS = {
    "rec_do_pass": "{ch} committee recommended it pass",
    "rec_do_adopt": "{ch} committee recommended it be adopted",
    "rec_be_adopted": "{ch} committee recommended it be adopted",
    "rec_none": "{ch} committee sent it on with no recommendation",
    "returned_full_committee": "Returned to the full {ch} committee",
    "assigned_subcommittee": "Assigned to a {ch} subcommittee",
    "subsequent_referral": "Sent to another {ch} committee",
    "repass_notwithstanding": "{ch} voted to pass it over the Governor's veto",
    "veto_overridden": "Legislature overrode the Governor's veto",
    "motion_to_table:line_item_veto_message_tabled": "{ch} set aside the Governor's line-item veto message; the law stands",
    "line_item_veto": "Governor vetoed part of it (line-item veto)",
    "enacted_line_item_veto": "Signed into law, with part of it vetoed (line-item veto)",
    "governor_signed_line_item": "Signed into law, with part of it vetoed (line-item veto)",
    "filed_without_signature": "Became law without the Governor's signature",
    "filed_sos": "Filed with the Secretary of State",
    "withdrawn_committee": "Withdrawn from a {ch} committee",
}

_OVERRIDE_RULES = {"repassed", "repass_notwithstanding"}

_ELECTION_WORDS = re.compile(
    r"\b(election|elections|ballot|ballots|voter|voters|voting|vote by mail|"
    r"signature verification|county clerk|secretary of state|initiative|referendum|"
    r"recall|campaign finance|redistricting|ranked choice)\b",
    re.IGNORECASE,
)


@dataclass
class Claim:
    text: str
    row_ids: list[int]


@dataclass
class Card:
    session: str
    measure: str            # "SB 976"
    measure_id: str         # "SB976"
    subject: str            # gatepost subject: or_legislature/2025R1/SB976
    title: Optional[str]
    outcome: str
    outcome_label: str
    headline: str
    claims: list[Claim]
    timeline: list[dict]
    topics: list[str]
    verified: bool
    halt_reason: Optional[str]
    last_action_date: str
    source_url: str
    public_url: str
    row_count: int
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _date(ts: str) -> str:
    """'2025-06-23T15:36:12' -> 'June 23, 2025'."""
    dt = datetime.fromisoformat(ts[:19])
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def _split(measure_id: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)$", measure_id)
    if not m:
        raise ValueError(f"bad measure id {measure_id!r}")
    return m.group(1), int(m.group(2))


def source_query(session: str, prefix: str, number: int) -> str:
    """The exact official OData query for this measure's action history."""
    return (
        f"{L.OLIS_API}/MeasureHistoryActions?$filter=SessionKey eq '{session}' and "
        f"MeasurePrefix eq '{prefix}' and MeasureNumber eq {number}&$orderby=ActionDate&$format=json"
    )


# proc_track end states, by what they mean for the measure.
_LAW_STATES = {"enacted", "enacted_line_item_veto", "line_item_veto_sustained", "veto_overridden"}
_VETO_STATES = {"vetoed", "veto_sustained"}


def outcome_of(prefix: str, states: dict[str, str], halted: bool, history: tuple = ()) -> str:
    """history: proc_track Item.history rows (occurred_at, chamber, from, to, rule_id).

    A line-item veto is still a law. "tabled" after a veto means the veto stood
    (SB 721, 2021R1); "tabled" without one is a bill set aside, not a veto.
    """
    if halted:
        return L.OUTCOME_HALTED
    vals = set(states.values())
    if vals & _LAW_STATES:
        return L.OUTCOME_LAW
    was_vetoed = any(h[3] == "vetoed" for h in history)
    if vals & _VETO_STATES or ("tabled" in vals and was_vetoed):
        return L.OUTCOME_VETOED
    if "adopted" in vals:
        return L.OUTCOME_ADOPTED
    if "signed_by_presiding" in vals:
        return L.OUTCOME_ADOPTED if prefix in L.NON_GOVERNOR_MEASURES else L.OUTCOME_PASSED
    if "failed" in vals:
        return L.OUTCOME_FAILED
    return L.OUTCOME_STOPPED


def topics_of(prefix: str, title: Optional[str], outcome: str) -> list[str]:
    t: list[str] = []
    if prefix in L.JOINT_RESOLUTIONS:
        t.append(L.TOPIC_BALLOT)
    if title and _ELECTION_WORDS.search(title):
        t.append(L.TOPIC_ELECTIONS)
    if outcome == L.OUTCOME_VETOED:
        t.append(L.TOPIC_VETO)
    return t


def _step_text(state: str, chamber: str, rule_id: str = "", second_chamber: bool = False) -> str:
    if state == "introduced" and second_chamber:
        tmpl = "Arrived in the {ch}"
    else:
        tmpl = _RULE_WORDS.get(rule_id) or _STEP_WORDS.get(state, state.replace("_", " ").capitalize() + " ({ch})")
    return tmpl.format(ch=L.CHAMBER_NAMES.get(chamber, chamber), po=L.PRESIDING_OFFICER.get(chamber, "presiding officer"))


def _stopped_sentence(measure: str, states: dict[str, str], origin: str, closed: bool) -> str:
    """Where a bill that did not pass got stuck, in plain words."""
    name = L.CHAMBER_NAMES
    ended = "when the session ended" if closed else "so far"
    passed = [c for c, s in states.items() if s == "passed"]
    if passed:
        other = [c for c in states if c not in passed]
        other_name = name.get(other[0], "other chamber") if other else ("Senate" if passed[0] == "H" else "House")
        return f"{measure} passed the {name.get(passed[0], passed[0])} but did not pass the {other_name}."
    c, s = next(iter(states.items())) if states else (origin, "introduced")
    ch = name.get(c, c)
    if s == "tabled":
        return f"{measure} was set aside (tabled) in the {ch}."
    if s in ("second_reading", "third_reading"):
        return f"{measure} reached the {ch} floor but did not get a final vote {ended}."
    if s in ("committee", "public_hearing", "work_session", "introduced"):
        return f"{measure} was still in a {ch} committee {ended}."
    return f"{measure} did not pass; its last state in the {ch} was {s.replace('_', ' ')}."


def build_card(
    session: str,
    measure_id: str,
    rows: list[dict],
    history: list[tuple],
    states: dict[str, str],
    halt: Optional[str],
    title: Optional[str] = None,
    session_closed: bool = True,
) -> Card:
    """rows: official action rows sorted by ActionDate. history: proc_track Item.history."""
    if not rows:
        raise ValueError(f"{measure_id}: no action rows")
    prefix, number = _split(measure_id)
    measure = f"{prefix} {number}"
    halted = halt is not None
    outcome = outcome_of(prefix, states, halted, tuple(history))
    by_date: dict[str, list[int]] = {}
    for r in rows:
        by_date.setdefault(r["ActionDate"][:19], []).append(int(r["MeasureHistoryId"]))

    # Timeline: one line per real state change (collapse committee->committee re-referrals).
    timeline: list[dict] = []
    origin_chamber = rows[0]["Chamber"]
    seen_veto = False
    for occurred_at, chamber, frm, to, rule_id in history:
        if frm == to and rule_id not in _RULE_WORDS and rule_id not in _OVERRIDE_RULES:
            continue
        ids = by_date.get(occurred_at[:19], [])
        text = _step_text(to, chamber, rule_id, second_chamber=chamber != origin_chamber)
        if seen_veto and rule_id in _OVERRIDE_RULES:
            text = f"{L.CHAMBER_NAMES.get(chamber, chamber)} voted to pass it over the Governor's veto"
        seen_veto = seen_veto or to == "vetoed"
        timeline.append({
            "date": occurred_at[:10],
            "when": _date(occurred_at),
            "chamber": chamber,
            "state": to,
            "text": text,
            "rule_id": rule_id,
            "row_ids": ids,
        })

    first, last = rows[0], rows[-1]
    first_ids = [int(first["MeasureHistoryId"])]
    last_ids = [int(last["MeasureHistoryId"])]
    origin = L.CHAMBER_NAMES.get(first["Chamber"], first["Chamber"])
    claims: list[Claim] = [Claim(f"{measure} was introduced in the {origin} on {_date(first['ActionDate'])}.", first_ids)]

    if halted:
        headline = f"{measure}: history could not be fully verified"
        claims.append(Claim(
            f"The official history could not be checked step by step ({halt.split('  [')[0]}). "
            "It is shown as recorded, not as verified.", last_ids))
    else:
        steps = [t for t in timeline if t["state"] not in ("introduced",)]
        key = {
            L.OUTCOME_LAW: "enacted",
            L.OUTCOME_VETOED: "veto_sustained" if "veto_sustained" in states.values() else "vetoed",
            L.OUTCOME_ADOPTED: None,
            L.OUTCOME_PASSED: "signed_by_presiding",
        }.get(outcome)
        anchor = next((t for t in reversed(steps) if key and t["state"] == key), None)
        if outcome == L.OUTCOME_LAW and anchor:
            headline = f"{measure} became law"
            claims.append(Claim(f"The Governor signed {measure} into law on {anchor['when']}.", anchor["row_ids"] or last_ids))
        elif outcome == L.OUTCOME_VETOED:
            veto = next((t for t in steps if t["state"] == "vetoed"), None)
            headline = f"{measure} was vetoed by the Governor"
            if veto:
                claims.append(Claim(f"The Governor vetoed {measure} on {veto['when']}.", veto["row_ids"] or last_ids))
            # "Repassed" before a veto is concurrence in amendments, not an override attempt.
            after_veto = steps[steps.index(veto) + 1:] if veto else []
            for t in after_veto:
                if t["rule_id"] in _OVERRIDE_RULES:
                    claims.append(Claim(
                        f"On {t['when']} the {L.CHAMBER_NAMES.get(t['chamber'], t['chamber'])} voted to pass it "
                        "over the veto, but an override needs both chambers.", t["row_ids"] or last_ids))
            if anchor and anchor["state"] == "veto_sustained":
                claims.append(Claim(f"The veto stood (recorded {anchor['when']}).", anchor["row_ids"] or last_ids))
        elif outcome == L.OUTCOME_ADOPTED:
            headline = f"{measure} was adopted"
            claims.append(Claim(f"{measure} was adopted; the last recorded step was on {_date(last['ActionDate'])}.", last_ids))
        elif outcome == L.OUTCOME_PASSED:
            headline = f"{measure} passed the Legislature"
            claims.append(Claim(f"{measure} passed both chambers; the last recorded step was on {_date(last['ActionDate'])}.", last_ids))
        elif outcome == L.OUTCOME_FAILED:
            fail = next((t for t in steps if t["state"] == "failed"), None)
            headline = f"{measure} was voted down"
            claims.append(Claim(f"{measure} was voted down{' on ' + fail['when'] if fail else ''}.", (fail or {}).get("row_ids") or last_ids))
        else:
            headline = f"{measure} did not pass" if session_closed else f"{measure} is still in progress"
            claims.append(Claim(
                _stopped_sentence(measure, states, first["Chamber"], session_closed)
                + f" Last recorded step: {_date(last['ActionDate'])}.", last_ids))
        claims.append(Claim(
            f"Each of the {len(rows)} recorded steps was checked against Oregon's chamber procedure "
            "and every move was a legal one.", [int(r["MeasureHistoryId"]) for r in rows]))

    if prefix in L.JOINT_RESOLUTIONS:
        if outcome in (L.OUTCOME_ADOPTED, L.OUTCOME_PASSED):
            claims.append(Claim(f"{measure} is a proposed change to the Oregon Constitution. Because it passed, it goes to voters.", last_ids))
        else:
            claims.append(Claim(
                f"{measure} is a proposed change to the Oregon Constitution. It would have gone to voters "
                "if passed; it did not pass, so it will not be on your ballot.", last_ids))

    return Card(
        session=session,
        measure=measure,
        measure_id=measure_id,
        subject=f"or_legislature/{session}/{measure_id}",
        title=title,
        outcome=outcome,
        outcome_label=L.OUTCOME_LABELS[outcome],
        headline=headline,
        claims=claims,
        timeline=timeline,
        topics=topics_of(prefix, title, outcome),
        verified=not halted,
        halt_reason=halt,
        last_action_date=last["ActionDate"][:10],
        source_url=source_query(session, prefix, number),
        public_url=L.OLIS_PUBLIC_PAGE.format(session=session, prefix=prefix, number=number),
        row_count=len(rows),
    )
