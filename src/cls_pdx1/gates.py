# @domain:   citizens_source
# @module:   gates
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Structural gates for cls_pdx1.

Every record must pass applicable gates before entering the graph or publication.
Gates return (ok: bool, reason: str | None). Reason is None on success.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cls_pdx1.models import Affiliation, Anomaly, AnomalyTier, ConfidenceTier, Signal


GateResult = tuple[bool, Optional[str]]

# Minimum sources required per confidence tier.
DEFAULT_CORROBORATION_POLICY: dict[int, int] = {
    int(ConfidenceTier.HARD_RECORD): 1,
    int(ConfidenceTier.REPORTED): 2,
    int(ConfidenceTier.INFERRED): 10,   # effectively unpublishable without extraordinary sourcing
}

# Signals older than this are considered stale.
_FRESHNESS_WINDOW_DAYS = 180


def provenance_gate(record: Any) -> GateResult:
    """Reject any record that lacks a resolvable HTTP/HTTPS source URI."""
    if record is None:
        return False, "PROV_001: record is None"

    if hasattr(record, "provenance"):
        prov = record.provenance
        uri = getattr(prov, "source_uri", None) if not isinstance(prov, dict) else prov.get("source_uri", "")
    elif isinstance(record, dict):
        prov = record.get("provenance")
        if not prov:
            return False, "PROV_002: missing provenance field"
        uri = prov.get("source_uri", "") if isinstance(prov, dict) else getattr(prov, "source_uri", "")
    else:
        return False, "PROV_003: unrecognised record type"

    if not uri:
        return False, "PROV_004: source_uri is empty"

    if not (uri.startswith("http://") or uri.startswith("https://")):
        return False, f"PROV_005: source_uri must be HTTP/HTTPS, got: {uri[:40]}"

    return True, None


def append_only_gate(seen_ids: set[str], record_id: str) -> GateResult:
    """Reject writes whose ID already exists in the seen set."""
    if record_id in seen_ids:
        return False, f"APPEND_001: duplicate id {record_id!r}"
    return True, None


def time_bounding_gate(affiliation: Affiliation) -> GateResult:
    """Require valid_from; reject reversed date ranges."""
    if affiliation.valid_to is None:
        return True, None
    if affiliation.valid_from > affiliation.valid_to:
        return False, (
            f"TIME_002: valid_from {affiliation.valid_from} is after "
            f"valid_to {affiliation.valid_to}"
        )
    return True, None


def tier_corroboration_gate(
    tier: ConfidenceTier,
    sources: list[str],
    policy: Optional[dict[int, int]] = None,
) -> GateResult:
    """Require at least N unique source URIs for the given confidence tier."""
    effective_policy = policy if policy is not None else DEFAULT_CORROBORATION_POLICY
    required = effective_policy.get(int(tier), 99)
    unique = len(set(sources))
    if unique < required:
        return False, (
            f"CORR_001: {tier.name} requires {required} unique sources, "
            f"got {unique}"
        )
    return True, None


def anomaly_publication_gate(anomaly: Anomaly) -> GateResult:
    """Only TIER_1 and TIER_2 anomalies are eligible for publication."""
    if anomaly.tier in (AnomalyTier.TIER_1, AnomalyTier.TIER_2):
        return True, None
    return False, (
        f"ANOM_001: {anomaly.tier.name} anomalies are below publication threshold"
    )


def signal_freshness_gate(signal: Signal, window_days: int = _FRESHNESS_WINDOW_DAYS) -> GateResult:
    """Reject signals whose occurred_at is older than the freshness window."""
    now = datetime.now(timezone.utc)
    occurred = signal.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    age = now - occurred
    if age > timedelta(days=window_days):
        return False, (
            f"FRESH_001: signal is {age.days} days old, "
            f"exceeds window of {window_days} days"
        )
    return True, None


def run_gates(*results: GateResult) -> tuple[bool, list[str]]:
    """Aggregate multiple gate results. Returns (all_ok, [failure_reasons])."""
    failures = [reason for ok, reason in results if not ok and reason is not None]
    all_ok = len(failures) == 0
    return all_ok, failures
