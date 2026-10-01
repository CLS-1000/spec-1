#!/usr/bin/env python3
# @domain:   spec-1
# @module:   tag_repo
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""
Bulk metadata tagger for SPEC-1 repo.
Infers @domain, @module, @loc, @status, @depends from path.
Inserts tag block at top of each untagged .py file.
DRY RUN by default — pass --write to apply.

Usage:
    python scripts/tag_repo.py              # preview only
    python scripts/tag_repo.py --write      # apply tags
    python scripts/tag_repo.py --write --path src/spec1_core
"""

import os
import re
import sys
import argparse
from pathlib import Path

REPO_ROOT   = Path(__file__).parent.parent
TAG_PATTERN = re.compile(r"#\s*@\w+:")

SKIP_DIRS  = {"_ARCHIVE", ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
SKIP_FILES = {"__init__.py", "conftest.py"}

# ── DOMAIN MAP ───────────────────────────────────────────────
# Order matters — first match wins
DOMAIN_RULES = [
    # namespace-level
    ("src/spec1_engine",      "spec1_engine"),
    ("src/spec1_core",        "spec-1"),
    ("src/spec1_api",         "spec-1"),
    ("src/spec1_analytics",   "spec-1"),
    ("src/cls_pdx1",          "citizens_source"),
    ("src/cls_osint",         "spec-1"),
    ("src/cls_db",            "spec-1"),
    ("src/cls_analyst_loop",  "spec-1"),
    ("src/cls_calibration",   "spec-1"),
    ("src/cls_leads",         "spec-1"),
    ("src/cls_leg_jud",       "spec-1"),
    ("src/cls_psyop",         "spec-1"),
    ("src/cls_verdicts",      "spec-1"),
    ("src/cls_world_brief",   "spec-1"),
    # root-level
    ("cls_pdx1/",             "citizens_source"),
    ("tests/",                "spec-1"),
    ("scripts/",              "spec-1"),
    ("tools/",                "spec-1"),
    (".github/",              "spec-1"),
]

# ── STATUS HEURISTICS ────────────────────────────────────────
def infer_status(rel: Path) -> str:
    parts = rel.parts
    if "tests" in parts:
        return "testing"
    if "tools" in parts or "scripts" in parts:
        return "drafting"
    if "spec1_engine" in str(rel):
        return "stable"
    if "spec1_core" in str(rel):
        return "stable"
    if "spec1_api" in str(rel):
        return "stable"
    return "drafting"

# ── LOC HEURISTICS ───────────────────────────────────────────
def infer_loc(rel: Path) -> str:
    if "spec1_engine" in str(rel):
        return "gh_main"
    if "spec1_core" in str(rel):
        return "gh_main"
    if "spec1_api" in str(rel):
        return "gh_main"
    if "tests" in rel.parts:
        return "gh_main"
    return "_SCRATCH"

# ── DOMAIN INFERENCE ─────────────────────────────────────────
def infer_domain(rel: Path) -> str:
    s = str(rel)
    for pattern, domain in DOMAIN_RULES:
        if pattern in s:
            return domain
    return "spec-1"

# ── MODULE INFERENCE ─────────────────────────────────────────
def infer_module(rel: Path) -> str:
    parts = rel.parts
    stem  = rel.stem

    # tests: use test target name
    if "tests" in parts:
        return stem  # e.g. test_harvester

    # src files: parent_stem (e.g. signal/harvester -> signal_harvester)
    if len(parts) >= 3 and parts[0] == "src":
        ns     = parts[1]   # e.g. spec1_core
        subpkg = parts[2] if len(parts) > 3 else ""
        if subpkg and subpkg not in ("__init__",):
            return f"{subpkg}_{stem}" if stem != "__init__" else subpkg
        return stem

    return stem

# ── DEPENDS INFERENCE ────────────────────────────────────────
def infer_depends(rel: Path) -> str:
    s = str(rel)
    if "spec1_api" in s:
        return "spec1_core, cls_db"
    if "briefing" in s:
        return "spec1_core/schemas"
    if "signal" in s:
        return "spec1_core/config/calibration.py"
    if "cls_analyst_loop" in s:
        return "cls_db"
    if "cls_osint" in s:
        return "cls_db, spec1_core"
    if "tests" in rel.parts:
        return "NONE"
    return "NONE"

# ── TAG BLOCK BUILDER ────────────────────────────────────────
def build_tag_block(rel: Path) -> str:
    domain  = infer_domain(rel)
    module  = infer_module(rel)
    loc     = infer_loc(rel)
    status  = infer_status(rel)
    depends = infer_depends(rel)
    return (
        f"# @domain:   {domain}\n"
        f"# @module:   {module}\n"
        f"# @loc:      {loc}\n"
        f"# @status:   {status}\n"
        f"# @depends:  {depends}\n"
    )

# ── ALREADY TAGGED? ──────────────────────────────────────────
def is_tagged(filepath: Path) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i > 10:
                    break
                if TAG_PATTERN.match(line.strip()):
                    return True
    except Exception:
        pass
    return False

# ── INSERT TAGS ──────────────────────────────────────────────
def insert_tags(filepath: Path, tag_block: str, dry_run: bool) -> bool:
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False

    lines = content.splitlines(keepends=True)

    # find insert point: after shebang if present, else top
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1

    new_lines = lines[:insert_at] + [tag_block + "\n"] + lines[insert_at:]
    new_content = "".join(new_lines)

    if not dry_run:
        filepath.write_text(new_content, encoding="utf-8")
    return True

# ── MAIN ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SPEC-1 Bulk Tagger")
    parser.add_argument("--write", action="store_true", help="Apply tags (default: dry run)")
    parser.add_argument("--path",  default="", help="Limit to subdirectory (relative to repo root)")
    args = parser.parse_args()

    dry_run    = not args.write
    search_root = REPO_ROOT / args.path if args.path else REPO_ROOT

    print(f"\n{'[DRY RUN] ' if dry_run else '[WRITING] '}Scanning {search_root}\n")

    tagged   = []
    skipped  = []
    already  = []
    errors   = []

    for root, dirs, files in os.walk(search_root):
        dirs[:] = sorted([d for d in dirs if d not in SKIP_DIRS])
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            if fname in SKIP_FILES:
                continue

            fpath = Path(root) / fname
            rel   = fpath.relative_to(REPO_ROOT)

            # skip spec1_engine per standing rule
            if "spec1_engine" in str(rel):
                skipped.append(rel)
                continue

            if is_tagged(fpath):
                already.append(rel)
                continue

            tag_block = build_tag_block(rel)
            ok = insert_tags(fpath, tag_block, dry_run)

            if ok:
                tagged.append((rel, tag_block))
            else:
                errors.append(rel)

    # report
    print(f"{'Would tag' if dry_run else 'Tagged'}:    {len(tagged)} files")
    print(f"Already tagged: {len(already)} files")
    print(f"Skipped:        {len(skipped)} files (spec1_engine — standing rule)")
    print(f"Errors:         {len(errors)} files")

    if tagged:
        print(f"\n{'── PREVIEW ──' if dry_run else '── APPLIED ──'}")
        for rel, block in tagged[:20]:
            print(f"\n  {rel}")
            for line in block.strip().splitlines():
                print(f"    {line}")
        if len(tagged) > 20:
            print(f"\n  ... and {len(tagged) - 20} more")

    if dry_run and tagged:
        print(f"\nRun with --write to apply.\n")

if __name__ == "__main__":
    main()
