# @domain:   handler
# @module:   audit
# @loc:      gh_main
# @status:   stable
# @depends:  cls_db

"""LLM audit runner for analyst outputs.

Audits check for:
1. Claims not supported by cited sources
2. Logical leaps beyond what evidence shows
3. Missing attribution
4. Fabricated entities/events/quotes
5. Confidence inflation

Returns JSON with findings and confidence score.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from spec1_core.llm.fallback_client import FallbackLLMClient

from cls_analyst_loop.schemas import AuditResult

logger = logging.getLogger(__name__)


AUDIT_SYSTEM_PROMPT = """You are auditing an intelligence report produced by an analyst.
Your job is not to rewrite the report. Your job is to flag problems.

Check for:
1. Claims not supported by the cited sources
2. Logical leaps beyond what the evidence shows
3. Missing attribution — assertions with no source
4. Fabricated entities, events, or quotes
5. Confidence inflation — conclusions stated as certain when evidence is ambiguous

For each finding:
- Quote the specific claim
- State the problem
- Rate severity: HIGH / MEDIUM / LOW
- Suggest minimum edit to resolve

Return JSON only:
{
  "claims_confirmed": int,
  "claims_flagged": int,
  "claims_dropped": int,
  "confidence": float (0.0 to 1.0),
  "findings": [
    {
      "claim": str,
      "problem": str,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "suggested_edit": str
    }
  ]
}"""


def run_audit(
    output_id: str,
    raw_output: str,
    source_data: str,
    audit_llm: str = "claude",
) -> AuditResult:
    """Run an LLM audit on analyst output via the three-tier FallbackLLMClient.

    Args:
        output_id: ID of the AnalystOutput being audited
        raw_output: The analyst's full report text
        source_data: The data the analyst was given
        audit_llm: Which LLM tier label to use (informational; routing handled by FallbackLLMClient)

    Returns:
        AuditResult with audit_id, findings, confidence, etc.
    """
    client = FallbackLLMClient()

    prompt = f"""Source data provided to analyst:
{source_data}

---

Analyst's report:
{raw_output}

---

Audit this report using the instructions above."""

    audit_text = client.complete(prompt, system=AUDIT_SYSTEM_PROMPT)
    tier = client.get_active_tier()
    audit_data = _parse_audit(audit_text, output_id, tier)

    audit_id = AuditResult.make_id(output_id, tier, datetime.now(timezone.utc))
    result = AuditResult(
        audit_id=audit_id,
        output_id=output_id,
        audit_llm=tier,
        audit_prompt=prompt,
        claims_confirmed=audit_data.get("claims_confirmed", 0),
        claims_flagged=audit_data.get("claims_flagged", 0),
        claims_dropped=audit_data.get("claims_dropped", 0),
        audit_output=json.dumps(audit_data),
        confidence=audit_data.get("confidence", 0.0),
    )
    return result


# Tier label FallbackLLMClient reports when neither Claude nor Ollama answered.
_RULES_TIER = "mock"

_AUDIT_KEYS = ("claims_confirmed", "claims_flagged", "claims_dropped", "confidence", "findings")


def _null_audit(reason: str) -> dict:
    """An audit record that says plainly no audit happened, at zero confidence."""
    return {
        "claims_confirmed": 0,
        "claims_flagged": 0,
        "claims_dropped": 0,
        "confidence": 0.0,
        "findings": [{
            "claim": "(entire report)",
            "problem": reason,
            "severity": "HIGH",
            "suggested_edit": "Retry audit",
        }],
    }


def _parse_audit(audit_text: str, output_id: str, tier: str) -> dict:
    """Parse model output into the audit shape, or return a zero-confidence null audit.

    The rule-based tier returns verifier-schema JSON, which carries its own
    ``confidence``. Accepting it would record a rule score as an audit result,
    so a rules-tier response, unparseable text, or JSON without the audit keys
    all become an explicit "no audit" record instead.
    """
    if tier == _RULES_TIER:
        logger.error("No model tier answered the audit for output %s", output_id)
        return _null_audit("No model audit ran: only the rule-based fallback tier was available.")
    try:
        data = json.loads(audit_text)
    except json.JSONDecodeError:
        logger.error("Could not parse audit JSON for output %s", output_id)
        return _null_audit(f"Audit response from tier '{tier}' was not valid JSON.")
    if not isinstance(data, dict) or not all(k in data for k in _AUDIT_KEYS):
        logger.error("Audit JSON for output %s is missing required keys", output_id)
        return _null_audit(f"Audit response from tier '{tier}' did not match the audit schema.")
    return data
