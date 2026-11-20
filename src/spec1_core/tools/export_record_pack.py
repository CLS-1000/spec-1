"""Export a record pack for a World State Brief.

    PYTHONPATH=src python -m spec1_core.tools.export_record_pack \\
        --since-hours 48 --out briefs/packs/pack_<label>.json

    PYTHONPATH=src python -m spec1_core.tools.export_record_pack \\
        --run-id run-5043af20d6b1 --out briefs/packs/pack_run-5043af20d6b1.json

Reads spec1.db read-only. Exits 1 when the window holds no stored records:
a brief is never written from an empty pack. Never overwrites an existing pack.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from spec1_core.briefing.record_pack import (
    RecordPackError,
    build_record_pack,
    write_record_pack,
)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_core.tools.export_record_pack")
    p.add_argument("--db", default="spec1.db")
    p.add_argument("--log", default="logs/llm_fallback.jsonl")
    p.add_argument("--psyop", default="data/psyop_signals.jsonl")
    p.add_argument("--since-hours", type=float, help="records written in the last N hours")
    p.add_argument("--until", help="ISO time the window ends (default: now)")
    p.add_argument("--run-id", action="append", default=[], help="limit to run id(s)")
    p.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    now = datetime.now(timezone.utc)
    until = datetime.fromisoformat(args.until.replace("Z", "+00:00")) if args.until else None
    end = until or now
    since = end - timedelta(hours=args.since_hours) if args.since_hours else None
    if since is None and not args.run_id:
        print("give --since-hours or --run-id", file=sys.stderr)
        return 2
    try:
        pack = build_record_pack(Path(args.db), Path(args.log), since=since, until=until,
                                 run_ids=args.run_id or None, psyop_path=Path(args.psyop),
                                 now=now)
        out = write_record_pack(pack, Path(args.out))
    except (RecordPackError, FileExistsError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    c = pack["counts"]
    print(f"wrote {out}: {c['records']} records, {c['usable_for_analysis']} usable for analysis; "
          f"tiers {c['by_tier']}; tier sources {c['by_tier_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
