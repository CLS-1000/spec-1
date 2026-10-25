# @domain:   machine
# @module:   routers_runs
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core

"""Runs router — read-only run history for the Triage Desk.

GET /runs                     recent runs (newest first)
GET /runs/{run_id}            run metadata, adapter stats, stage funnel, guard
GET /runs/{run_id}/records    that run's stored records, filterable
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from spec1_api import runs_index

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def list_runs(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Recent runs from cycle logs, structured run logs and the intel store."""
    runs = runs_index.list_runs(limit=limit)
    return {"total": len(runs), "runs": runs}


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    """One run's metadata, per-adapter stats, stage funnel and publish guard."""
    run = runs_index.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return run


@router.get("/{run_id}/records")
def get_run_records(
    run_id: str,
    tier: Optional[Literal["llm_verified", "rule_based", "unverified"]] = Query(
        None, description="analysis_tier filter; 'unverified' = no tier (pre-011)"),
    source: Optional[str] = Query(None, description="Source feed / adapter name"),
    gate_status: Optional[Literal["pass", "fail", "unknown"]] = Query(None),
    min_weight: Optional[float] = Query(None, ge=0.0, description="Minimum composite score"),
    tier1_only: bool = Query(False, description="Only TIER_1 anomaly records"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    """Stored records for one run, joined with their gate decisions."""
    records = runs_index.get_records(
        run_id, tier=tier, source=source, gate_status=gate_status,
        min_weight=min_weight, tier1_only=tier1_only, limit=limit,
    )
    if records is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return {"run_id": run_id, "total": len(records), "records": records}
