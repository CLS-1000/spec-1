# @domain:   handler
# @module:   test_audit_tier
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""run_audit records the tier that actually answered, and never turns a non-audit
response into an audit score."""

from __future__ import annotations

import json
from unittest.mock import patch

from cls_analyst_loop.audit import run_audit

GOOD_AUDIT = json.dumps({
    "claims_confirmed": 4,
    "claims_flagged": 1,
    "claims_dropped": 0,
    "confidence": 0.82,
    "findings": [{"claim": "x", "problem": "y", "severity": "LOW", "suggested_edit": "z"}],
})

# What tier3_rules.to_verifier_json returns: valid JSON with its own confidence.
VERIFIER_JSON = json.dumps({
    "verified": True, "confidence": 0.65, "reasoning": "rules", "classification": "Investigate",
})


class _FakeClient:
    def __init__(self, text: str, tier: str):
        self._text, self._tier = text, tier

    def complete(self, prompt: str, system: str = "") -> str:
        return self._text

    def get_active_tier(self) -> str:
        return self._tier


def _audit(text: str, tier: str):
    with patch("cls_analyst_loop.audit.FallbackLLMClient", return_value=_FakeClient(text, tier)):
        return run_audit("output_abc", "report text", "source data")


def test_model_audit_keeps_its_scores_and_real_tier():
    for tier in ("claude", "ollama"):
        result = _audit(GOOD_AUDIT, tier)
        assert result.audit_llm == tier
        assert result.confidence == 0.82
        assert result.claims_confirmed == 4


def test_rules_tier_is_recorded_as_no_audit_not_as_a_score():
    result = _audit(VERIFIER_JSON, "mock")
    assert result.audit_llm == "mock"
    assert result.confidence == 0.0
    assert result.claims_confirmed == 0
    findings = json.loads(result.audit_output)["findings"]
    assert findings[0]["severity"] == "HIGH"
    assert "rule-based" in findings[0]["problem"]


def test_unparseable_or_wrong_shape_response_is_a_null_audit():
    for text in ("not json at all", VERIFIER_JSON):
        result = _audit(text, "claude")
        assert result.confidence == 0.0
        assert json.loads(result.audit_output)["findings"][0]["severity"] == "HIGH"
