#!/usr/bin/env python3
# @domain:   spec-1
# @module:   check_hardcoded_labels
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Check for hardcoded label/enum strings in Python source files.

Scans ``src/`` for bare string literals that should be imported from
``spec1_labels`` instead.  Exits 0 when clean, 1 when violations are found.

Usage::

    python .github/scripts/check_hardcoded_labels.py [--src-dir src]

In CI::

    python .github/scripts/check_hardcoded_labels.py

"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical label values that MUST be imported from spec1_labels, never
# hard-coded as bare string literals inside modules.
# We exempt spec1_labels.py itself and test files.
# ---------------------------------------------------------------------------
CANONICAL_LABELS: set[str] = {
    # Priorities
    "CRITICAL",
    "PRIORITY_CRITICAL",
    # Psyop classifications
    "HIGH_RISK",
    "MEDIUM_RISK",
    "LOW_RISK",
    "CLEAN",
    # Psyop threat levels (single-word values also used elsewhere — we check
    # them only in files under cls_psyop/, cls_leads/)
}

# Labels that are context-sensitive: only flag in specific module paths
_CONTEXT_SENSITIVE: dict[str, set[str]] = {
    # These single-word strings are ambiguous — only flag in known hot-spots
    "HIGH":   {"cls_psyop", "cls_leads"},
    "MEDIUM": {"cls_psyop", "cls_leads"},
    "LOW":    {"cls_psyop", "cls_leads"},
    # Psyop-specific risk words
    "HIGH_RISK":   {"cls_psyop", "cls_leads"},
    "MEDIUM_RISK": {"cls_psyop", "cls_leads"},
    "LOW_RISK":    {"cls_psyop", "cls_leads"},
    "CLEAN":       {"cls_psyop"},
    # Priority words
    "CRITICAL": {"cls_leads"},
}

# Files/directories to exclude from scanning
_EXCLUDES: tuple[str, ...] = (
    "spec1_labels.py",
    "test_",
    ".venv",
    "__pycache__",
    "node_modules",
)

# Reverse mapping: label *value* → canonical constant name in spec1_labels.
# Used to produce accurate, actionable violation messages.
_LABEL_TO_CONSTANT: dict[str, str] = {
    "CRITICAL":    "PRIORITY_CRITICAL",
    "HIGH_RISK":   "PSYOP_HIGH_RISK",
    "MEDIUM_RISK": "PSYOP_MEDIUM_RISK",
    "LOW_RISK":    "PSYOP_LOW_RISK",
    "CLEAN":       "PSYOP_CLEAN",
    # Ambiguous single-word values — list the most likely candidates.
    "HIGH":   "PRIORITY_HIGH or THREAT_HIGH",
    "MEDIUM": "PRIORITY_MEDIUM or THREAT_MEDIUM",
    "LOW":    "PRIORITY_LOW or THREAT_LOW",
}


def _violation_message(value: str) -> str:
    constant = _LABEL_TO_CONSTANT.get(value)
    if constant:
        return (
            f"Import the canonical constant from spec1_labels "
            f"(e.g. spec1_labels.{constant}) instead of bare string {value!r}"
        )
    return f"Import the canonical constant from spec1_labels instead of bare string {value!r}"


def _is_excluded(path: Path) -> bool:
    parts = path.parts
    for exc in _EXCLUDES:
        if any(exc in p for p in parts):
            return True
    return False


def _relevant_context(path: Path, label: str) -> bool:
    """Return True if label should be checked in this path."""
    if label not in _CONTEXT_SENSITIVE:
        return True  # always relevant
    required_contexts = _CONTEXT_SENSITIVE[label]
    path_str = str(path)
    return any(ctx in path_str for ctx in required_contexts)


def _extract_string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Return (lineno, value) for every string constant in the AST."""
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            results.append((node.lineno, node.value))
    return results


def check_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (lineno, label, reason) violations in *path*."""
    violations: list[tuple[int, str, str]] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return violations

    all_labels = CANONICAL_LABELS | set(_CONTEXT_SENSITIVE.keys())
    for lineno, value in _extract_string_literals(tree):
        if value in all_labels and _relevant_context(path, value):
            violations.append(
                (lineno, value, _violation_message(value))
            )
    return violations


def scan(src_dir: Path) -> dict[Path, list[tuple[int, str, str]]]:
    """Scan all .py files under *src_dir*; return {path: [violations]}."""
    findings: dict[Path, list[tuple[int, str, str]]] = {}
    for py_file in sorted(src_dir.rglob("*.py")):
        if _is_excluded(py_file):
            continue
        violations = check_file(py_file)
        if violations:
            findings[py_file] = violations
    return findings


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Detect hardcoded label strings that should come from spec1_labels.",
    )
    p.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Source directory to scan (default: src/).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    src_dir = args.src_dir

    if not src_dir.is_dir():
        print(f"ERROR: source directory not found: {src_dir}", file=sys.stderr)
        return 2

    findings = scan(src_dir)

    if not findings:
        print("✓ No hardcoded label strings found")
        return 0

    total = sum(len(v) for v in findings.values())
    print(f"✗ Found {total} hardcoded label(s) in {len(findings)} file(s):\n")
    for path, violations in sorted(findings.items()):
        for lineno, label, reason in violations:
            print(f"  {path}:{lineno}: {reason}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
