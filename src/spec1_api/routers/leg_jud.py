# @domain:   machine
# @module:   routers_leg_jud
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""Legislative & Judicial Desk router — /leg_jud."""

from __future__ import annotations

import os
from typing import Optional

from spec1_core.intelligence.store import anchor_to_home

from fastapi import APIRouter, Query

from spec1_api.dependencies import OsintStoreDep

router = APIRouter(prefix="/leg_jud", tags=["legislative_judicial"])


@router.get("/brief")
def get_leg_jud_brief() -> dict:
    """Return the latest Legislative & Judicial Desk brief."""
    store_path = anchor_to_home(os.environ.get("SPEC1_LEG_JUD_PATH", "leg_jud_briefs.jsonl"))
    if not store_path.is_file():
        return {"brief": None, "message": "No brief generated yet"}
    from cls_leg_jud.store import LegJudStore
    store = LegJudStore(store_path)
    latest = store.latest()
    return {"brief": latest}


@router.get("/brief/history")
def list_leg_jud_briefs(limit: int = Query(10, ge=1, le=100)) -> dict:
    """Return recent Legislative & Judicial Desk briefs."""
    store_path = anchor_to_home(os.environ.get("SPEC1_LEG_JUD_PATH", "leg_jud_briefs.jsonl"))
    if not store_path.is_file():
        return {"total": 0, "items": []}
    from cls_leg_jud.store import LegJudStore
    store = LegJudStore(store_path)
    items = list(store.read_all())
    items = items[-limit:]
    items.reverse()
    return {"total": len(items), "items": items}


@router.get("/judicial")
def list_judicial_records(
    osint_store: OsintStoreDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    judge: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    court: Optional[str] = Query(None),
) -> dict:
    """Return judicial records from the OSINT store."""
    records = list(osint_store.filter_by("source_type", "JUDICIAL"))
    if judge:
        q = judge.lower()
        records = [r for r in records if q in r.get("metadata", {}).get("judge", "").lower()]
    if action:
        q = action.lower()
        records = [r for r in records if q in r.get("metadata", {}).get("action_type", "").lower()]
    if court:
        q = court.lower()
        records = [r for r in records if q in r.get("metadata", {}).get("court", "").lower()]
    total = len(records)
    page = records[offset: offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "items": page}


@router.get("/state_leg")
def list_state_leg_records(
    osint_store: OsintStoreDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: Optional[str] = Query(None),
    chamber: Optional[str] = Query(None),
    disclosure_gap: Optional[bool] = Query(None),
) -> dict:
    """Return state legislative records from the OSINT store."""
    records = list(osint_store.filter_by("source_type", "STATE_LEG"))
    if state:
        q = state.upper()
        records = [r for r in records if r.get("metadata", {}).get("state", "").upper() == q]
    if chamber:
        q = chamber.upper()
        records = [r for r in records if r.get("metadata", {}).get("chamber", "").upper() == q]
    if disclosure_gap is not None:
        records = [r for r in records if r.get("metadata", {}).get("disclosure_gap") == disclosure_gap]
    total = len(records)
    page = records[offset: offset + limit]
    return {"total": total, "limit": limit, "offset": offset, "items": page}
