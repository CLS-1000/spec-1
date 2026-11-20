"""Record stamping utility for Tier-3 triage and Migration 011 compliance.

The analysis tier is decided here from the backend that actually answered
(``client.last_tier``), never from anything the model wrote. Every stamp
also carries its provenance: tier_used, model, llm_session, stamped_by.
"""
import logging
from typing import Any, Dict

from spec1_core.llm.fallback_client import LocalTier3Client
from spec1_labels import LLM_TIER_RULES, STAMPED_BY_BACKFILL, analysis_tier_for

logger = logging.getLogger("spec1.triage.stamper")


class TriageStamper:
    def __init__(self, client: LocalTier3Client | None = None):
        self.client = client or LocalTier3Client()

    def evaluate_and_stamp(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Audits record via the local model and stamps analysis_tier plus provenance."""
        try:
            verdict = self.client.verify_triage_record(record)
        except Exception as exc:  # an unexpected client error must not stop a backfill
            logger.error("Triage verification failed for %s: %s", record.get("record_id"), exc)
            verdict = None
        tier_used = getattr(self.client, "last_tier", LLM_TIER_RULES) if verdict else LLM_TIER_RULES

        record["analysis_tier"] = analysis_tier_for(tier_used)
        record["tier_used"] = tier_used
        record["model"] = getattr(self.client, "model", None) if verdict else None
        record["llm_session"] = getattr(self.client, "session_id", None)
        record["stamped_by"] = STAMPED_BY_BACKFILL
        if verdict:
            record["triage_confidence"] = verdict.confidence
            record["triage_justification"] = verdict.justification
            record["triage_flags"] = verdict.flags
            record["triage_classification"] = verdict.classification
        else:
            # Deterministic fallback when daemon is down or validation fails
            record["triage_confidence"] = 0.0
            record["triage_justification"] = ""
            record["triage_flags"] = ["FALLBACK_RULE_BASED"]
            record["triage_classification"] = "UNVERIFIED"

        return record


_stamper: TriageStamper | None = None


def evaluate_and_stamp_record(record: Dict[str, Any]) -> Dict[str, Any]:
    global _stamper
    if _stamper is None:
        _stamper = TriageStamper()
    return _stamper.evaluate_and_stamp(record)
