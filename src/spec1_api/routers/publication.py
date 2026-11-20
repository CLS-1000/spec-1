# @domain:   machine
# @module:   routers_publication
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""Publication router — GET /publication/latest, GET /publication/list, POST /publication/generate."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from spec1_core.intelligence.store import anchor_to_home

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from spec1_api.dependencies import IntelStoreDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/publication", tags=["publication"])

_BRIEFS_DIR = Path("generated/briefs")


def _safe_pdf_path(p: Path) -> Path:
    """Resolve path and ensure it stays within _BRIEFS_DIR (no symlink escape)."""
    resolved = p.resolve()
    base = anchor_to_home(_BRIEFS_DIR)
    if p.is_symlink() or not resolved.is_relative_to(base):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


def _real_pdfs() -> list[tuple[Path, os.stat_result]]:
    """Return (path, stat) pairs for non-symlink PDFs; files deleted mid-scan are skipped."""
    if not anchor_to_home(_BRIEFS_DIR).exists():
        return []
    result = []
    for p in anchor_to_home(_BRIEFS_DIR).glob("spec1_issue_*.pdf"):
        if p.is_symlink():
            continue
        try:
            result.append((p, p.stat()))
        except OSError:
            pass
    return result


@router.get("/latest")
def get_latest_publication() -> FileResponse:
    """Return the most recently generated publication PDF."""
    pdfs = _real_pdfs()
    if not pdfs:
        raise HTTPException(status_code=404, detail="No publication PDFs found")
    latest, _ = max(pdfs, key=lambda t: (t[1].st_mtime, t[0].name))
    safe = _safe_pdf_path(latest)
    return FileResponse(
        path=str(safe),
        media_type="application/pdf",
        filename=latest.name,
    )


@router.get("/list")
def list_publications() -> dict:
    """Return metadata for all generated publication PDFs, newest first."""
    pdfs = sorted(_real_pdfs(), key=lambda t: (t[1].st_mtime, t[0].name), reverse=True)
    items = [{"filename": p.name, "size_bytes": st.st_size} for p, st in pdfs]
    return {"total": len(items), "items": items}


@router.post("/generate")
def generate_publication_endpoint(intel_store: IntelStoreDep) -> dict:
    """Generate a new publication PDF from the latest brief and current intelligence records."""
    from spec1_core.tools.publication_generator import generate_publication as _gen

    briefs_dir = anchor_to_home(os.environ.get("SPEC1_BRIEFS_DIR", "briefs"))
    brief_path = briefs_dir / "spec1_brief_latest.md"
    brief_text = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""

    try:
        all_records = list(intel_store.read_all())
    except Exception:
        logger.exception("Failed to load intel records for publication")
        all_records = []

    records = sorted(
        all_records,
        key=lambda r: float(r.get("confidence", 0)),
        reverse=True,
    )[:20]

    cycle_stats = {"records_stored": len(records)}

    try:
        pdf_path = _gen(records, brief_text, cycle_stats)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "filename": Path(pdf_path).name,
        "url": "/publication/latest",
        "message": "Publication generated successfully",
    }


@router.get("/{filename}")
def get_publication_by_name(filename: str) -> FileResponse:
    """Serve a specific publication PDF by filename."""
    # Resolve path only from the pre-scanned trusted list — never build a path from user input.
    for p, _ in _real_pdfs():
        if p.name == filename:
            return FileResponse(str(p), media_type="application/pdf", filename=p.name)
    raise HTTPException(status_code=404, detail="Not found")
