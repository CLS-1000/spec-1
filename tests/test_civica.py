# @domain:   civica
# @module:   test_civica
# @status:   testing

"""cls_civica unit tests: plain-language cards and the publication gate.

No network, no sibling repos: histories here are hand-built in proc_track's
Item.history shape (occurred_at, chamber, from_state, to_state, rule_id).
End-to-end build + seal + tamper tests live in test_civica_e2e.py.
"""

from __future__ import annotations

from cls_civica import labels as L
from cls_civica import policy
from cls_civica.plain import build_card, outcome_of, topics_of


def _row(hid, date, chamber, text, prefix="SB", number=976, session="2025R1"):
    return {"MeasureHistoryId": hid, "SessionKey": session, "MeasurePrefix": prefix,
            "MeasureNumber": number, "Chamber": chamber, "ActionDate": date,
            "ActionText": text, "VoteText": None, "CreatedDate": date,
            "ModifiedDate": None, "PublicNotification": False}


VETO_ROWS = [
    _row(1, "2025-02-04T10:49:12", "S", "Introduction and first reading. Referred to President's desk."),
    _row(2, "2025-06-23T15:36:12", "S", "Third reading. Passed."),
    _row(3, "2025-06-23T15:57:17", "H", "First reading. Referred to Speaker's desk."),
    _row(4, "2025-06-26T14:57:08", "H", "Third reading. Passed."),
    _row(5, "2025-06-27T15:58:40", "S", "President signed."),
    _row(6, "2025-08-07T20:25:00", "S", "Governor vetoed."),
    _row(7, "2025-10-01T09:27:00", "S", "Veto sustained."),
]
VETO_HISTORY = [
    ("2025-02-04T10:49:12", "S", None, "introduced", "introduction_first_reading"),
    ("2025-06-23T15:36:12", "S", "third_reading", "passed", "passed"),
    ("2025-06-23T15:57:17", "H", None, "introduced", "first_reading"),
    ("2025-06-26T14:57:08", "H", "third_reading", "passed", "passed"),
    ("2025-06-27T15:58:40", "S", "passed", "signed_by_presiding", "president_signed"),
    ("2025-08-07T20:25:00", "S", "signed_by_presiding", "vetoed", "governor_vetoed"),
    ("2025-10-01T09:27:00", "S", "vetoed", "veto_sustained", "veto_sustained"),
]


def _card(**kw):
    args = dict(session="2025R1", measure_id="SB976", rows=VETO_ROWS, history=VETO_HISTORY,
                states={"S": "veto_sustained", "H": "signed_by_presiding"}, halt=None)
    args.update(kw)
    return build_card(**args)


def _inputs(card):
    d = card.to_dict()
    return {"card": d, "evidence_digest": "sha256:" + "0" * 64,
            "source_row_ids": [r["MeasureHistoryId"] for r in VETO_ROWS]}


class TestOutcome:
    def test_enacted_is_law(self):
        assert outcome_of("HB", {"H": "enacted", "S": "signed_by_presiding"}, False) == L.OUTCOME_LAW

    def test_veto_sustained(self):
        assert outcome_of("SB", {"S": "veto_sustained"}, False) == L.OUTCOME_VETOED

    def test_resolution_signed_is_adopted(self):
        assert outcome_of("HCR", {"H": "signed_by_presiding"}, False) == L.OUTCOME_ADOPTED

    def test_bill_signed_by_presiding_only_passed_legislature(self):
        assert outcome_of("HB", {"H": "signed_by_presiding"}, False) == L.OUTCOME_PASSED

    def test_halt_is_never_a_verified_outcome(self):
        assert outcome_of("HB", {"H": "enacted"}, True) == L.OUTCOME_HALTED

    def test_committee_is_stopped(self):
        assert outcome_of("HB", {"H": "committee"}, False) == L.OUTCOME_STOPPED

    def test_line_item_veto_is_law(self):
        assert outcome_of("SB", {"S": "line_item_veto_sustained", "H": "signed_by_presiding"}, False) == L.OUTCOME_LAW
        assert outcome_of("SB", {"S": "enacted_line_item_veto"}, False) == L.OUTCOME_LAW

    def test_override_is_law(self):
        assert outcome_of("SB", {"S": "veto_overridden", "H": "veto_overridden"}, False) == L.OUTCOME_LAW

    def test_tabled_after_veto_is_vetoed(self):
        hist = (("2021-08-06T10:40:45", "S", "signed_by_presiding", "vetoed", "governor_vetoed"),
                ("2021-09-20T10:41:00", "S", "vetoed", "tabled", "motion_to_table"))
        assert outcome_of("SB", {"S": "tabled", "H": "signed_by_presiding"}, False, hist) == L.OUTCOME_VETOED

    def test_tabled_without_veto_is_not_vetoed(self):
        hist = (("2025-04-01T10:00:00", "H", "passed", "tabled", "tabled_simple"),)
        assert outcome_of("HB", {"H": "tabled"}, False, hist) == L.OUTCOME_STOPPED


class TestTopics:
    def test_joint_resolution_is_ballot(self):
        assert L.TOPIC_BALLOT in topics_of("SJR", None, L.OUTCOME_STOPPED)

    def test_elections_needs_title(self):
        assert L.TOPIC_ELECTIONS not in topics_of("HB", None, L.OUTCOME_STOPPED)
        assert L.TOPIC_ELECTIONS in topics_of("HB", "Relating to ballot signature verification", L.OUTCOME_STOPPED)

    def test_veto_topic(self):
        assert topics_of("SB", None, L.OUTCOME_VETOED) == [L.TOPIC_VETO]


class TestCard:
    def test_veto_card_claims_and_dates(self):
        c = _card()
        assert c.outcome == L.OUTCOME_VETOED
        assert c.headline == "SB 976 was vetoed by the Governor"
        texts = [x.text for x in c.claims]
        assert "The Governor vetoed SB 976 on August 7, 2025." in texts
        assert "The veto stood (recorded October 1, 2025)." in texts
        assert c.subject == "or_legislature/2025R1/SB976"

    def test_every_claim_cites_real_rows(self):
        c = _card()
        ids = {r["MeasureHistoryId"] for r in VETO_ROWS}
        for claim in c.claims:
            assert claim.row_ids and set(claim.row_ids) <= ids

    def test_second_chamber_arrival_wording(self):
        c = _card()
        assert any(t["text"] == "Arrived in the House" for t in c.timeline)

    def test_source_is_official_api(self):
        assert _card().source_url.startswith(L.OLIS_HOST_PREFIX)

    def test_repassed_before_veto_is_not_an_override(self):
        rows = VETO_ROWS[:2] + [_row(8, "2025-06-24T10:00:00", "S", "Repassed.")] + VETO_ROWS[2:]
        hist = VETO_HISTORY[:2] + [("2025-06-24T10:00:00", "S", "passed", "passed", "repassed")] + VETO_HISTORY[2:]
        c = _card(rows=rows, history=hist)
        assert not any("over the veto" in x.text for x in c.claims)

    def test_override_attempt_after_veto_is_reported(self):
        rows = VETO_ROWS[:6] + [_row(9, "2025-08-20T10:00:00", "S", "Repassed notwithstanding veto.")] + VETO_ROWS[6:]
        hist = VETO_HISTORY[:6] + [("2025-08-20T10:00:00", "S", "vetoed", "vetoed", "repassed")] + VETO_HISTORY[6:]
        c = _card(rows=rows, history=hist)
        assert any("voted to pass it over the veto" in x.text for x in c.claims)

    def test_joint_resolution_ballot_claim(self):
        rows = [_row(1, "2025-01-13T08:00:00", "H", "First reading.", "HJR", 1),
                _row(2, "2025-06-27T12:00:00", "H", "In committee upon adjournment.", "HJR", 1)]
        hist = [("2025-01-13T08:00:00", "H", None, "introduced", "first_reading"),
                ("2025-01-13T08:00:00", "H", "introduced", "committee", "referred_to")]
        c = build_card("2025R1", "HJR1", rows, hist, {"H": "committee"}, None)
        assert c.outcome == L.OUTCOME_STOPPED
        assert L.TOPIC_BALLOT in c.topics
        assert any("will not be on your ballot" in x.text for x in c.claims)
        assert any("still in a House committee when the session ended" in x.text for x in c.claims)

    def test_halted_card_is_labelled_not_verified(self):
        c = _card(halt="S: passed -> second_reading not allowed  [rule=x row='y']")
        assert c.outcome == L.OUTCOME_HALTED and not c.verified
        assert "could not be fully verified" in c.headline
        assert not any("every move was a legal one" in x.text for x in c.claims)


class TestPublicationGate:
    def test_allows_sourced_card(self):
        ok, detail = policy.decide(_inputs(_card()))
        assert ok is True and "sourced claims" in detail

    def test_denies_unsourced_claim(self):
        inp = _inputs(_card())
        inp["card"]["claims"][0]["row_ids"] = []
        assert policy.decide(inp) == (False, "claim 0 is unsourced")

    def test_denies_claim_citing_rows_outside_evidence(self):
        inp = _inputs(_card())
        inp["card"]["claims"][1]["row_ids"] = [999999]
        ok, detail = policy.decide(inp)
        assert ok is False and "not in evidence" in detail

    def test_denies_non_official_source(self):
        inp = _inputs(_card())
        inp["card"]["source_url"] = "https://example.com/fake"
        assert policy.decide(inp)[0] is False

    def test_denies_missing_evidence(self):
        inp = _inputs(_card())
        inp["evidence_digest"] = ""
        assert policy.decide(inp) == (False, "evidence not recorded before decision")

    def test_denies_unverified_dressed_as_verified(self):
        inp = _inputs(_card(halt="boom"))
        inp["card"]["outcome"] = L.OUTCOME_LAW
        assert policy.decide(inp)[0] is False

    def test_allows_honestly_labelled_unverified(self):
        assert policy.decide(_inputs(_card(halt="boom")))[0] is True

    def test_does_not_police_tone(self):
        inp = _inputs(_card())
        inp["card"]["claims"][0]["text"] = "Alarming: this bill was vetoed after a 3x acceleration."
        assert policy.decide(inp)[0] is True
