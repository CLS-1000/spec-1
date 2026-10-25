"""Record stamping utility for Tier-3 triage and Migration 011 compliance."""
import logging
from typing import Any, Dict

from spec1_core.llm.fallback_client import LocalTier3Client

logger = logging.getLogger("spec1.triage.stamper")


class TriageStamper:
    def __init__(self, client: LocalTier3Client | None = None):
        self.client = client or LocalTier3Client()

    def evaluate_and_stamp(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Audits record via local Qwen 2.5 and stamps analysis_tier for Migration 011."""
        verdict = self.client.verify_triage_record(record)
        if verdict:
            record["analysis_tier"] = verdict.analysis_tier
            record["triage_confidence"] = verdict.confidence
            record["triage_justification"] = verdict.justification
            record["triage_flags"] = verdict.flags
            record["triage_classification"] = verdict.classification
        else:
            # Deterministic fallback when daemon is down or validation fails
            record["analysis_tier"] = "rule_based"
            record["triage_confidence"] = 0.0
            record["triage_justification"] = "Local Tier-3 daemon unreachable; defaulted to rule_based"
            record["triage_flags"] = ["FALLBACK_RULE_BASED"]
            record["triage_classification"] = "UNVERIFIED"

        return record


# Global default instance
stamper = TriageStamper()


def evaluate_and_stamp_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return stamper.evaluate_and_stamp(record)
