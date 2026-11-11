#!/usr/bin/env python3
"""Export verified SPEC-1 records into a World State Brief prompt bundle."""

from __future__ import annotations

import argparse
import datetime
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path("spec1.db")
DEFAULT_OUT_DIR = Path("briefs/prompts")
PUBLISHABLE_TIER = "llm_verified"
DEFAULT_EXCLUDED_SOURCES = ("rand",)


def latest_verified_run(conn: sqlite3.Connection, excluded: tuple[str, ...]) -> str | None:
    placeholders = ",".join("?" * len(excluded)) or "''"
    row = conn.execute(
        f"""
        SELECT run_id
        FROM intelligence_records
        WHERE analysis_tier = ?
          AND signal_source NOT IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (PUBLISHABLE_TIER, *excluded),
    ).fetchone()
    return row["run_id"] if row else None


def verified_records(
    conn: sqlite3.Connection,
    run_id: str,
    min_score: float,
    limit: int,
    excluded: tuple[str, ...],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" * len(excluded)) or "''"
    return conn.execute(
        f"""
        SELECT record_id, signal_source, signal_url, opportunity_score,
               analysis_tier, classification, confidence,
               signal_excerpt, llm_reasoning, created_at
        FROM intelligence_records
        WHERE run_id = ?
          AND analysis_tier = ?
          AND signal_source NOT IN ({placeholders})
          AND opportunity_score >= ?
        ORDER BY opportunity_score DESC, created_at DESC
        LIMIT ?
        """,
        (run_id, PUBLISHABLE_TIER, *excluded, min_score, limit),
    ).fetchall()


def fill_header(template: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^(\*\*{re.escape(field)}:\*\*)[ \t]*(.*?)([ ]{{2}})?$", re.M)
    return pattern.sub(lambda m: f"{m.group(1)} {value}{m.group(3) or ''}", template, count=1)


def blockquote(text: str) -> str:
    return "\n".join("> " + line for line in text.strip().splitlines()) or "> "


def format_score(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "N/A"


def build_prompt(
    template: str,
    records: list[sqlite3.Row],
    run_id: str,
    today: str,
    min_score: float,
) -> str:
    output_format = fill_header(template, "Date", today)
    output_format = fill_header(output_format, "Run ID", run_id)

    lines = [
        "You are the Lead OSINT Analyst and Managing Editor for Notitia Civica.",
        "Synthesize the verified intelligence corpus below into a publication-ready",
        "**World State Brief**, following Notitia Civica's editorial standards and its template.",
        "",
        "---",
        "",
        "## REQUIRED OUTPUT FORMAT",
        "",
        "Follow this template exactly: same sections, same order, same header fields.",
        "Replace the bracketed and italic placeholders; keep the Publication Note as written.",
        "",
        "````markdown",
        output_format.rstrip(),
        "````",
        "",
        "---",
        "",
        "## EDITORIAL STANDARDS",
        "",
        "1. Keep these apart: sourced facts, observable patterns, analytical judgments, open questions, and what to watch next.",
        "2. Confidence ratings:",
        "   - **High:** official filings, statutory language, or corroborated sensor data.",
        "   - **Moderate:** credible primary reporting or institutional analysis.",
        "   - **Directional:** an emerging pattern from weaker signals that needs watching.",
        "3. Declarative, nonpartisan, precise, readable by non-specialists. No loaded words, no rhetorical questions.",
        "4. Every finding cites at least one Record ID from the corpus, e.g. `[rec-c2f9b2ba76fd]`.",
        "   Use only the records below. Do not add facts, sources or numbers from memory.",
        "5. The Source Register lists every source URL you cite.",
        "",
        "---",
        "",
        "## INGESTED INTELLIGENCE CORPUS",
        "",
        f"Run: {run_id} | Records: {len(records)} | Tier: {PUBLISHABLE_TIER} | Score threshold: >= {min_score}",
        "",
    ]

    for index, rec in enumerate(records, 1):
        lines += [
            f"### [{index}/{len(records)}] Record ID: {rec['record_id']}",
            f"- **Source:** {rec['signal_source']} | **Score:** {format_score(rec['opportunity_score'])}"
            f" | **Confidence:** {format_score(rec['confidence'])}"
            f" | **Tier:** {rec['analysis_tier']} | **Class:** {rec['classification']}",
            f"- **URL:** {rec['signal_url'] or 'N/A'}",
            f"- **Local triage assessment:** {rec['llm_reasoning'] or 'none recorded'}",
            "- **Excerpt:**",
            blockquote(rec["signal_excerpt"] or "No excerpt captured"),
            "",
        ]

    return "\n".join(lines)


def export(
    db_path: Path,
    template_path: Path,
    out_dir: Path,
    run_id: str | None,
    min_score: float,
    limit: int,
    excluded: tuple[str, ...],
) -> Path:
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path.resolve()}")
    if not template_path.is_file():
        raise SystemExit(f"Template not found: {template_path}")

    template = template_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        run_id = run_id or latest_verified_run(conn, excluded)
        if run_id is None:
            raise SystemExit(f"No {PUBLISHABLE_TIER} records found in {db_path}. Nothing to export.")
        records = verified_records(conn, run_id, min_score, limit, excluded)
    finally:
        conn.close()

    if not records:
        raise SystemExit(f"Run {run_id} has no {PUBLISHABLE_TIER} records with opportunity_score >= {min_score}.")

    today = datetime.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"world_state_prompt_{today}_{run_id}.md"
    out_path.write_text(build_prompt(template, records, run_id, today, min_score), encoding="utf-8")
    print(f"Wrote {out_path} ({len(records)} records from {run_id})")
    return out_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export SPEC-1 records into a World State Brief prompt.")
    parser.add_argument("--template", type=Path, default=Path("../notitia-civica/templates/world-state-brief.md"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", help="Run ID to export")
    parser.add_argument("--min-score", type=float, default=0.70)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--exclude-source", action="append", dest="excluded")
    args = parser.parse_args(argv)

    tpl = args.template.expanduser()
    if not tpl.exists():
        fallback_paths = [
            Path("~/projects/notitia-civica/templates/world-state-brief.md").expanduser(),
            Path("~/notitia-civica/templates/world-state-brief.md").expanduser(),
            Path("templates/world-state-brief.md").expanduser(),
        ]
        for p in fallback_paths:
            if p.exists():
                tpl = p
                break

    export(
        db_path=args.db.expanduser(),
        template_path=tpl,
        out_dir=args.out_dir.expanduser(),
        run_id=args.run_id,
        min_score=args.min_score,
        limit=args.limit,
        excluded=tuple(args.excluded) if args.excluded else DEFAULT_EXCLUDED_SOURCES,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
