from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from cls_congress.models import ConfidenceTier, Signal

GateResult = tuple[bool, Optional[str]]
DEFAULT_MIN_CREDIBILITY_SCORE = 0.5
DEFAULT_MIN_WORDS = 50
DEFAULT_MAX_HOURS = 48

_CREDIBILITY_SCORE = {
    ConfidenceTier.HARD_RECORD: 1.0,
    ConfidenceTier.REPORTED: 0.7,
    ConfidenceTier.INFERRED: 0.3,
}


def credibility_gate(
    confidence: ConfidenceTier,
    min_score: float = DEFAULT_MIN_CREDIBILITY_SCORE,
) -> GateResult:
    score = _CREDIBILITY_SCORE.get(confidence, 0.0)
    if score < min_score:
        return False, f"CRED_001: score {score:.2f} below {min_score:.2f}"
    return True, None


def volume_gate(text: str, min_words: int = DEFAULT_MIN_WORDS) -> GateResult:
    count = len((text or "").split())
    if count < min_words:
        return False, f"VOL_001: {count} words below {min_words}"
    return True, None


def velocity_gate(occurred_at: datetime, max_hours: int = DEFAULT_MAX_HOURS) -> GateResult:
    ts = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - ts
    if age > timedelta(hours=max_hours):
        return False, f"VEL_001: {age.total_seconds() / 3600:.1f}h exceeds {max_hours}h"
    return True, None


def novelty_gate(payload: str, seen_hashes: set[str]) -> GateResult:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest in seen_hashes:
        return False, "NOV_001: duplicate payload"
    return True, None


def run_signal_gates(
    signal: Signal,
    *,
    confidence: ConfidenceTier,
    text: str,
    seen_hashes: set[str],
) -> tuple[bool, list[str]]:
    payload = f"{signal.kind}:{signal.member_id or ''}:{signal.entity_id or ''}:{signal.bill_id or ''}:{signal.occurred_at.isoformat()}"
    results = [
        credibility_gate(confidence),
        volume_gate(text),
        velocity_gate(signal.occurred_at),
        novelty_gate(payload, seen_hashes),
    ]
    failures = [reason for ok, reason in results if not ok and reason]
    if not failures:
        seen_hashes.add(hashlib.sha256(payload.encode("utf-8")).hexdigest())
    return len(failures) == 0, failures
