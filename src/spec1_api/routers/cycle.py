# @domain:   machine
# @module:   routers_cycle
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""Cycle router — POST /cycle/run."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi import HTTPException

from spec1_api import metrics as _metrics
from spec1_api import webhooks as _webhooks
from spec1_api.schemas import CycleRequest, CycleResponse
from spec1_core.app.cycle import run_cycle as _execute_cycle

router = APIRouter(prefix="/cycle", tags=["cycle"])
logger = logging.getLogger(__name__)

_last_run: dict = {}


@router.post("/run", response_model=CycleResponse)
def run_cycle(request: CycleRequest, background_tasks: BackgroundTasks) -> CycleResponse:
    """Trigger a full SPEC-1 intelligence cycle (all steps: psyop, brief, publication, workspace)."""
    store_path = Path(os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"))
    try:
        stats = _execute_cycle(
            store_path=store_path,
            environment=request.environment,
            max_signals=request.max_signals,
            verbose=False,
        )
    except Exception as exc:
        logger.exception("Cycle execution failed")
        raise HTTPException(status_code=500, detail=f"Cycle execution failed: {exc}") from exc
    result = CycleResponse(
        run_id=stats["run_id"],
        started_at=stats["started_at"],
        finished_at=stats.get("finished_at"),
        signals_harvested=stats.get("signals_harvested", 0),
        signals_parsed=stats.get("signals_parsed", 0),
        opportunities_found=stats.get("opportunities_found", 0),
        investigations_generated=stats.get("investigations_generated", 0),
        outcomes_verified=stats.get("outcomes_verified", 0),
        records_stored=stats.get("records_stored", 0),
        errors=stats.get("errors", []),
        psyop_classification=stats.get("psyop_classification"),
        psyop_score=stats.get("psyop_score"),
        psyop_patterns_fired=stats.get("psyop_patterns_fired"),
        brief_word_count=stats.get("brief_word_count"),
        brief_path=str(stats["brief_path"]) if stats.get("brief_path") is not None else None,
        publication_path=str(stats["publication_path"]) if stats.get("publication_path") is not None else None,
        cases_updated=stats.get("cases_updated"),
    )
    _last_run.update(result.model_dump())
    _metrics.record_cycle(stats)
    _webhooks.fire_cycle_completed(stats)
    return result


@router.get("/status")
def cycle_status() -> dict:
    """Return the status of the last cycle run."""
    if not _last_run:
        return {"status": "no_run", "message": "No cycle has been run yet"}
    return {"status": "completed", **_last_run}
