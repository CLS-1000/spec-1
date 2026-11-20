# @domain:   machine
# @module:   publish_log
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Idempotency log for published X (Twitter) threads.

Append-only JSONL; keyed by run_id. Safe for concurrent reads from multiple
processes; single-writer per process enforced by the caller (XPublisher).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home
from typing import Any


def _log_path() -> Path:
    return anchor_to_home(os.getenv("SPEC1_PUBLISH_LOG", "publish_log.jsonl"))


def append_event(event: str, **kwargs: Any) -> None:
    """Append a structured event record to the publish log."""
    path = _log_path()
    record = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **kwargs}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def has_x_publish(run_id: str) -> bool:
    """Return True if run_id already has an x_publish event in the log."""
    path = _log_path()
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "x_publish" and rec.get("run_id") == run_id:
                return True
    return False


def load_x_publish(run_id: str) -> Any:
    """Return a PublishResult for a previously published run_id.

    Raises KeyError if no matching event is found.
    """
    from spec1_core.app.publishers.x import PublishResult  # lazy — avoids circular import

    path = _log_path()
    if not path.exists():
        raise KeyError(f"No publish log; run_id={run_id} not found")
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "x_publish" and rec.get("run_id") == run_id:
                return PublishResult(
                    run_id=run_id,
                    thread_root_id=rec["thread_root_id"],
                    posted_count=rec["posted_count"],
                    skipped_sections=tuple(rec.get("skipped_sections", [])),
                    cycle_utc=datetime.fromisoformat(rec["cycle_utc"]),
                )
    raise KeyError(f"run_id={run_id} not found in publish log")
