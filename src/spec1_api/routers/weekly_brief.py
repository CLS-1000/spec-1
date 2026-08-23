# @domain:   machine
# @module:   routers_weekly_brief
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db, cls_weekly_brief

"""Public weekly brief router — GET/POST /api/v1/weekly-brief."""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException

from spec1_api.dependencies import IntelStoreDep
from cls_weekly_brief import (
    produce_weekly_brief,
    to_json_summary,
    to_full_json,
    WeeklyBriefStore,
)

router = APIRouter(prefix="/weekly-brief", tags=["weekly-brief"])

_WEEKLY_BRIEFS_PATH = Path("spec1_weekly_briefs.jsonl")


def _get_store() -> WeeklyBriefStore:
    """Get or create weekly brief store."""
    return WeeklyBriefStore(_WEEKLY_BRIEFS_PATH)


@router.get("/latest")
def get_latest_weekly_brief() -> dict:
    """Return the most recently produced weekly intelligence brief."""
    store = _get_store()
    brief = store.latest()
    if brief is None:
        raise HTTPException(status_code=404, detail="No weekly brief available yet")
    return to_json_summary(brief) if brief else {"message": "No brief available"}


@router.get("/history")
def list_weekly_briefs(
    limit: int = Query(10, ge=1, le=52),
) -> dict:
    """Return weekly brief history (up to 52 weeks)."""
    store = _get_store()
    all_briefs = list(store.read_all())
    items = [to_json_summary(b) if isinstance(b, dict) else b for b in all_briefs[-limit:]]
    return {"total": len(all_briefs), "items": items}


@router.get("/index")
def get_weekly_brief_index() -> dict:
    """Return all weekly briefs sorted newest first with summary metadata."""
    store = _get_store()
    all_briefs = list(store.read_all())
    items = []
    for brief in reversed(all_briefs):
        items.append({
            "brief_id": brief.get("brief_id"),
            "week_id": brief.get("week_id"),
            "week_start": brief.get("week_start"),
            "week_end": brief.get("week_end"),
            "records_analyzed": brief.get("records_analyzed"),
            "verified_count": brief.get("verified_count"),
            "inferred_count": brief.get("inferred_count"),
            "speculation_count": brief.get("speculation_count"),
            "produced_at": brief.get("produced_at"),
        })
    return {"total": len(items), "items": items}


@router.get("/{week_id}")
def get_weekly_brief_by_week(week_id: str) -> dict:
    """Return the weekly brief for a specific ISO week (YYYY-W##).

    Returns full brief with all evidence items.
    """
    store = _get_store()
    brief = store.get_by_week_id(week_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"No brief found for week {week_id}")
    return to_full_json(brief) if isinstance(brief, dict) else brief.to_dict()


@router.get("/{week_id}/summary")
def get_weekly_brief_summary(week_id: str) -> dict:
    """Return a summary of the weekly brief for a specific week."""
    store = _get_store()
    brief = store.get_by_week_id(week_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"No brief found for week {week_id}")
    return to_json_summary(brief) if isinstance(brief, dict) else brief


@router.post("/generate")
def generate_weekly_brief(
    intel_store: IntelStoreDep,
    week_id: Optional[str] = Query(None, description="ISO week YYYY-W##; defaults to current"),
) -> dict:
    """Generate a new weekly intelligence brief from current intelligence records.

    Aggregates the past 7 days of records and classifies evidence into tiers.
    Persists to JSONL store and returns summary.
    """
    records = list(intel_store.read_all())
    brief = produce_weekly_brief(records, week_id=week_id)

    store = _get_store()
    entry = store.save(brief, write_markdown=True)

    return {
        "status": "success",
        "brief_id": brief.brief_id,
        "week_id": brief.week_id,
        "records_analyzed": brief.records_analyzed,
        "verified_count": brief.verified_count,
        "inferred_count": brief.inferred_count,
        "speculation_count": brief.speculation_count,
        "produced_at": brief.produced_at.isoformat()
        if hasattr(brief.produced_at, "isoformat")
        else str(brief.produced_at),
        "markdown_path": f"briefs/markdown/weekly_{brief.week_id}.md",
    }
