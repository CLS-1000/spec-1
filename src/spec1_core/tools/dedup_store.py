# @domain:    machine
# @module:    dedup_store
# @loc:      gh_main
# @status:    stable
# @depends:  NONE

"""Non-destructive JSONL store deduplicator.

Reads an intelligence JSONL store, keeps the first occurrence per ``record_id``,
and writes a new ``<name>.dedup.jsonl`` file plus a drop report without modifying
the source file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spec1_core.intelligence.store import resolve_store_path


def dedup_jsonl_store(
    source_path: Path,
    output_path: Path | None = None,
    pk_field: str = "record_id",
) -> dict:
    """Write a deduplicated copy of *source_path* keeping the first record per PK.

    Never modifies or truncates *source_path*.
    """
    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Store not found: {src}")

    dst = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else src.with_name(f"{src.stem}.dedup.jsonl")
    )
    if dst == src:
        raise ValueError("Output path must differ from source path to preserve the original file.")

    seen_pks: set[str] = set()
    kept_lines: list[str] = []
    dropped_line_numbers: list[int] = []
    malformed_line_numbers: list[int] = []
    total_non_empty = 0

    with src.open("r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            total_non_empty += 1
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                malformed_line_numbers.append(line_no)
                continue

            pk = rec.get(pk_field)
            if pk is not None:
                if pk in seen_pks:
                    dropped_line_numbers.append(line_no)
                    continue
                seen_pks.add(pk)

            kept_lines.append(stripped)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as out:
        for item in kept_lines:
            out.write(item + "\n")

    return {
        "source_path": str(src),
        "output_path": str(dst),
        "total_lines": total_non_empty,
        "kept_count": len(kept_lines),
        "dropped_count": len(dropped_line_numbers),
        "dropped_line_numbers": dropped_line_numbers,
        "malformed_line_numbers": malformed_line_numbers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Non-destructive SPEC-1 JSONL deduplicator")
    parser.add_argument(
        "--store",
        default=None,
        help="Input JSONL store path (defaults to resolved SPEC1_STORE_PATH)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output deduplicated JSONL path (defaults to <store_stem>.dedup.jsonl)",
    )
    parser.add_argument("--pk-field", default="record_id", help="Primary key field name")
    args = parser.parse_args(argv)

    src = resolve_store_path(args.store)
    out = Path(args.output) if args.output else None
    report = dedup_jsonl_store(src, output_path=out, pk_field=args.pk_field)
    print(json.dumps({k: v for k, v in report.items() if k != "dropped_line_numbers"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
