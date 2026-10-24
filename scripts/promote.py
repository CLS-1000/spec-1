#!/usr/bin/env python3
# @domain:   spec-1
# @module:   promote
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""
Batch promoter for SPEC-1 tag system.
Updates @loc and @status tags across a namespace or file list.

Usage:
    python scripts/promote.py --namespace spec1_core
    python scripts/promote.py --namespace cls_analyst_loop
    python scripts/promote.py --namespace tests --status testing
    python scripts/promote.py --file src/spec1_core/signal/harvester.py
    python scripts/promote.py --namespace spec1_core --dry-run
"""

import os
import re
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

LOC_PATTERN    = re.compile(r"(#\s*@loc:\s*)(\S+)")
STATUS_PATTERN = re.compile(r"(#\s*@status:\s*)(\S+)")
TAG_PATTERN    = re.compile(r"#\s*@\w+:")

SKIP_DIRS = {"_ARCHIVE", ".git", "__pycache__", "node_modules", ".venv", "venv"}

# Namespace → path fragment mapping
NAMESPACE_PATHS = {
    "spec1_core":       "src/spec1_core",
    "spec1_api":        "src/spec1_api",
    "spec1_analytics":  "src/spec1_analytics",
    "cls_analyst_loop": "src/cls_analyst_loop",
    "cls_calibration":  "src/cls_calibration",
    "cls_db":           "src/cls_db",
    "cls_leads":        "src/cls_leads",
    "cls_leg_jud":      "src/cls_leg_jud",
    "cls_osint":        "src/cls_osint",
    "cls_pdx1":         "src/cls_pdx1",
    "cls_psyop":        "src/cls_psyop",
    "cls_verdicts":     "src/cls_verdicts",
    "cls_world_brief":  "src/cls_world_brief",
    "tests":            "tests",
    "scripts":          "scripts",
    "tools":            "tools",
    "citizens_source": "src/cls_pdx1",
}

def update_tags(filepath: Path, new_loc: str, new_status: str, dry_run: bool) -> tuple[bool, str, str]:
    """Returns (changed, old_loc, old_status)"""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False, "", ""

    old_loc    = ""
    old_status = ""

    m = LOC_PATTERN.search(content)
    if m:
        old_loc = m.group(2)

    m = STATUS_PATTERN.search(content)
    if m:
        old_status = m.group(2)

    # only update if file has tags
    if not old_loc and not old_status:
        return False, "", ""

    # skip if already at target
    if old_loc == new_loc and old_status == new_status:
        return False, old_loc, old_status

    new_content = content
    if old_loc and old_loc != new_loc:
        new_content = LOC_PATTERN.sub(lambda m: m.group(1) + new_loc, new_content, count=1)
    if old_status and old_status != new_status:
        new_content = STATUS_PATTERN.sub(lambda m: m.group(1) + new_status, new_content, count=1)

    if not dry_run:
        filepath.write_text(new_content, encoding="utf-8")

    return True, old_loc, old_status

def collect_files(namespace: str) -> list[Path]:
    path_fragment = NAMESPACE_PATHS.get(namespace)
    if not path_fragment:
        # try treating namespace as a direct path fragment
        path_fragment = namespace

    search_root = REPO_ROOT / path_fragment
    if not search_root.exists():
        print(f"[FAIL] Path not found: {search_root}")
        sys.exit(1)

    files = []
    for root, dirs, filenames in os.walk(search_root):
        dirs[:] = sorted([d for d in dirs if d not in SKIP_DIRS])
        for fname in sorted(filenames):
            if fname.endswith(".py"):
                files.append(Path(root) / fname)
    return files

def main():
    parser = argparse.ArgumentParser(description="SPEC-1 Batch Promoter")
    parser.add_argument("--namespace", help="Namespace to promote (e.g. spec1_core, cls_db, tests)")
    parser.add_argument("--file",      help="Single file to promote")
    parser.add_argument("--loc",       default="gh_main", help="Target @loc (default: gh_main)")
    parser.add_argument("--status",    default="stable",  help="Target @status (default: stable)")
    parser.add_argument("--dry-run",   action="store_true", help="Preview only, no writes")
    args = parser.parse_args()

    if not args.namespace and not args.file:
        parser.print_help()
        sys.exit(1)

    dry_run    = args.dry_run
    new_loc    = args.loc
    new_status = args.status

    if args.file:
        files = [REPO_ROOT / args.file]
    else:
        files = collect_files(args.namespace)

    print(f"\n{'[DRY RUN] ' if dry_run else '[WRITING] '}"
          f"Promoting {len(files)} files → @loc: {new_loc} / @status: {new_status}\n")

    promoted  = []
    skipped   = []
    no_tags   = []

    for fpath in files:
        rel = fpath.relative_to(REPO_ROOT)
        changed, old_loc, old_status = update_tags(fpath, new_loc, new_status, dry_run)

        if not old_loc and not old_status:
            no_tags.append(rel)
        elif not changed:
            skipped.append(rel)
        else:
            promoted.append((rel, old_loc, old_status))

    # report
    print(f"{'Would promote' if dry_run else 'Promoted'}: {len(promoted)} files")
    print(f"Already at target:  {len(skipped)} files")
    print(f"No tags found:      {len(no_tags)} files")

    if promoted:
        print(f"\n── {'PREVIEW' if dry_run else 'APPLIED'} ──")
        for rel, old_loc, old_status in promoted:
            print(f"  {rel}")
            print(f"    @loc:    {old_loc} → {new_loc}")
            print(f"    @status: {old_status} → {new_status}")

    if dry_run and promoted:
        print("\nRun without --dry-run to apply.\n")

    if not dry_run and promoted:
        print("\nNext steps:")
        print("  spec1-index")
        print(f"  git add -A && git commit -m \"chore: promote {args.namespace or args.file} to {new_loc}\"")
        print()

if __name__ == "__main__":
    main()
