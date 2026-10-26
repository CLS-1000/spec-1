# @domain:   publisher
# @module:   routers_narrative_desk
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_api/narrative_store, spec1_core/briefing

"""Narrative Desk router — draft, review and release the daily brief.

GET   /narrative/status                  engine, today's canonical brief + receipt, job state
POST  /narrative/generate                start a draft job {desk, voice, date?} on the local model
GET   /narrative/jobs/{job_id}           job state
GET   /narrative/drafts                  draft index
GET   /narrative/drafts/{draft_id}       draft markdown, sidecar, Hed/Dek/Lead, edits, readiness
PATCH /narrative/drafts/{draft_id}       save Hed/Dek/Lead edits (the draft itself is never edited)
GET   /narrative/drafts/{draft_id}/evidence   the run's records behind the draft
GET   /narrative/drafts/{draft_id}/export     release file list + Notitia Civica print preview
POST  /narrative/publish                 release a draft as the canonical daily brief

Generation writes only under briefs/drafts/. Release is the only writer of
briefs/spec1_brief_<date>.md, runs the shared publish guard plus a confidence
floor, and refuses a date that already has a receipt unless ``force`` (which
archives the old release first). Nothing is pushed off the machine; the
Notitia Civica workflow still publishes, behind its own guard.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from spec1_api import narrative_store as ns
from spec1_core.core.logging_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/narrative", tags=["narrative"])

Desk = Literal["standard", "legislative"]
Voice = Literal["standard", "world_state", "notitia_civica"]

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ── schemas ───────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    desk: Desk = "standard"
    voice: Voice = "standard"
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class EditsRequest(BaseModel):
    hed: Optional[str] = Field(None, max_length=300)
    dek: Optional[str] = Field(None, max_length=500)
    lead: Optional[str] = Field(None, max_length=4000)


class PublishRequest(BaseModel):
    draft_id: str = Field(..., max_length=200)
    analyst_signature: str = Field(..., min_length=1, max_length=120)
    export_targets: list[Literal["canonical", "notitia_civica"]] = ["canonical", "notitia_civica"]
    force: bool = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _draft_or_404(draft_id: str):
    path = ns.resolve_draft(draft_id)
    if path is None:
        raise HTTPException(status_code=404, detail="no such draft")
    return path


def _running_job() -> Optional[dict]:
    with _jobs_lock:
        return next((j for j in _jobs.values() if j["status"] in ("pending", "running")), None)


def _job_view(job: dict) -> dict:
    end = job.get("finished") or time.monotonic()
    return {
        "job_id": job["job_id"], "status": job["status"], "desk": job["desk"],
        "voice": job["voice"], "date": job["date"], "run_id": job["run_id"],
        "created_at": job["created_at"],
        "elapsed_seconds": round(end - job["started"], 1) if job.get("started") else 0.0,
        "draft_id": job.get("draft_id"), "draft_path": job.get("draft_path"),
        "error": job.get("error"),
    }


def _engine_model() -> str:
    from spec1_core.llm.fallback_client import CHAT_MODEL
    return os.environ.get("OLLAMA_MODEL") or CHAT_MODEL


def _cycle_stats(run_id: str, records: list[dict]) -> dict:
    from spec1_core.tools.generate_brief import _cycle_stats_for
    stats = _cycle_stats_for(run_id, records)
    s = ns.record_stats(records)
    stats.update(records_tier=s["records_tier"], analysis_tiers=s["tier_counts"])
    return stats


def _generate(job_id: str) -> None:
    """Background worker. Never raises; the job records the outcome."""
    with _jobs_lock:
        job = _jobs[job_id]
        job.update(status="running", started=time.monotonic())
    try:
        from cls_db.publish_log import append_event
        from spec1_core.briefing import generator
        from spec1_labels import BRIEF_SOURCE_MODEL, BRIEF_SOURCE_RULES

        records = job.pop("_records")
        stats = _cycle_stats(job["run_id"], records)
        markdown, prompts = generator.generate_brief(records, stats, mode=ns.VOICE_MODES[job["voice"]])
        backend = stats.get("brief_backend")
        source = BRIEF_SOURCE_RULES if stats.get("brief_fallback") or not markdown else BRIEF_SOURCE_MODEL
        model = _engine_model() if backend == "local" else generator.MODEL if backend == "claude" else None
        draft_id, path = ns.write_draft(
            date=job["date"], voice=job["voice"], desk=job["desk"], run_id=job["run_id"],
            markdown=markdown, prompts=prompts, stats=ns.record_stats(records),
            brief_source=source, brief_backend=backend, model=model)
        append_event("draft_generated", run_id=job["run_id"], draft_id=draft_id,
                     voice=job["voice"], desk=job["desk"], model=model, brief_source=source)
        with _jobs_lock:
            job.update(status="completed", draft_id=draft_id, draft_path=str(path),
                       finished=time.monotonic())
    except Exception as exc:  # the worker must not die silently
        with _jobs_lock:
            job.update(status="failed", error=f"{type(exc).__name__}: {exc}", finished=time.monotonic())


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/status")
def narrative_status() -> dict:
    from spec1_core.llm import ollama_manager
    url = os.environ.get("SPEC1_OLLAMA_URL", ollama_manager.DEFAULT_URL)
    try:
        reachable = bool(ollama_manager.is_running(url))
    except Exception:
        reachable = False
    today = _today()
    entry = ns.canonical_index().get(today) or {}
    running = _running_job()
    return {
        "date": today,
        "engine_model": _engine_model(),
        "engine_reachable": reachable,
        "canonical_brief": entry["brief"].name if "brief" in entry else None,
        "receipt": ns.receipt_for(today),
        "job_running": _job_view(running) if running else None,
        "drafts": len(ns.draft_index()),
        "min_confidence": ns.MIN_CONFIDENCE,
    }


@router.post("/generate", status_code=202)
def narrative_generate(req: GenerateRequest, background: BackgroundTasks) -> dict:
    date = req.date or _today()
    if _running_job():
        raise HTTPException(status_code=409, detail="a draft job is already running")
    run_id, records = ns.latest_run_on(req.desk, date)
    if not run_id:
        raise HTTPException(status_code=404, detail=f"no {req.desk} records written on {date}")
    job_id = uuid.uuid4().hex
    job = {"job_id": job_id, "status": "pending", "desk": req.desk, "voice": req.voice,
           "date": date, "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
           "_records": records}
    with _jobs_lock:
        _jobs[job_id] = job
    background.add_task(_generate, job_id)
    return {"job_id": job_id, "status": "pending", "voice": req.voice, "desk": req.desk,
            "date": date, "run_id": run_id, "created_at": job["created_at"]}


@router.get("/jobs/{job_id}")
def narrative_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return _job_view(job)


@router.get("/drafts")
def narrative_drafts() -> dict:
    receipts = {d: ns.receipt_for(d) for d in ns.canonical_index()}
    items = []
    for draft_id, path in ns.draft_index().items():
        meta = ns.draft_meta(path) or {}
        released = any((r or {}).get("draft_id") == draft_id for r in receipts.values())
        items.append({
            "draft_id": draft_id, "date": meta.get("date"), "voice": meta.get("voice"),
            "desk": meta.get("desk"), "run_id": meta.get("run_id"),
            "generated_at": meta.get("generated_at"), "analysis_tier": meta.get("analysis_tier"),
            "avg_confidence": meta.get("avg_confidence"), "model": meta.get("model"),
            "publishable": ns.readiness(path)["publishable"], "released": released,
        })
    items.sort(key=lambda d: d.get("generated_at") or "", reverse=True)
    return {"total": len(items), "drafts": items}


@router.get("/drafts/{draft_id}")
def narrative_draft(draft_id: str) -> dict:
    from spec1_api.routers.legislative_desk import _strip_pdf_instructions
    path = _draft_or_404(draft_id)
    markdown = _strip_pdf_instructions(path.read_text(encoding="utf-8"))
    edits = ns.draft_edits(path)
    meta = ns.draft_meta(path)
    date = (meta or {}).get("date") or ""
    return {
        "draft_id": draft_id,
        "markdown": markdown,
        "edited_markdown": ns.apply_edits(markdown, edits),
        "meta": meta,
        "frontmatter": ns.frontmatter(markdown),
        "edits": edits,
        "readiness": ns.readiness(path),
        "existing_receipt": ns.receipt_for(date) if ns.DATE_RE.match(date) else None,
    }


@router.patch("/drafts/{draft_id}")
def narrative_edit(draft_id: str, req: EditsRequest) -> dict:
    path = _draft_or_404(draft_id)
    return {"draft_id": draft_id, "edits": ns.save_edits(path, req.model_dump())}


@router.get("/drafts/{draft_id}/evidence")
def narrative_evidence(draft_id: str) -> dict:
    path = _draft_or_404(draft_id)
    meta = ns.draft_meta(path) or {}
    desk, run_id = meta.get("desk") or "standard", meta.get("run_id") or ""
    records = ns.run_records(desk, run_id)
    if desk == "legislative":
        from spec1_api.routers.legislative_desk import _row
        rows = [_row(r) for r in records]
    else:
        rows = [{
            "record_id": r.get("record_id", ""), "source": r.get("signal_source", ""),
            "classification": r.get("outcome_classification") or r.get("classification", ""),
            "confidence": r.get("outcome_confidence", r.get("confidence")),
            "analysis_tier": r.get("analysis_tier") or "unverified",
            "priority": r.get("opportunity_priority", ""), "url": r.get("signal_url", ""),
            "excerpt": (r.get("signal_excerpt") or "")[:280],
            "reasoning": r.get("llm_reasoning", ""),
        } for r in records]
    return {"draft_id": draft_id, "desk": desk, "run_id": run_id, "total": len(rows), "records": rows}


@router.get("/drafts/{draft_id}/export")
def narrative_export(draft_id: str) -> dict:
    path = _draft_or_404(draft_id)
    meta = ns.draft_meta(path) or {}
    date = meta.get("date") or ""
    if not ns.DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="draft has no valid date")
    markdown = ns.apply_edits(path.read_text(encoding="utf-8"), ns.draft_edits(path))
    try:
        preview = ns.print_preview(markdown, date)
    except Exception:
        logger.exception("Notitia Civica preview failed for %s", draft_id)
        preview, error = None, "preview rendering failed (details in the server log)"
    else:
        error = None if preview is not None else "Notitia Civica template not found"
    return {
        "draft_id": draft_id,
        "date": date,
        "files": ns.release_files(date),
        "workflow_copies": [f"spec1_brief_{date}.md", f"spec1_brief_{date}.meta.json",
                            "spec1_brief_latest.md",
                            f"published/civic-intelligence-brief_{date}.html"],
        "existing_receipt": ns.receipt_for(date),
        "preview_available": preview is not None,
        "preview_html": preview,
        "preview_error": error,
    }


@router.post("/publish")
def narrative_publish(req: PublishRequest) -> dict:
    path = _draft_or_404(req.draft_id)
    signature = req.analyst_signature.strip()
    if not signature:
        raise HTTPException(status_code=422, detail="analyst_signature is required")
    try:
        receipt = ns.release(path, analyst_signature=signature,
                             export_targets=list(dict.fromkeys(req.export_targets)), force=req.force)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=f"publish gate refused: {exc}") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from cls_db.publish_log import append_event
    append_event("brief_released", run_id=receipt["run_id"], draft_id=receipt["draft_id"],
                 date=receipt["date"], analyst=signature, brief_sha256=receipt["brief_sha256"],
                 forced=receipt["supersedes"] is not None)
    return {"status": "released", "receipt": receipt}
