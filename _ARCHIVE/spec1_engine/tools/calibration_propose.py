"""Calibration proposal CLI — surfaces drift for human review.

Reads intel records + verdicts, produces a descriptive ProposalReport,
and writes it to --out-dir as both Markdown and JSONL.

Per governance (CLAUDE.md rule 11): calibration is descriptive only.
This tool never changes thresholds automatically — it surfaces drift
so a human can decide whether to act.

Usage:
    python -m spec1_engine.tools.calibration_propose \\
        --intel spec1_intelligence.jsonl \\
        --verdicts verdicts.jsonl \\
        --out-dir generated/

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cls_calibration.aggregator import produce_report
from cls_calibration.formatter import to_markdown
from cls_calibration.proposer import propose_adjustments
from cls_calibration.schemas import CalibrationReport
from cls_verdicts.schemas import Verdict


def _load_records(path: Path) -> list[dict]:
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_verdicts(path: Path) -> list[Verdict]:
    verdicts = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                raw = json.loads(line)
                if "verdict_id" not in raw:
                    raw["verdict_id"] = Verdict.make_id(
                        raw.get("record_id", ""),
                        raw.get("reviewer", "anonymous"),
                        raw.get("reviewed_at", ""),
                    )
                verdicts.append(Verdict(**raw))
    return verdicts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce a descriptive calibration proposal from intel + verdicts."
    )
    parser.add_argument("--intel", required=True, help="Path to spec1_intelligence.jsonl")
    parser.add_argument("--verdicts", required=True, help="Path to verdicts.jsonl")
    parser.add_argument("--out-dir", required=True, help="Directory for output files")
    parser.add_argument("--sample-floor", type=int, default=10,
                        help="Min verdicts per bucket to include in report (default: 10)")
    parser.add_argument("--delta-floor", type=float, default=0.10,
                        help="Min accuracy delta to flag as a suggested adjustment (default: 0.10)")
    args = parser.parse_args(argv)

    intel_path = Path(args.intel)
    verdicts_path = Path(args.verdicts)
    out_dir = Path(args.out_dir)

    if not intel_path.exists():
        print(f"ERROR: intel file not found: {intel_path}", file=sys.stderr)
        return 1
    if not verdicts_path.exists():
        print(f"ERROR: verdicts file not found: {verdicts_path}", file=sys.stderr)
        return 1

    records = _load_records(intel_path)
    verdict_objs = _load_verdicts(verdicts_path)
    verdict_dicts = [v.to_dict() for v in verdict_objs]

    report: CalibrationReport = produce_report(records, verdict_dicts)
    proposal = propose_adjustments(
        report,
        sample_floor=args.sample_floor,
        delta_floor=args.delta_floor,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "calibration_report.md"
    jsonl_path = out_dir / "calibration_report.jsonl"

    md_path.write_text(to_markdown(proposal), encoding="utf-8")
    with jsonl_path.open("a", encoding="utf-8") as f:
        entry = {
            "calibration": report.to_dict(),
            "proposal": proposal.to_dict(),
        }
        f.write(json.dumps(entry, default=str) + "\n")

    print(f"Calibration report written to {out_dir}")
    print(to_markdown(proposal))
    return 0


if __name__ == "__main__":
    sys.exit(main())
