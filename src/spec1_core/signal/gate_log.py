"""Append-only log of every gate decision — passed and blocked.

One JSON line per scored signal, written once and never rewritten. This is
what lets an operator (or a reader of a published brief) see exactly why an
item was surfaced or discarded: which gates failed, the measured values and
the thresholds they were compared against.

Writes are failure-first: a logging error is reported to the caller and never
stops the cycle.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from spec1_core.schemas.models import Signal

GATE_LOG_ENV = "SPEC1_GATE_LOG_PATH"


def default_gate_log_path(store_path: Path) -> Path:
    """``SPEC1_GATE_LOG_PATH`` if set, else ``<store>_gate_decisions.jsonl``."""
    override = os.environ.get(GATE_LOG_ENV)
    if override:
        return Path(override)
    store_path = Path(store_path)
    return store_path.with_name(f"{store_path.stem}_gate_decisions.jsonl")


def build_decision(
    signal: Signal,
    evaluation: dict,
    run_id: str,
    opportunity_id: Optional[str] = None,
) -> dict:
    """Build one decision record from ``scorer.evaluate_gates`` output."""
    return {
        "run_id": run_id,
        "signal_id": signal.signal_id,
        "source": signal.source,
        "url": getattr(signal, "url", None),
        "decision": "passed" if evaluation["passed"] else "blocked",
        "failed_gates": list(evaluation["failed_gates"]),
        "gates": evaluation["gates"],
        "opportunity_id": opportunity_id,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }


class GateDecisionLog:
    """Append-only JSONL writer for gate decisions."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
