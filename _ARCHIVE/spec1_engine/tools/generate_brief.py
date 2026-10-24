"""CLI: generate a daily intelligence brief from intelligence records.

Tries Claude Sonnet via spec1_engine.briefing.generator first; falls back to
the rule-based cls_world_brief producer if the API call fails or
ANTHROPIC_API_KEY is unset.

Usage:
    PYTHONPATH=src python -m spec1_engine.tools.generate_brief \
        --intel spec1_intelligence.jsonl \
        --run-id latest \
        --out-dir generated/briefs

Reads:  intel JSONL store
Writes: <out-dir>/spec1_brief_<date>.md, spec1_brief_latest.md, brief_index.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


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


def _group_by_run_id(records: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r.get("run_id") or "unknown"].append(r)
    return dict(groups)


def _pick_run(groups: dict[str, list[dict]], run_id: str) -> tuple[str, list[dict]]:
    if run_id != "latest":
        if run_id not in groups:
            raise SystemExit(f"run_id {run_id!r} not found in store")
        return run_id, groups[run_id]
    if not groups:
        raise SystemExit("no records found in store")

    def _ts(records: list[dict]) -> str:
        for r in records:
            ts = r.get("written_at") or r.get("created_at") or r.get("finished_at") or ""
            if ts:
                return str(ts)
        return ""

    latest_id = max(groups.keys(), key=lambda rid: _ts(groups[rid]))
    return latest_id, groups[latest_id]


def _cycle_stats_for(run_id: str, records: list[dict]) -> dict:
    timestamp = ""
    for r in records:
        ts = r.get("written_at") or r.get("created_at") or r.get("finished_at") or ""
        if ts:
            timestamp = str(ts)
            break
    return {
        "run_id": run_id,
        "started_at": records[0].get("started_at", timestamp) if records else timestamp,
        "finished_at": timestamp or datetime.now(timezone.utc).isoformat(),
        "signals_harvested": records[0].get("signals_harvested", len(records)) if records else 0,
        "opportunities_found": records[0].get("opportunities_found", len(records)) if records else 0,
        "records_stored": len(records),
    }


def _try_claude(records: list[dict], cycle_stats: dict, mode: str = "standard") -> tuple[str, str] | None:
    try:
        from spec1_engine.briefing.generator import generate_brief
    except Exception as exc:
        print(f"[generate_brief] briefing.generator unavailable: {exc}", file=sys.stderr)
        return None
    try:
        brief_md, prompts_text = generate_brief(records, cycle_stats, mode=mode)
        return brief_md, prompts_text
    except Exception as exc:
        print(f"[generate_brief] Claude path failed: {exc}", file=sys.stderr)
        return None


def _rule_based_fallback(records: list[dict]) -> str:
    from cls_world_brief.formatter import to_markdown
    from cls_world_brief.producer import produce_brief

    brief = produce_brief(records)
    return to_markdown(brief)


def _write_outputs(out_dir: Path, brief_md: str, prompts: str, run_id: str, timestamp: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        dt = datetime.fromisoformat(timestamp)
    except Exception:
        dt = datetime.now(timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")

    dated_path = out_dir / f"spec1_brief_{date_str}.md"
    latest_path = out_dir / "spec1_brief_latest.md"
    prompts_path = out_dir / f"spec1_prompts_{date_str}.md"
    index_path = out_dir / "brief_index.jsonl"

    dated_path.write_text(brief_md, encoding="utf-8")
    latest_path.write_text(brief_md, encoding="utf-8")
    if prompts:
        prompts_path.write_text(prompts, encoding="utf-8")

    entry = {
        "run_id": run_id,
        "date": date_str,
        "filepath": str(dated_path),
        "word_count": len(brief_md.split()),
        "timestamp": timestamp,
    }
    with index_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return dated_path


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_engine.tools.generate_brief")
    p.add_argument(
        "--intel",
        default=os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"),
        help="Path to intelligence JSONL store",
    )
    p.add_argument(
        "--run-id",
        default="latest",
        help='Specific run_id to brief, or "latest" (default)',
    )
    p.add_argument(
        "--out-dir",
        default=os.environ.get("SPEC1_BRIEFS_DIR", "generated/briefs"),
        help="Directory to write the brief into",
    )
    p.add_argument(
        "--rule-based",
        action="store_true",
        help="Skip Claude and use the rule-based producer directly",
    )
    p.add_argument(
        "--mode",
        default="standard",
        choices=["standard", "geopolitics", "legislative"],
        help="Brief template: standard (default), geopolitics, or legislative",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    intel_path = Path(args.intel)
    out_dir = Path(args.out_dir)

    records = _read_jsonl(intel_path)
    if not records:
        print(f"records=0 intel={intel_path} (nothing to brief)", file=sys.stderr)
        return 0

    groups = _group_by_run_id(records)
    run_id, run_records = _pick_run(groups, args.run_id)
    cycle_stats = _cycle_stats_for(run_id, run_records)

    brief_md = ""
    prompts = ""
    used_fallback = False

    if not args.rule_based:
        result = _try_claude(run_records, cycle_stats, mode=args.mode)
        if result is not None:
            brief_md, prompts = result

    if not brief_md:
        brief_md = _rule_based_fallback(run_records)
        used_fallback = True

    out_path = _write_outputs(out_dir, brief_md, prompts, run_id, cycle_stats["finished_at"])
    word_count = len(brief_md.split())
    source = "rule-based" if used_fallback else "claude"
    print(
        f"run_id={run_id} records={len(run_records)} words={word_count} "
        f"source={source} -> {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
