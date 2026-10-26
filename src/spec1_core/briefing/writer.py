# @domain:   publisher
# @module:   briefing_writer
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core/schemas

"""Brief writer — persists generated briefs to disk."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from spec1_labels import (
    ANALYSIS_TIER_LLM_VERIFIED,
    ANALYSIS_TIER_RULE_BASED,
    BRIEF_RULE_FALLBACK_NOTE,
    BRIEF_SOURCE_HAND_WRITTEN,
    BRIEF_SOURCE_MODEL,
)

logger = logging.getLogger(__name__)

BRIEFS_DIR = Path("briefs")
_lock = threading.Lock()

PDF_INSTRUCTIONS_HEADING = "### PDF Conversion"

# Content floor for a brief, in words, counted by brief_content_words() (the
# PDF-conversion footer and symbol-only tokens such as ``━━━`` rules are not
# counted). A model reply below this is treated as a failed generation, and the
# publish guard refuses a brief below it whatever its sidecar says.
# run-fe8f2b8df1af (2026-10-26): qwen2.5:3b returned 62 ``━`` characters and it
# was stamped llm_verified and passed --check. The value is a human call.
BRIEF_MIN_WORDS = 150

_WORD_RE = re.compile(r"\w")

_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_ /\-]*\}")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _strip_unresolved_placeholders(brief: str) -> str:
    """Remove template placeholders (e.g. ``{tone/language}``) left in a brief.

    A "Communication" section containing placeholders is dropped entirely;
    any other leftover placeholder is replaced with an em dash.
    """
    lines = brief.splitlines()
    out: list[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence or lines[i].lstrip().startswith("```"):
            out.append(lines[i])
            i += 1
            continue
        m = _HEADING_RE.match(lines[i].strip())
        if m and m.group(2).strip().strip("*").lower().startswith("communication"):
            level = len(m.group(1))
            j = i + 1
            while j < len(lines):
                n = _HEADING_RE.match(lines[j].strip())
                if n and len(n.group(1)) <= level:
                    break
                j += 1
            if any(_PLACEHOLDER_RE.search(ln) for ln in lines[i:j]):
                i = j
                continue
        out.append(_PLACEHOLDER_RE.sub("—", lines[i]))
        i += 1
    result = "\n".join(out)
    return result + "\n" if brief.endswith("\n") else result


def brief_content_words(text: str) -> int:
    """Words of actual content in *text*.

    Drops everything from the PDF-conversion footer on, and counts only tokens
    with at least one letter or digit, so rules, bullets and box-drawing
    characters do not count.
    """
    body = text.split(PDF_INSTRUCTIONS_HEADING, 1)[0]
    return sum(1 for tok in body.split() if _WORD_RE.search(tok))


def _pdf_instructions(md_name: str) -> str:
    """Footer explaining how to convert the brief to PDF."""
    stem = md_name[:-3] if md_name.endswith(".md") else md_name
    return (
        f"\n\n---\n\n{PDF_INSTRUCTIONS_HEADING}\n\n"
        "This brief is Markdown. To produce a PDF:\n\n"
        "1. Pandoc (recommended):\n\n"
        "   ```\n"
        f"   pandoc briefs/{md_name} -o briefs/{stem}.pdf --pdf-engine=xelatex\n"
        "   ```\n\n"
        "2. HTML export, then PDF (weasyprint or wkhtmltopdf):\n\n"
        "   ```\n"
        f"   pandoc briefs/{md_name} -s -o briefs/{stem}.html\n"
        f"   weasyprint briefs/{stem}.html briefs/{stem}.pdf\n"
        f"   wkhtmltopdf briefs/{stem}.html briefs/{stem}.pdf\n"
        "   ```\n\n"
        "3. SPEC-1 built-in renderer:\n\n"
        "   ```\n"
        f"   python -m spec1_core.tools.pdf_render --brief-md briefs/{md_name} --out briefs/{stem}.pdf\n"
        "   ```\n"
    )


def _extract_prompts(brief: str) -> list[str]:
    """Extract CLAUDE PROMPT blockquote blocks from a generated brief.

    Returns a list of blockquote strings, one per lead.
    """
    prompts = []
    lines = brief.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith(">") and "**CLAUDE PROMPT:**" in stripped:
            block_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block_lines.append(lines[i])
                i += 1
            prompts.append("\n".join(block_lines))
        else:
            i += 1
    return prompts


def _build_prompts_doc(prompts: list[str], date_str: str, timestamp: str) -> str:
    """Build the prompts-only markdown document."""
    lines = [
        f"# SPEC-1 Investigation Prompts — {date_str}",
        f"Generated: {timestamp}",
        "",
    ]
    if not prompts:
        lines.append("_(No Claude investigation prompts in this brief.)_")
        lines.append("")
    else:
        for i, prompt_block in enumerate(prompts, start=1):
            lines.append(f"## Prompt {i}")
            lines.append("")
            lines.append(prompt_block)
            lines.append("")
    return "\n".join(lines)


def _build_prompt_payload_doc(prompts: str, date_str: str, timestamp: str) -> str:
    """Build a prompts document from a raw system/user prompt payload string."""
    lines = [
        f"# SPEC-1 Investigation Prompts — {date_str}",
        f"Generated: {timestamp}",
        "",
        "## Prompt Payload",
        "",
        prompts.strip(),
        "",
    ]
    return "\n".join(lines)


def write_brief(
    brief: str,
    run_id: str,
    timestamp: str,
    prompts: str | None = None,
    prefix: str = "spec1_brief",
) -> str:
    """Write brief to disk and return the filepath string.

    Creates (with the default *prefix*):
      briefs/spec1_brief_{YYYY-MM-DD}.md    — dated full brief
      briefs/spec1_brief_latest.md          — always overwritten
      briefs/spec1_prompts_{YYYY-MM-DD}.md  — investigation prompts only
      briefs/spec1_prompts_latest.md        — always overwritten
      briefs/brief_index.jsonl              — append-only index

    Another *prefix* (e.g. ``spec1_legislative``) gives a desk its own files —
    ``{prefix}_{date}.md``, ``{prefix}_latest.md``, ``{prefix}_prompts_*``,
    ``{prefix}_index.jsonl`` — so it never overwrites or joins the daily brief.
    """
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse date from timestamp; fall back to today
    try:
        dt = datetime.fromisoformat(timestamp)
    except Exception:
        dt = datetime.now(timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")

    prompts_prefix = "spec1_prompts" if prefix == "spec1_brief" else f"{prefix}_prompts"
    dated_path = BRIEFS_DIR / f"{prefix}_{date_str}.md"
    latest_path = BRIEFS_DIR / f"{prefix}_latest.md"
    prompts_dated_path = BRIEFS_DIR / f"{prompts_prefix}_{date_str}.md"
    prompts_latest_path = BRIEFS_DIR / f"{prompts_prefix}_latest.md"
    # The daily index is copied to the public site by notitia_civica_publish.yml;
    # other desks keep their own so they can't be listed as a daily brief.
    index_path = BRIEFS_DIR / ("brief_index.jsonl" if prefix == "spec1_brief" else f"{prefix}_index.jsonl")

    brief = _strip_unresolved_placeholders(brief)

    # Extract and format investigation prompts from brief; fall back to raw payload
    extracted_prompts = _extract_prompts(brief)
    if extracted_prompts:
        prompts_doc = _build_prompts_doc(extracted_prompts, date_str, timestamp)
        prompt_count = len(extracted_prompts)
    elif prompts and prompts.strip():
        prompts_doc = _build_prompt_payload_doc(prompts, date_str, timestamp)
        prompt_count = 1
    else:
        prompts_doc = _build_prompts_doc([], date_str, timestamp)
        prompt_count = 0

    word_count = len(brief.split())
    if PDF_INSTRUCTIONS_HEADING not in brief:
        brief = brief.rstrip("\n") + _pdf_instructions(dated_path.name)

    with _lock:
        dated_path.write_text(brief, encoding="utf-8")
        latest_path.write_text(brief, encoding="utf-8")
        prompts_dated_path.write_text(prompts_doc, encoding="utf-8")
        prompts_latest_path.write_text(prompts_doc, encoding="utf-8")

        index_entry = {
            "run_id": run_id,
            "date": date_str,
            "filepath": str(dated_path),
            "word_count": word_count,
            "timestamp": timestamp,
        }
        with index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(index_entry) + "\n")

    logger.info("Brief written to %s (%d words, %d prompts)", dated_path, word_count, prompt_count)
    return str(dated_path)


def write_brief_pdf(brief_md_path: Path, out_pdf_path: Path) -> Path:
    """Render a markdown brief to PDF via the out-of-process renderer.

    Subprocesses to `python -m spec1_core.tools.pdf_render` so weasyprint and
    its native deps stay out of the engine/API process. Raises RuntimeError on
    any subprocess failure (missing input, render error, missing weasyprint).
    """
    brief_md_path = Path(brief_md_path)
    out_pdf_path = Path(out_pdf_path)
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "spec1_core.tools.pdf_render",
            "--brief-md",
            str(brief_md_path),
            "--out",
            str(out_pdf_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PDF render failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    return out_pdf_path


def write_handoff(doc: str, timestamp: str) -> str:
    """Write briefs/spec1_handoff_{date}.md (+ _latest) and return the dated path."""
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        dt = datetime.fromisoformat(timestamp)
    except Exception:
        dt = datetime.now(timezone.utc)
    dated = BRIEFS_DIR / f"spec1_handoff_{dt.strftime('%Y-%m-%d')}.md"
    with _lock:
        dated.write_text(doc, encoding="utf-8")
        (BRIEFS_DIR / "spec1_handoff_latest.md").write_text(doc, encoding="utf-8")
    return str(dated)


# ── Brief provenance (publish guard) ─────────────────────────────────────────
#
# Every brief the cycle writes gets a sidecar ``<brief>.meta.json`` saying how
# it was made. A brief is publishable only when its ``analysis_tier`` is
# ``llm_verified``: every record behind it was classified by a real model AND
# the text came from a model or was written by hand from those records. The
# Notitia publisher refuses anything else, including a brief with no sidecar.


def meta_path_for(brief_path: str | Path) -> Path:
    """``briefs/spec1_brief_2026-10-24.md`` → ``briefs/spec1_brief_2026-10-24.meta.json``."""
    p = Path(brief_path)
    return p.with_name(p.stem + ".meta.json")


def brief_analysis_tier(records_tier: str, brief_source: str) -> str:
    """The brief's tier: verified only if its records and its text both are."""
    if records_tier == ANALYSIS_TIER_LLM_VERIFIED and brief_source in (
        BRIEF_SOURCE_MODEL, BRIEF_SOURCE_HAND_WRITTEN,
    ):
        return ANALYSIS_TIER_LLM_VERIFIED
    return ANALYSIS_TIER_RULE_BASED


def write_brief_meta(
    brief_path: str | Path,
    *,
    run_id: str,
    records_tier: str,
    brief_source: str,
    record_tiers: dict | None = None,
    latest_name: str = "spec1_brief_latest.md",
) -> Path:
    """Write the provenance sidecar for *brief_path* and for *latest_name*."""
    brief_path = Path(brief_path)
    meta = {
        "run_id": run_id,
        "brief": brief_path.name,
        "records_tier": records_tier,
        "brief_source": brief_source,
        "record_tiers": record_tiers or {},
        "analysis_tier": brief_analysis_tier(records_tier, brief_source),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    text = json.dumps(meta, indent=2) + "\n"
    out = meta_path_for(brief_path)
    with _lock:
        out.write_text(text, encoding="utf-8")
        meta_path_for(brief_path.with_name(latest_name)).write_text(text, encoding="utf-8")
    return out


def read_brief_meta(brief_path: str | Path) -> dict | None:
    """Return the sidecar for *brief_path*, or None if missing/unreadable."""
    try:
        return json.loads(meta_path_for(brief_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def mark_hand_written(brief_path: str | Path) -> dict:
    """Record that *brief_path* now holds a hand-written brief (e.g. Claude in chat).

    Keeps the cycle's ``records_tier``: a hand-written brief over rule-based
    records is still rule-based and still refused by the publisher.
    """
    meta = read_brief_meta(brief_path)
    if meta is None:
        raise FileNotFoundError(f"no provenance sidecar for {brief_path}: {meta_path_for(brief_path)}")
    meta["brief_source"] = BRIEF_SOURCE_HAND_WRITTEN
    meta["analysis_tier"] = brief_analysis_tier(meta.get("records_tier", ""), BRIEF_SOURCE_HAND_WRITTEN)
    meta["marked_hand_written_at"] = datetime.now(timezone.utc).isoformat()
    meta_path_for(brief_path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


# A home directory or Windows user folder in brief text means machine output
# (stack traces, harvest errors) leaked into the brief.
LOCAL_PATH_RE = re.compile(r"(?<![\w.~/-])/(?:home|Users)/[^/\s]+/|(?<!\w)[A-Za-z]:\\Users\\", re.IGNORECASE)


def evidence_block_reason(meta: dict, text: str) -> str | None:
    """Why a brief labelled llm_verified still may not publish, judged on evidence.

    The label alone is not enough: the sidecar's record counts must show
    model-verified records and nothing rule-based, and the text must not be the
    rule fallback, carry local file paths, or fall below BRIEF_MIN_WORDS.
    """
    tiers = meta.get("record_tiers") or {}
    counts = {}
    for key, value in tiers.items():
        try:
            counts[key] = int(value or 0)
        except (TypeError, ValueError):
            counts[key] = 0
    verified = counts.get(ANALYSIS_TIER_LLM_VERIFIED, 0)
    other = sum(v for k, v in counts.items() if k != ANALYSIS_TIER_LLM_VERIFIED)
    if verified < 1:
        return (f"sidecar says {ANALYSIS_TIER_LLM_VERIFIED} but record_tiers shows no "
                f"{ANALYSIS_TIER_LLM_VERIFIED} records ({tiers or 'empty'}); the label is not evidence")
    if other:
        return f"record_tiers includes {other} record(s) that are not {ANALYSIS_TIER_LLM_VERIFIED} ({tiers})"
    if BRIEF_RULE_FALLBACK_NOTE in text:
        return ("brief text is the rule-based fallback; write the brief from the handoff "
                "before marking it hand-written")
    hit = LOCAL_PATH_RE.search(text)
    if hit:
        return f"brief contains a local file path ({hit.group(0)}...); remove machine output before publishing"
    words = brief_content_words(text)
    if words < BRIEF_MIN_WORDS:
        return (f"brief has {words} words of content (minimum {BRIEF_MIN_WORDS}, excluding the "
                "PDF-conversion footer); a degenerate model reply is not a brief")
    return None


def publish_block_reason(brief_path: str | Path) -> str | None:
    """None if *brief_path* may be published; otherwise why it may not."""
    meta = read_brief_meta(brief_path)
    if meta is None:
        return f"no provenance sidecar ({meta_path_for(brief_path).name}); refusing to publish an unlabelled brief"
    tier = meta.get("analysis_tier")
    if tier != ANALYSIS_TIER_LLM_VERIFIED:
        return (f"brief is {tier or 'unlabelled'} (records_tier={meta.get('records_tier')}, "
                f"brief_source={meta.get('brief_source')}); only {ANALYSIS_TIER_LLM_VERIFIED} briefs publish")
    try:
        text = Path(brief_path).read_text(encoding="utf-8")
    except OSError as exc:
        return f"brief unreadable: {exc}"
    return evidence_block_reason(meta, text)


if __name__ == "__main__":
    import argparse

    _p = argparse.ArgumentParser(description="Brief provenance tools")
    _p.add_argument("--mark-hand-written", metavar="BRIEF_MD",
                    help="Record that this brief was written by hand from the cycle handoff")
    _p.add_argument("--check", metavar="BRIEF_MD", help="Exit 1 unless this brief may be published")
    _a = _p.parse_args()
    if _a.mark_hand_written:
        print(json.dumps(mark_hand_written(_a.mark_hand_written), indent=2))
    if _a.check:
        _why = publish_block_reason(_a.check)
        print(f"REFUSED: {_why}" if _why else "OK: publishable")
        sys.exit(1 if _why else 0)
