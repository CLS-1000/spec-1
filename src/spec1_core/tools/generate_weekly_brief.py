# @domain:   publisher
# @module:   tools_generate_weekly_brief
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""CLI: generate a weekly public intelligence brief from intelligence records.

Aggregates 7 days of IntelligenceRecords, classifies evidence into
VERIFIED/INFERRED/SPECULATION tiers, and produces a PublicWeeklyBrief.

Usage:
    PYTHONPATH=src python -m spec1_core.tools.generate_weekly_brief \\
        --intel spec1_intelligence.jsonl \\
        --week 2026-W34 \\
        --out-dir generated/weekly_briefs

    # Or use current week (default):
    PYTHONPATH=src python -m spec1_core.tools.generate_weekly_brief \\
        --intel spec1_intelligence.jsonl

Reads:  intel JSONL store
Writes: <out-dir>/weekly_brief_<week_id>.md, weekly_briefs.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from cls_weekly_brief import (
    produce_weekly_brief,
    to_markdown,
    to_json_summary,
    WeeklyBriefStore,
)


def _read_jsonl(path: Path) -> list[dict]:
    """Read JSONL file into list of dicts."""
    if not path.exists():
        print(f"[generate_weekly_brief] Store not found: {path}", file=sys.stderr)
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Generate public weekly intelligence brief from SPEC-1 records"
    )
    parser.add_argument(
        "--intel",
        type=Path,
        default=Path("spec1_intelligence.jsonl"),
        help="Path to intelligence JSONL store",
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="ISO week format YYYY-W##; defaults to current week",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("generated/weekly_briefs"),
        help="Output directory for Markdown and JSONL",
    )

    args = parser.parse_args()

    # Read records
    records = _read_jsonl(args.intel)
    if not records:
        print(f"[generate_weekly_brief] No records found in {args.intel}", file=sys.stderr)
        sys.exit(1)

    print(f"[generate_weekly_brief] Loaded {len(records)} records from {args.intel}")

    # Generate brief
    brief = produce_weekly_brief(records, week_id=args.week)

    print(f"[generate_weekly_brief] Generated brief {brief.brief_id}")
    print(f"  Week: {brief.week_id} ({brief.week_start} to {brief.week_end})")
    print(f"  Records analyzed: {brief.records_analyzed}")
    print(f"  Evidence: {brief.verified_count} VERIFIED, {brief.inferred_count} INFERRED, "
          f"{brief.speculation_count} SPECULATION")

    # Write outputs
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Store to JSONL (append-only)
    store = WeeklyBriefStore(args.out_dir / "weekly_briefs.jsonl")
    store.save(brief, write_markdown=True)

    # Also write Markdown directly to out-dir
    md_path = args.out_dir / f"weekly_{brief.week_id}.md"
    md_content = to_markdown(brief)
    with md_path.open("w", encoding="utf-8") as fh:
        fh.write(md_content)

    print(f"[generate_weekly_brief] Written to {md_path}")

    # Write index
    index_path = args.out_dir / "weekly_brief_index.jsonl"
    all_briefs = list(store.read_all())
    with index_path.open("w", encoding="utf-8") as fh:
        for b in all_briefs:
            # b is already a dict from store.read_all()
            if isinstance(b, dict):
                summary = {
                    "brief_id": b.get("brief_id"),
                    "week_id": b.get("week_id"),
                    "week_start": b.get("week_start"),
                    "week_end": b.get("week_end"),
                    "records_analyzed": b.get("records_analyzed"),
                    "verified_count": b.get("verified_count"),
                    "inferred_count": b.get("inferred_count"),
                    "speculation_count": b.get("speculation_count"),
                    "produced_at": b.get("produced_at"),
                }
            else:
                summary = to_json_summary(b)
            fh.write(json.dumps(summary) + "\n")

    print(f"[generate_weekly_brief] Updated index: {index_path} ({len(all_briefs)} briefs)")
    print("[generate_weekly_brief] Done")


if __name__ == "__main__":
    main()
