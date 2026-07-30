#!/usr/bin/env python3
# @domain:   spec-1
# @module:   manual_publisher
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""
SPEC-1 Manual Publisher — workbench for generating and rendering intelligence briefs.

Reads an existing brief markdown file or generates one from a JSONL intelligence
store, then renders it to a clean HTML document (and optionally a PDF).

The HTML output references ``assets/brief_style.css`` for print-ready styling.
PDF output is produced via the out-of-process WeasyPrint renderer
(``spec1_engine.tools.pdf_render``) so this script never imports weasyprint directly.

Usage examples
--------------
Render an existing brief to HTML::

    python tools/manual_publisher.py --brief briefs/spec1_brief_latest.md

Generate from the intel store and render both HTML and PDF::

    PYTHONPATH=src python tools/manual_publisher.py \\
        --intel spec1_intelligence.jsonl \\
        --format both \\
        --out-dir generated/briefs

Generate using the rule-based producer (no Anthropic API required)::

    PYTHONPATH=src python tools/manual_publisher.py \\
        --intel spec1_intelligence.jsonl \\
        --rule-based \\
        --format html
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _group_by_run_id(records: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r.get("run_id") or "unknown"].append(r)
    return dict(groups)


def _latest_run(groups: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    def _ts(recs: list[dict]) -> str:
        for r in recs:
            ts = r.get("written_at") or r.get("created_at") or r.get("finished_at") or ""
            if ts:
                return str(ts)
        return ""

    latest_id = max(groups.keys(), key=lambda rid: _ts(groups[rid]))
    return latest_id, groups[latest_id]


def _cycle_stats(run_id: str, records: list[dict]) -> dict:
    timestamp = ""
    for r in records:
        ts = r.get("written_at") or r.get("created_at") or r.get("finished_at") or ""
        if ts:
            timestamp = str(ts)
            break
    return {
        "run_id": run_id,
        "finished_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "signals_harvested": records[0].get("signals_harvested", len(records)) if records else 0,
        "records_stored": len(records),
    }


# ---------------------------------------------------------------------------
# Brief generation
# ---------------------------------------------------------------------------

def _generate_brief(records: list[dict], cycle_stats: dict, rule_based: bool) -> str:
    if not rule_based:
        try:
            from spec1_engine.briefing.generator import generate_brief  # type: ignore
            brief_md, _ = generate_brief(records, cycle_stats)
            if brief_md:
                return brief_md
        except Exception as exc:
            print(f"[manual_publisher] Claude path unavailable: {exc}", file=sys.stderr)

    # Rule-based fallback
    try:
        from cls_world_brief.formatter import to_markdown  # type: ignore
        from cls_world_brief.producer import produce_brief  # type: ignore
        brief = produce_brief(records)
        return to_markdown(brief)
    except Exception as exc:
        raise RuntimeError(f"Rule-based fallback also failed: {exc}") from exc


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WORLD STATE BRIEF</title>
<link rel="stylesheet" href="{css_path}">
</head>
<body>
    <div class="masthead">
        <div class="masthead-title">WORLD STATE BRIEF</div>
        <div class="masthead-subtitle">GEOPOLITICAL INTELLIGENCE &middot; DAILY ANALYSIS</div>
        <div class="masthead-date">{date_line}</div>
    </div>
    <div class="brief-body">
        {body}
    </div>
    <div class="footer">
        <p>WORLD STATE BRIEF &mdash; SPEC-1 INTELLIGENCE ENGINE</p>
        <p>Analysis aggregates open-source intelligence. Not investment or policy advice.</p>
    </div>
</body>
</html>"""


def _extract_date_line(md_text: str) -> str:
    m = re.search(r"(?:#+ .*?)(20\d\d-\d\d-\d\d)", md_text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            return f"{dt.strftime('%A, %B')} {dt.day}, {dt.year}".upper()
        except ValueError:
            return m.group(1)
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%A, %B')} {now.day}, {now.year}".upper()


def _md_to_html_body(md_text: str) -> str:
    try:
        from markdown import markdown  # type: ignore
        return markdown(md_text, extensions=["tables", "fenced_code"])
    except ImportError:
        pass

    # Minimal fallback — escape and wrap paragraphs
    import html as _html
    lines = md_text.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(#{1,6}) (.+)$", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_html.escape(m.group(2))}</h{level}>")
        elif stripped.startswith("---"):
            out.append("<hr>")
        else:
            out.append(f"<p>{_html.escape(stripped)}</p>")
    return "\n".join(out)


def render_html(md_text: str, css_path: str = "../assets/brief_style.css") -> str:
    """Render a brief markdown string to a full HTML document.

    ``css_path`` is the ``href`` written into the ``<link>`` tag — use a
    relative path from the output file's location or an absolute path.
    """
    date_line = _extract_date_line(md_text)
    body = _md_to_html_body(md_text)
    return _HTML_TEMPLATE.format(date_line=date_line, body=body, css_path=css_path)


# ---------------------------------------------------------------------------
# PDF rendering (out-of-process via spec1_engine.tools.pdf_render)
# ---------------------------------------------------------------------------

def render_pdf(md_path: Path, out_path: Path) -> None:
    """Render a brief markdown file to PDF via the out-of-process renderer."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "spec1_engine.tools.pdf_render",
            "--brief-md",
            str(md_path),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PDF render failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manual_publisher",
        description="SPEC-1 manual publishing workbench — generate and render intelligence briefs.",
    )

    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--brief",
        metavar="PATH",
        help="Path to an existing brief markdown file (skips generation).",
    )
    src.add_argument(
        "--intel",
        metavar="PATH",
        default=os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"),
        help=(
            "Path to the intelligence JSONL store used when --brief is not given "
            "(default: %(default)s)."
        ),
    )

    p.add_argument(
        "--run-id",
        default="latest",
        help='run_id to use from the intel store, or "latest" (default).',
    )
    p.add_argument(
        "--rule-based",
        action="store_true",
        help="Skip Claude and use the rule-based world-brief producer.",
    )
    p.add_argument(
        "--format",
        choices=["html", "pdf", "both"],
        default="html",
        help="Output format (default: html).",
    )
    p.add_argument(
        "--out-dir",
        metavar="DIR",
        default=os.environ.get("SPEC1_BRIEFS_DIR", "generated/briefs"),
        help="Directory to write outputs into (default: %(default)s).",
    )
    p.add_argument(
        "--css",
        metavar="PATH",
        default=None,
        help=(
            "href value written into the HTML <link> tag. "
            "Defaults to a relative path from --out-dir to assets/brief_style.css."
        ),
    )
    return p


def _resolve_css_href(out_dir: Path, css_override: str | None) -> str:
    if css_override:
        return css_override
    # Compute a relative path from out_dir to the assets/ directory at repo root.
    repo_root = Path(__file__).resolve().parent.parent
    css_abs = repo_root / "assets" / "brief_style.css"
    try:
        return os.path.relpath(css_abs, out_dir.resolve())
    except ValueError:
        # On Windows, relpath can fail across drives — fall back to absolute.
        return str(css_abs)


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Obtain brief markdown ────────────────────────────────────────────────
    if args.brief:
        md_path = Path(args.brief)
        if not md_path.exists():
            print(f"error: brief file not found: {md_path}", file=sys.stderr)
            return 1
        md_text = md_path.read_text(encoding="utf-8")
        run_id = md_path.stem
        timestamp = datetime.now(timezone.utc).isoformat()
    else:
        intel_path = Path(args.intel)
        records = _read_jsonl(intel_path)
        if not records:
            print(f"error: no records found in {intel_path}", file=sys.stderr)
            return 1

        groups = _group_by_run_id(records)
        if args.run_id == "latest":
            run_id, run_records = _latest_run(groups)
        else:
            if args.run_id not in groups:
                print(f"error: run_id {args.run_id!r} not found in store", file=sys.stderr)
                return 1
            run_id, run_records = args.run_id, groups[args.run_id]

        stats = _cycle_stats(run_id, run_records)
        timestamp = stats["finished_at"]

        print(
            f"[manual_publisher] generating brief: run_id={run_id} "
            f"records={len(run_records)} rule_based={args.rule_based}",
            file=sys.stderr,
        )
        md_text = _generate_brief(run_records, stats, args.rule_based)

        # Persist the generated markdown alongside other outputs
        try:
            dt = datetime.fromisoformat(timestamp)
        except Exception:
            dt = datetime.now(timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        md_path = out_dir / f"spec1_brief_{date_str}.md"
        md_path.write_text(md_text, encoding="utf-8")
        print(f"[manual_publisher] brief written: {md_path}", file=sys.stderr)

    # ── Derive base filename from markdown path ──────────────────────────────
    base_name = md_path.stem  # e.g. "spec1_brief_2026-05-14"
    html_path = out_dir / f"{base_name}.html"
    pdf_path = out_dir / f"{base_name}.pdf"

    css_href = _resolve_css_href(out_dir, args.css)

    # ── HTML ─────────────────────────────────────────────────────────────────
    if args.format in ("html", "both"):
        html_content = render_html(md_text, css_path=css_href)
        html_path.write_text(html_content, encoding="utf-8")
        print(f"[manual_publisher] HTML written: {html_path}", file=sys.stderr)

    # ── PDF ──────────────────────────────────────────────────────────────────
    if args.format in ("pdf", "both"):
        try:
            render_pdf(md_path, pdf_path)
            print(f"[manual_publisher] PDF written: {pdf_path}", file=sys.stderr)
        except RuntimeError as exc:
            print(f"[manual_publisher] PDF render error: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
