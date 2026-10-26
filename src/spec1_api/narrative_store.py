# @domain:   publisher
# @module:   narrative_store
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core/briefing, cls_db/publish_log

"""File side of the Narrative Desk: drafts, edits, releases, receipts.

Layout under ``SPEC1_BRIEFS_DIR`` (default ``briefs``)::

    drafts/spec1_brief_<date>_<voice>_<run_id>.md          generated draft (never edited)
    drafts/spec1_brief_<date>_<voice>_<run_id>.meta.json   its provenance sidecar
    drafts/spec1_brief_<date>_<voice>_<run_id>.edits.json  analyst edits (Hed / Dek / Lead)
    spec1_brief_<date>.md (+ .meta.json, latest alias)     canonical brief, written only by release
    spec1_brief_<date>.published.json                      release receipt
    releases/<date>/r<n>/                                  a published release superseded by --force

No request value is ever joined into a path: drafts and canonical briefs are
found by globbing their directory and looked up by key in that index.
Nothing published is deleted; a forced re-release archives the old one first.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404 — fixed argv, no shell
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from spec1_labels import ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED

DAILY_PREFIX = "spec1_brief"
VOICES = ("standard", "world_state", "notitia_civica")
DESKS = ("standard", "legislative")
# voice → generate_brief mode; every mode's prompts live in core/prompts/.
VOICE_MODES = {"standard": "standard", "world_state": "geopolitics", "notitia_civica": "legislative"}
MIN_CONFIDENCE = 0.55

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DRAFT_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_(standard|world_state|notitia_civica)_[A-Za-z0-9_-]{1,80}$")
_DRAFT_STEM_RE = re.compile(
    r"^spec1_brief_(\d{4}-\d{2}-\d{2})_(standard|world_state|notitia_civica)_([A-Za-z0-9_-]{1,80})$")
_RUN_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


# ── paths ─────────────────────────────────────────────────────────────────────

def briefs_dir() -> Path:
    return Path(os.environ.get("SPEC1_BRIEFS_DIR", "briefs"))


def drafts_dir() -> Path:
    return briefs_dir() / "drafts"


def releases_dir() -> Path:
    return briefs_dir() / "releases"


def store_path(desk: str) -> Path:
    if desk == "legislative":
        return Path(os.environ.get("SPEC1_LEGISLATIVE_STORE", "spec1_legislative.jsonl"))
    return Path(os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"))


def _sidecar(md: Path, suffix: str) -> Path:
    return md.with_name(md.stem + suffix)


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── records ───────────────────────────────────────────────────────────────────

def read_store(desk: str) -> list[dict]:
    path = store_path(desk)
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


def latest_run_on(desk: str, date: str) -> tuple[Optional[str], list[dict]]:
    """The run whose records were written last on *date* (UTC), and its records."""
    latest: dict[str, str] = {}
    by_run: dict[str, list[dict]] = {}
    for rec in read_store(desk):
        written = str(rec.get("written_at") or "")
        run_id = rec.get("run_id")
        if not run_id or not written.startswith(date):
            continue
        by_run.setdefault(run_id, []).append(rec)
        latest[run_id] = max(latest.get(run_id, ""), written)
    if not latest:
        return None, []
    run_id = max(latest, key=latest.__getitem__)
    return run_id, by_run[run_id]


def run_records(desk: str, run_id: str) -> list[dict]:
    return [r for r in read_store(desk) if r.get("run_id") == run_id]


def record_stats(records: list[dict]) -> dict:
    """Tier counts, records tier and average confidence, as the cycle computes them."""
    tiers = Counter(r.get("analysis_tier") or ANALYSIS_TIER_RULE_BASED for r in records)
    confs = [float(r["outcome_confidence"]) for r in records
             if isinstance(r.get("outcome_confidence"), (int, float))]
    return {
        "tier_counts": {ANALYSIS_TIER_LLM_VERIFIED: tiers.get(ANALYSIS_TIER_LLM_VERIFIED, 0),
                        ANALYSIS_TIER_RULE_BASED: sum(v for k, v in tiers.items()
                                                      if k != ANALYSIS_TIER_LLM_VERIFIED)},
        "records_tier": (ANALYSIS_TIER_LLM_VERIFIED
                         if records and set(tiers) == {ANALYSIS_TIER_LLM_VERIFIED}
                         else ANALYSIS_TIER_RULE_BASED),
        "avg_confidence": round(sum(confs) / len(confs), 3) if confs else None,
        "records": len(records),
    }


# ── drafts ────────────────────────────────────────────────────────────────────

def draft_index() -> dict[str, Path]:
    """draft_id → draft .md path, from the files that exist."""
    index: dict[str, Path] = {}
    d = drafts_dir()
    if not d.is_dir():
        return index
    for p in d.glob(f"{DAILY_PREFIX}_*.md"):
        m = _DRAFT_STEM_RE.match(p.stem)
        if m and p.is_file():
            index[f"{m.group(1)}_{m.group(2)}_{m.group(3)}"] = p
    return index


def resolve_draft(draft_id: str) -> Optional[Path]:
    """The draft for *draft_id*, or None. Never builds a path from the id."""
    if not DRAFT_ID_RE.match(draft_id or ""):
        return None
    return draft_index().get(draft_id)


def write_draft(*, date: str, voice: str, desk: str, run_id: str, markdown: str,
                prompts: str, stats: dict, brief_source: str, brief_backend: Optional[str],
                model: Optional[str]) -> tuple[str, Path]:
    """Write a draft and its sidecar under drafts/. Returns (draft_id, path)."""
    from spec1_core.briefing.writer import brief_analysis_tier

    safe_run = _RUN_ID_SAFE.sub("-", run_id)[:80] or "run"
    draft_id = f"{date}_{voice}_{safe_run}"
    d = drafts_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{DAILY_PREFIX}_{draft_id}.md"
    path.write_text(markdown, encoding="utf-8")
    if prompts:
        _sidecar(path, ".prompts.md").write_text(prompts, encoding="utf-8")
    meta = {
        "draft_id": draft_id,
        "run_id": run_id,
        "date": date,
        "voice": voice,
        "desk": desk,
        "mode": VOICE_MODES[voice],
        "brief": path.name,
        "records_tier": stats["records_tier"],
        "brief_source": brief_source,
        "brief_backend": brief_backend,
        "model": model,
        "record_tiers": stats["tier_counts"],
        "avg_confidence": stats["avg_confidence"],
        "records": stats["records"],
        "analysis_tier": brief_analysis_tier(stats["records_tier"], brief_source),
        "generated_at": _now(),
    }
    _sidecar(path, ".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return draft_id, path


def draft_meta(path: Path) -> Optional[dict]:
    return _read_json(_sidecar(path, ".meta.json"))


def draft_edits(path: Path) -> dict:
    return _read_json(_sidecar(path, ".edits.json")) or {}


def save_edits(path: Path, edits: dict) -> dict:
    current = draft_edits(path)
    current.update({k: v for k, v in edits.items() if v is not None})
    current["edited_at"] = _now()
    _sidecar(path, ".edits.json").write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


# ── Hed / Dek / Lead ──────────────────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_DEK = re.compile(r"^(\*\*|\*|_)(.+?)\1\s*$")


def frontmatter(markdown: str) -> dict:
    """Hed = first heading, Dek = first emphasised line, Lead = first paragraph after the Hed."""
    hed = dek = lead = ""
    lines = markdown.splitlines()
    i = 0
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m:
            hed = m.group(2)
            break
    para: list[str] = []
    for line in lines[i + 1:] if hed else lines:
        s = line.strip()
        if not s:
            if para:
                break
            continue
        if _HEADING.match(s) or s.startswith(("---", "- ", "* ", "|")):
            if para:
                break
            continue
        if not dek and not para and _DEK.match(s):
            dek = _DEK.match(s).group(2)
            continue
        para.append(s)
    lead = " ".join(para)
    return {"hed": hed, "dek": dek, "lead": lead}


def apply_edits(markdown: str, edits: dict) -> str:
    """Replace the Hed / Dek / Lead the analyst edited; leave everything else alone."""
    fm = frontmatter(markdown)
    lines = markdown.splitlines()
    hed_at = next((i for i, line in enumerate(lines) if _HEADING.match(line)), None)
    out = markdown
    for key in ("hed", "dek", "lead"):
        new = (edits.get(key) or "").strip()
        old = fm[key]
        if not new or new == old:
            continue
        if old:
            out = out.replace(old, new, 1)
            continue
        lines = out.splitlines()
        if key == "hed":
            lines[:0] = [f"## {new}", ""]
            hed_at = 0
        else:
            at = (hed_at + 1) if hed_at is not None else 0
            lines[at:at] = ["", f"*{new}*" if key == "dek" else new, ""]
        out = "\n".join(lines) + "\n"
    return out


# A line that is only a bracketed instruction, e.g. "[3-5 bullets. Each bullet: ...]":
# the prompt template's guidance copied into the brief by a small model.
_TEMPLATE_LEAK = re.compile(r"^\s*\[[^\]\n]{20,}\]?\s*$")


def template_leaks(markdown: str) -> list[str]:
    """Lines of *markdown* that are prompt-template instructions, not brief text."""
    return [line.strip() for line in markdown.splitlines() if _TEMPLATE_LEAK.match(line)]


def readiness(draft_path: Optional[Path]) -> dict:
    """Whether a draft may be released, and why not.

    The tier check is the shared publish guard (writer.publish_block_reason, the
    same one notitia_civica_publish.yml runs); the narrative desk adds a confidence floor.
    """
    from spec1_core.briefing.writer import publish_block_reason

    meta = draft_meta(draft_path) if draft_path is not None else None
    reasons: list[str] = []
    if draft_path is None or meta is None:
        reasons.append("no provenance sidecar")
    else:
        why = publish_block_reason(draft_path)
        if why:
            reasons.append(why)
        conf = meta.get("avg_confidence")
        if not isinstance(conf, (int, float)) or conf < MIN_CONFIDENCE:
            reasons.append(f"average confidence {conf if conf is not None else 'unknown'} "
                           f"is below {MIN_CONFIDENCE}")
        leaked = template_leaks(draft_path.read_text(encoding="utf-8"))
        if leaked:
            reasons.append(f"{len(leaked)} unfilled template instruction line(s), e.g. {leaked[0][:80]!r}; "
                           "edit or regenerate the draft")
    tiers = (meta or {}).get("record_tiers") or {}
    return {
        "publishable": not reasons,
        "reasons": reasons,
        "llm_verified": tiers.get(ANALYSIS_TIER_LLM_VERIFIED, 0),
        "rule_based": tiers.get(ANALYSIS_TIER_RULE_BASED, 0),
        "avg_confidence": (meta or {}).get("avg_confidence"),
        "min_confidence": MIN_CONFIDENCE,
    }


# ── canonical briefs & releases ───────────────────────────────────────────────

def canonical_index() -> dict[str, dict[str, Path]]:
    """date → {"brief", "meta", "receipt"} for the canonical daily files that exist."""
    out: dict[str, dict[str, Path]] = {}
    d = briefs_dir()
    if not d.is_dir():
        return out
    for p in d.glob(f"{DAILY_PREFIX}_*"):
        if not p.is_file():
            continue
        m = re.match(r"^spec1_brief_(\d{4}-\d{2}-\d{2})(\.md|\.meta\.json|\.published\.json)$", p.name)
        if m:
            kind = {".md": "brief", ".meta.json": "meta", ".published.json": "receipt"}[m.group(2)]
            out.setdefault(m.group(1), {})[kind] = p
    return out


def receipt_for(date: str) -> Optional[dict]:
    entry = canonical_index().get(date) or {}
    return _read_json(entry["receipt"]) if "receipt" in entry else None


def release_files(date: str) -> list[str]:
    """What a release writes, and what notitia_civica_publish.yml then copies."""
    return [f"{DAILY_PREFIX}_{date}.md", f"{DAILY_PREFIX}_{date}.meta.json",
            f"{DAILY_PREFIX}_latest.md", f"{DAILY_PREFIX}_latest.meta.json",
            f"{DAILY_PREFIX}_{date}.published.json"]


def _git_commit() -> str:
    try:
        out = subprocess.run(  # nosec B603 B607 — fixed argv, no shell
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parents[2])
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _archive(date: str, entry: dict[str, Path]) -> str:
    """Copy the published release for *date* into releases/<date>/r<n>/ before it is replaced."""
    base = releases_dir() / date
    base.mkdir(parents=True, exist_ok=True)
    n = 1 + sum(1 for p in base.glob("r*") if p.is_dir() and p.name[1:].isdigit())
    target = base / f"r{n}"
    target.mkdir()
    for p in entry.values():
        shutil.copy2(p, target / p.name)
    return str(target)


def release(draft_path: Path, *, analyst_signature: str, export_targets: list[str],
            force: bool = False) -> dict:
    """Promote a draft to the canonical daily brief and write its receipt.

    Raises PermissionError (gate refused), FileExistsError (already released),
    ValueError (bad draft). Callers map these to HTTP errors.
    """
    meta = draft_meta(draft_path)
    if meta is None:
        raise ValueError("draft has no provenance sidecar")
    gate = readiness(draft_path)
    if not gate["publishable"]:
        raise PermissionError("; ".join(gate["reasons"]))
    date = meta.get("date") or ""
    if not DATE_RE.match(date):
        raise ValueError("draft has no valid date")

    existing = canonical_index().get(date) or {}
    supersedes = None
    archived_to = None
    if "receipt" in existing:
        if not force:
            raise FileExistsError(f"{date} already has a published release; pass force to supersede it")
        supersedes = _read_json(existing["receipt"])
        archived_to = _archive(date, existing)

    edits = draft_edits(draft_path)
    markdown = apply_edits(draft_path.read_text(encoding="utf-8"), edits)
    d = briefs_dir()
    brief = d / f"{DAILY_PREFIX}_{date}.md"
    brief_meta = _sidecar(brief, ".meta.json")
    released_meta = {**meta, "brief": brief.name, "released_from_draft": meta.get("draft_id"),
                     "edits": {k: edits[k] for k in ("hed", "dek", "lead") if edits.get(k)}}
    meta_text = json.dumps(released_meta, indent=2) + "\n"
    brief.write_text(markdown, encoding="utf-8")
    brief_meta.write_text(meta_text, encoding="utf-8")
    (d / f"{DAILY_PREFIX}_latest.md").write_text(markdown, encoding="utf-8")
    (d / f"{DAILY_PREFIX}_latest.meta.json").write_text(meta_text, encoding="utf-8")

    receipt = {
        "date": date,
        "released_at": _now(),
        "analyst_signature": analyst_signature,
        "draft_id": meta.get("draft_id"),
        "run_id": meta.get("run_id"),
        "voice": meta.get("voice"),
        "desk": meta.get("desk"),
        "model": meta.get("model"),
        "analysis_tier": meta.get("analysis_tier"),
        "avg_confidence": meta.get("avg_confidence"),
        "export_targets": export_targets,
        "brief_sha256": _sha256(brief),
        "meta_sha256": _sha256(brief_meta),
        "git_commit": _git_commit(),
        "supersedes": ({"released_at": supersedes.get("released_at"),
                        "draft_id": supersedes.get("draft_id"),
                        "brief_sha256": supersedes.get("brief_sha256"),
                        "archived_to": archived_to} if supersedes is not None else None),
    }
    _sidecar(brief, ".published.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                                  encoding="utf-8")
    return receipt


# ── export preview ────────────────────────────────────────────────────────────

_INJECT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "inject_brief_to_template.py"
_STRIP_TAGS = re.compile(r"<(link|script)\b[^>]*>(?:.*?</script>)?", re.I | re.S)


def template_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "notitia-civica" / "templates" / "print" \
        / "civic-intelligence-brief.html"
    return Path(os.environ.get("SPEC1_NOTITIA_TEMPLATE", str(default)))


def print_preview(markdown: str, date: str) -> Optional[str]:
    """The brief rendered into the Notitia Civica print layout, offline; None without a template."""
    tpl = template_path()
    if not tpl.is_file() or not _INJECT_SCRIPT.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("spec1_inject_brief", _INJECT_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    html = mod.inject_brief_into_template(markdown, tpl.read_text(encoding="utf-8"),
                                          datetime.strptime(date, "%Y-%m-%d").date())
    return _STRIP_TAGS.sub("", html)
