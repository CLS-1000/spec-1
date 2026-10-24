"""CLI: read intelligence records, score them for psyop patterns, write JSONL.

Usage:
    PYTHONPATH=src python -m spec1_engine.tools.run_psyop \
        --intel spec1_intelligence.jsonl \
        --out generated/psyop_scores.jsonl

Reads:  intel JSONL store (default $SPEC1_STORE_PATH or spec1_intelligence.jsonl)
Writes: PsyopScore per record, one JSON line per score.

Exit code 0 on success.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cls_psyop.scorer import filter_risky, score_records
from cls_psyop.store import PsyopStore
from spec1_labels import PSYOP_CLEAN, PSYOP_LOW_RISK, PSYOP_MEDIUM_RISK, PSYOP_HIGH_RISK


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
    p = argparse.ArgumentParser(prog="spec1_engine.tools.run_psyop")
    p.add_argument(
        "--intel",
        default=os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"),
        help="Path to intelligence JSONL store",
    )
    p.add_argument(
        "--out",
        default=os.environ.get("SPEC1_PSYOP_PATH", "generated/psyop_scores.jsonl"),
        help="Path to write PsyopScore JSONL",
    )
    p.add_argument(
        "--min-classification",
        choices=[PSYOP_CLEAN, PSYOP_LOW_RISK, PSYOP_MEDIUM_RISK, PSYOP_HIGH_RISK],
        default=PSYOP_CLEAN,
        help="Only persist scores at or above this classification (default: CLEAN — keep all)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    intel_path = Path(args.intel)
    out_path = Path(args.out)

    records = _read_jsonl(intel_path)
    if not records:
        print(f"records=0 intel={intel_path} (no records to score)", file=sys.stderr)
        return 0

    scores = score_records(records)
    if args.min_classification != PSYOP_CLEAN:
        scores = filter_risky(scores, min_classification=args.min_classification)

    store = PsyopStore(out_path)
    written = store.save_batch(scores)

    by_class: dict[str, int] = {}
    for s in scores:
        by_class[s.classification] = by_class.get(s.classification, 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(by_class.items()))
    print(
        f"records={len(records)} scored={len(scores)} written={len(written)} "
        f"-> {out_path} [{breakdown}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
