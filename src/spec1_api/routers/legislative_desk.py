# @domain:   machine
# @module:   routers_legislative_desk
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core/app/legislative_desk, cls_leg_jud/bridge

"""Legislative desk router — read-only data for the Legislative & Judicial Desk view.

GET /desk/legislative/status    desk configuration and local-engine reachability
GET /desk/legislative/records   records from spec1_legislative.jsonl, newest first, filterable
GET /desk/legislative/brief     latest (or dated) spec1_legislative_<date>.md + its .meta.json

Reads files only; never runs the desk or a model. Paths:
``SPEC1_LEGISLATIVE_STORE`` (default ``spec1_legislative.jsonl``) and
``SPEC1_BRIEFS_DIR`` (default ``briefs``).
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/desk/legislative", tags=["legislative_desk"])

BRIEF_PREFIX = "spec1_legislative"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MEASURE_RE = re.compile(r"^([A-Z]+)\s*(\d+)$")
_KINDS = ("measure", "interim_committee", "bill")


def _store_path() -> Path:
    return Path(os.environ.get("SPEC1_LEGISLATIVE_STORE", "spec1_legislative.jsonl"))


def _briefs_dir() -> Path:
    return Path(os.environ.get("SPEC1_BRIEFS_DIR", "briefs"))


def _read_records() -> list[dict]:
    """Every parseable row of the legislative store, in file (append) order."""
    path = _store_path()
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _kind(domain: str) -> str:
    """'state_leg.or.measure' → 'measure'; 'state_leg.ca.bill' → 'bill'."""
    tail = domain.rsplit(".", 1)[-1] if domain else ""
    return tail if tail in _KINDS else "other"


def _chamber(meta: dict, prefix: str) -> str:
    if meta.get("chamber"):
        return str(meta["chamber"])
    if prefix.startswith("H"):
        return "House"
    if prefix.startswith("S"):
        return "Senate"
    return ""


def _row(rec: dict) -> dict:
    """The fields the desk view shows, flattened from a stored record."""
    meta = rec.get("metadata") or {}
    domain = rec.get("domain") or ""
    kind = _kind(domain)
    bill = str(meta.get("bill") or "")
    prefix, number = "", ""
    if kind != "interim_committee":
        m = _MEASURE_RE.match(bill.replace(" ", " ").strip())
        if m:
            prefix, number = m.group(1), m.group(2)
    return {
        "record_id": rec.get("record_id", ""),
        "run_id": rec.get("run_id", ""),
        "kind": kind,
        "domain": domain,
        "state": meta.get("state", ""),
        "measure": bill,
        "measure_prefix": prefix,
        "measure_number": number,
        "title": rec.get("title") or meta.get("title") or "",
        "status": meta.get("status", ""),
        "chamber": _chamber(meta, prefix) if kind != "interim_committee" else "",
        "committee_code": meta.get("committee_code", ""),
        "committee": meta.get("sponsor", "") if kind == "interim_committee" else "",
        "last_action": rec.get("published_at", ""),
        "priority": rec.get("opportunity_priority", ""),
        "classification": rec.get("outcome_classification") or rec.get("classification", ""),
        "confidence": rec.get("outcome_confidence", rec.get("confidence")),
        "analysis_tier": rec.get("analysis_tier") or "unverified",
        "reasoning": rec.get("llm_reasoning", ""),
        "summary": rec.get("summary", ""),
        "url": meta.get("source_url") or rec.get("signal_url", ""),
        "source": rec.get("signal_source", ""),
    }


@router.get("/status")
def desk_status() -> dict:
    """Desk configuration as the next run would use it, and whether Ollama answers."""
    from cls_leg_jud.bridge import DEFAULT_LIMIT, DEFAULT_LOOKAHEAD_DAYS, DEFAULT_SINCE_DAYS
    from spec1_core.llm import ollama_manager
    from spec1_core.llm.fallback_client import CHAT_MODEL

    url = os.environ.get("SPEC1_OLLAMA_URL", ollama_manager.DEFAULT_URL)
    try:
        reachable = bool(ollama_manager.is_running(url))
    except Exception:
        reachable = False
    store = _store_path()
    return {
        "lookback_days": DEFAULT_SINCE_DAYS,
        "lookahead_days": DEFAULT_LOOKAHEAD_DAYS,
        "max_per_run": DEFAULT_LIMIT,
        "engine_model": os.environ.get("OLLAMA_MODEL") or CHAT_MODEL,
        "engine_url": url,
        "engine_reachable": reachable,
        "store_path": str(store),
        "store_exists": store.is_file(),
    }


@router.get("/records")
def desk_records(
    kind: Optional[Literal["measure", "interim_committee", "bill"]] = Query(
        None, description="measure = Oregon measures; interim_committee = OLIS interim meetings; "
                          "bill = other states"),
    tier: Optional[Literal["llm_verified", "rule_based", "unverified"]] = Query(None),
    run_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Case-insensitive search over measure, title, committee"),
    limit: int = Query(200, ge=1, le=2000),
) -> dict:
    """Stored legislative records, newest first, with counts over the unfiltered store."""
    rows = [_row(r) for r in reversed(_read_records())]
    counts = {
        "total": len(rows),
        "by_kind": dict(Counter(r["kind"] for r in rows)),
        "by_tier": dict(Counter(r["analysis_tier"] for r in rows)),
        "runs": len({r["run_id"] for r in rows}),
    }
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if tier:
        rows = [r for r in rows if r["analysis_tier"] == tier]
    if run_id:
        rows = [r for r in rows if r["run_id"] == run_id]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in " ".join(
            (r["measure"], r["title"], r["committee"], r["committee_code"])).lower()]
    matched = len(rows)
    return {"store_path": str(_store_path()), "counts": counts, "matched": matched,
            "records": rows[:limit]}


def _strip_pdf_instructions(markdown: str) -> str:
    """Drop the '### PDF Conversion' footer the writer appends to every brief."""
    from spec1_core.briefing.writer import PDF_INSTRUCTIONS_HEADING
    idx = markdown.find(PDF_INSTRUCTIONS_HEADING)
    if idx < 0:
        return markdown
    body = markdown[:idx].rstrip()
    if body.endswith("---"):
        body = body[:-3].rstrip()
    return body + "\n"


@router.get("/brief")
def desk_brief(
    date: Optional[str] = Query(None, description="YYYY-MM-DD; default: the latest brief"),
) -> dict:
    """The legislative brief's markdown, its provenance sidecar, and its run's record stats."""
    if date is not None and not _DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    # Pick from the files that exist rather than building a path from the request,
    # so no user-supplied value ever reaches the filesystem.
    briefs = {p.stem[len(BRIEF_PREFIX) + 1:]: p
              for p in _briefs_dir().glob(f"{BRIEF_PREFIX}_*.md") if p.is_file()}
    path = briefs.get(date if date else "latest")
    if path is None:
        raise HTTPException(status_code=404, detail="no legislative brief for that date")

    markdown = path.read_text(encoding="utf-8")
    meta_path = path.with_name(path.stem + ".meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = None

    run_stats = None
    run_id = (meta or {}).get("run_id")
    if run_id:
        recs = [r for r in _read_records() if r.get("run_id") == run_id]
        confs = [float(r["outcome_confidence"]) for r in recs
                 if isinstance(r.get("outcome_confidence"), (int, float))]
        run_stats = {
            "records": len(recs),
            "avg_confidence": round(sum(confs) / len(confs), 3) if confs else None,
            "by_kind": dict(Counter(_kind(r.get("domain") or "") for r in recs)),
            "by_classification": dict(Counter(
                r.get("outcome_classification") or "—" for r in recs)),
        }

    dates = sorted((d for d in briefs if _DATE_RE.match(d)), reverse=True)
    return {
        "path": str(path),
        "markdown": _strip_pdf_instructions(markdown),
        "meta": meta,
        "run_stats": run_stats,
        "available_dates": dates,
    }
