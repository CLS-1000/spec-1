# @domain:   spec-1
# @module:   test_pdx1_neutrality
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for cls_pdx1.neutrality gates."""

from __future__ import annotations


from cls_pdx1.neutrality.tone import tone_gate, LOADED_VERBS
from cls_pdx1.neutrality.attribution import attribution_gate
from cls_pdx1.neutrality.section import section_gate


class TestToneGate:
    def test_neutral_text_passes(self):
        ok, reason = tone_gate("The council voted to approve the measure.")
        assert ok
        assert reason is None

    def test_loaded_verb_fails(self):
        ok, reason = tone_gate("The official admitted wrongdoing.")
        assert not ok
        assert "TONE_001" in (reason or "")

    def test_slammed_fails(self):
        ok, reason = tone_gate("The mayor slammed the decision.")
        assert not ok

    def test_neutral_verbs_allowed(self):
        for verb in ("said", "stated", "proposed", "voted", "noted"):
            ok, _ = tone_gate(f"The official {verb} the policy.")
            assert ok, f"Neutral verb '{verb}' should pass"

    def test_empty_text_passes(self):
        ok, _ = tone_gate("")
        assert ok

    def test_all_loaded_verbs_in_set(self):
        assert "admitted" in LOADED_VERBS
        assert "claimed" in LOADED_VERBS
        assert "slammed" in LOADED_VERBS

    def test_case_insensitive(self):
        ok, _ = tone_gate("The official ADMITTED the error.")
        assert not ok


class TestAttributionGate:
    def test_valid_https_uri_passes(self):
        ok, reason = attribution_gate("Some body text.", "https://example.com/source")
        assert ok

    def test_valid_http_uri_passes(self):
        ok, reason = attribution_gate("Body text.", "http://example.com/source")
        assert ok

    def test_empty_uri_fails(self):
        ok, reason = attribution_gate("Body text.", "")
        assert not ok
        assert "ATTR_001" in (reason or "")

    def test_ftp_uri_fails(self):
        ok, reason = attribution_gate("Body text.", "ftp://files.example.com")
        assert not ok

    def test_none_uri_fails(self):
        ok, reason = attribution_gate("Body.", None)
        assert not ok


class TestSectionGate:
    def test_clean_section_passes(self):
        ok, failures = section_gate(
            "City Council Votes on Budget",
            "The council voted to approve the annual budget.",
            "https://portland.gov/council",
        )
        assert ok
        assert failures == []

    def test_loaded_title_fails(self):
        ok, failures = section_gate(
            "Mayor Slammed by Critics",
            "The mayor stated the policy.",
            "https://portland.gov",
        )
        assert not ok
        assert any("TONE" in f for f in failures)

    def test_missing_source_uri_fails(self):
        ok, failures = section_gate(
            "Clean Title",
            "The council voted on the measure.",
            "",
        )
        assert not ok
        assert any("ATTR" in f for f in failures)

    def test_multiple_failures_collected(self):
        ok, failures = section_gate(
            "Official Admitted Wrongdoing",
            "The official claimed everything was fine.",
            "ftp://bad-uri",
        )
        assert not ok
        assert len(failures) >= 1  # at least tone failure
