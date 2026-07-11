from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Query

from cls_congress.models import MemberRegistry
from cls_congress.pipeline import CycleResult, Pipeline
from cls_congress.sources import CongressGovAdapter, FecAdapter, LdaAdapter, SenateSeiAdapter
from cls_congress.watch import TopLobbyingFirmsWatch, TopPacsWatch

router = APIRouter(prefix="/congress_brief", tags=["congress_brief"])

_registry = MemberRegistry()
_registry.load()

_pipeline = Pipeline(
    adapters=[
        CongressGovAdapter(),
        FecAdapter(member_registry=_registry),
        LdaAdapter(member_registry=_registry),
        SenateSeiAdapter(member_registry=_registry),
    ],
    watch_modules=[TopPacsWatch(), TopLobbyingFirmsWatch()],
)

_state_lock = threading.Lock()
_last_result = CycleResult()
_last_issue = None


@router.post("/cycle")
def run_cycle() -> dict:
    global _last_result, _last_issue
    with _state_lock:
        _last_result = _pipeline.run_cycle()
        if _last_result.issue is not None:
            _last_issue = _last_result.issue
    return {
        "signals": len(_last_result.signals),
        "affiliations": len(_last_result.affiliations),
        "anomalies": len(_last_result.anomalies),
        "published": _last_result.issue is not None,
    }


@router.get("/brief")
def get_latest_brief() -> dict:
    with _state_lock:
        if _last_issue is None:
            raise HTTPException(status_code=404, detail="No congress brief published yet")
        return _last_issue.model_dump()


@router.get("/member/{member_id}")
def get_member(member_id: str) -> dict:
    member = _registry.get(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    with _state_lock:
        member_signals = [s for s in _last_result.signals if s.member_id == member_id]
        member_affiliations = [a for a in _last_result.affiliations if a.member_id == member_id]
    return {
        "member": member.model_dump(),
        "signals": [s.model_dump() for s in member_signals],
        "affiliations": [a.model_dump() for a in member_affiliations],
    }


@router.get("/entity/{entity_id}")
def get_entity(entity_id: str) -> dict:
    with _state_lock:
        entity_signals = [s for s in _last_result.signals if s.entity_id == entity_id]
        entity_affiliations = [a for a in _last_result.affiliations if a.entity_id == entity_id]
    if not entity_signals and not entity_affiliations:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "entity_id": entity_id,
        "signals": [s.model_dump() for s in entity_signals],
        "affiliations": [a.model_dump() for a in entity_affiliations],
    }


@router.get("/anomalies")
def get_anomalies(tier: int | None = Query(default=None, ge=1, le=4)) -> dict:
    with _state_lock:
        anomalies = _last_result.anomalies
        if tier is not None:
            anomalies = [a for a in anomalies if int(a.tier) == tier]
    return {"count": len(anomalies), "items": [a.model_dump() for a in anomalies]}
