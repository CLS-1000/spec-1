# @domain:   machine
# @module:   scheduler
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""APScheduler background scheduler for spec1_api."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from spec1_core.core.ids import run_id as new_run_id

logger = logging.getLogger(__name__)

_scheduler = None
KILL_FILE = Path(".cls_kill")


def _run_cycle_job() -> None:
    """Background job — runs one full intelligence cycle (all steps).

    Skipped if the kill-file is present.
    """
    if KILL_FILE.exists():
        logger.warning("Kill file present at %s — skipping scheduled cycle.", KILL_FILE)
        return
    cycle_run_id = new_run_id()
    started = time.perf_counter()
    logger.info("Scheduled cycle started: run_id=%s stage=cycle", cycle_run_id)
    try:
        from spec1_core.app.cycle import run_cycle
        stats = run_cycle(
            store_path=Path(os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")),
            run_id=cycle_run_id,
            environment=os.environ.get("SPEC1_ENVIRONMENT", "production"),
            verbose=False,
        )
        logger.info(
            "Scheduled cycle complete: run_id=%s duration_seconds=%.3f "
            "%d records stored, %d errors",
            cycle_run_id,
            time.perf_counter() - started,
            stats["records_stored"],
            len(stats.get("errors", [])),
        )
    except Exception as exc:
        logger.exception(
            "Scheduled cycle failed: run_id=%s stage=cycle duration_seconds=%.3f: %s",
            cycle_run_id,
            time.perf_counter() - started,
            exc,
        )


def start_scheduler() -> None:
    """Start the APScheduler if not already running."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        hour = int(os.environ.get("SPEC1_CRON_HOUR", "6"))
        minute = int(os.environ.get("SPEC1_CRON_MINUTE", "0"))
        timezone = os.environ.get("SPEC1_TIMEZONE", "America/Los_Angeles")

        _scheduler = BackgroundScheduler(timezone=timezone)
        _scheduler.add_job(
            _run_cycle_job,
            trigger="cron",
            hour=hour,
            minute=minute,
            id="daily_cycle",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Scheduler started: daily cycle at %02d:%02d %s", hour, minute, timezone)
    except ImportError:
        logger.warning("APScheduler not installed — scheduler disabled")
    except Exception as exc:
        logger.error("Scheduler failed to start: %s", exc)


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        started = time.perf_counter()
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            logger.exception(
                "Scheduler shutdown failed: duration_seconds=%.3f",
                time.perf_counter() - started,
            )
        _scheduler = None
        logger.info("Scheduler stopped: duration_seconds=%.3f", time.perf_counter() - started)


def get_scheduler():
    return _scheduler


def maybe_run_on_start() -> None:
    """Fire one immediate cycle in a daemon thread when SPEC1_RUN_ON_START=true.

    Skipped if the kill-file is present.
    """
    if os.environ.get("SPEC1_RUN_ON_START", "").lower() != "true":
        return
    if KILL_FILE.exists():
        logger.warning("Kill file present — skipping startup cycle.")
        return
    logger.info("SPEC1_RUN_ON_START=true — triggering immediate cycle.")
    t = threading.Thread(target=_run_cycle_job, daemon=True, name="spec1-startup-cycle")
    t.start()
