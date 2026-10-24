"""CLI: derive actionable Lead objects from intelligence records.

Usage:
    PYTHONPATH=src python -m spec1_engine.tools.generate_leads \
        --intel spec1_intelligence.jsonl \
        --out generated/leads.jsonl \
        --min-confidence 0.3 \
        --max-leads 50

Reads:  intel JSONL store
Writes: <out>: one Lead per JSONL line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cls_leads.generator import generate_leads
from cls_leads.store import LeadStore
from spec1_labels import PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
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


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_engine.tools.generate_leads")
    p.add_argument(
        "--intel",
        default=os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"),
        help="Path to intelligence JSONL store",
    )
    p.add_argument(
        "--out",
        default=os.environ.get("SPEC1_LEADS_PATH", "generated/leads.jsonl"),
        help="Path to write Lead JSONL",
    )
    p.add_argument(
        "--min-confidence",
        type=float,
        default=0.3,
        help="Minimum record confidence to consider (default 0.3)",
    )
    p.add_argument(
        "--max-leads",
        type=int,
        default=50,
        help="Maximum leads to write, sorted by priority (default 50)",
    )
    p.add_argument(
        "--priority",
        choices=[PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW],
        default=None,
        help="Filter to a single priority level (default: keep all)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    intel_path = Path(args.intel)
    out_path = Path(args.out)

    records = _read_jsonl(intel_path)
    if not records:
        print(f"records=0 intel={intel_path} (no records to lead)", file=sys.stderr)
        return 0

    leads = generate_leads(
        records,
        min_confidence=args.min_confidence,
        max_leads=args.max_leads,
    )
    if args.priority:
        leads = [lead for lead in leads if lead.priority == args.priority]

    store = LeadStore(out_path)
    written = store.save_batch(leads)

    by_priority: dict[str, int] = {}
    for lead in leads:
        by_priority[lead.priority] = by_priority.get(lead.priority, 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(by_priority.items()))
    print(
        f"records={len(records)} leads={len(leads)} written={len(written)} "
        f"-> {out_path} [{breakdown}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
