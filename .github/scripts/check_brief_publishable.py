#!/usr/bin/env python3
"""Decide whether a generated brief is real output or a failed-run artifact.

``generate_brief()`` never raises. When ``ANTHROPIC_API_KEY`` is missing or the
API call fails it returns ``_fallback_brief()`` — a stub that interpolates the
whole ``cycle_stats`` dict — and the cycle writes that to disk and exits 0. A
green cycle run therefore says nothing about whether a brief was produced.

This gate reads the brief the cycle just wrote and answers one question: is
this publishable? It is the thing standing between a failed run and the
publication repo.

Two signals, because the first one alone is brittle:

1. The fallback marker. Exact, but only catches the stub we know about.
2. Word count. A real brief is bounded above by ``MAX_TOKENS`` (2500 → roughly
   1900 words) and is not a stub below. A stats dump blows through the ceiling —
   the 2026-08-04 run wrote 32,971 words. Anything far outside the plausible
   band is not a brief regardless of what it contains.

Exit 0 when publishable, 1 when not, 2 on a usage error. ``--soft`` reports
without failing, for callers that want to branch on the output instead.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Emitted by _fallback_brief() in both briefing/generator.py copies.
FALLBACK_MARKER = "[Brief generation failed."

# A real brief is generated under MAX_TOKENS=2500 (spec1_engine) or 4000
# (spec1_core), so ~1900 and ~3000 words respectively. The ceiling is set well
# clear of that to flag stats dumps without tripping on a long legitimate brief.
DEFAULT_MIN_WORDS = 200
DEFAULT_MAX_WORDS = 10_000


def _emit(name: str, value: str) -> None:
    """Write a step output when running under Actions; always echo locally."""
    print(f"{name}={value}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def check(path: Path, min_words: int, max_words: int) -> tuple[bool, str]:
    """Return (publishable, reason)."""
    if not path.exists():
        return False, f"no brief at {path} — the cycle wrote nothing"

    text = path.read_text(encoding="utf-8", errors="replace")
    words = len(text.split())

    if FALLBACK_MARKER in text:
        return False, (
            f"fallback brief ({words} words) — generate_brief() returned its stub, "
            "so the LLM call did not succeed. Check ANTHROPIC_API_KEY."
        )
    if words < min_words:
        return False, f"brief is {words} words, below the {min_words}-word floor"
    if words > max_words:
        return False, (
            f"brief is {words} words, above the {max_words}-word ceiling — "
            "far past what MAX_TOKENS allows, so this is a data dump, not a brief"
        )
    return True, f"brief looks real ({words} words)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brief", type=Path, help="path to the brief markdown file")
    ap.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    ap.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    ap.add_argument(
        "--soft",
        action="store_true",
        help="report and exit 0 even when the brief is not publishable",
    )
    args = ap.parse_args(argv)

    if args.min_words > args.max_words:
        print("error: --min-words exceeds --max-words", file=sys.stderr)
        return 2

    publishable, reason = check(args.brief, args.min_words, args.max_words)

    _emit("publishable", "true" if publishable else "false")
    _emit("reason", reason)

    if publishable:
        print(f"::notice::brief gate passed — {reason}")
        return 0

    print(f"::error::brief gate failed — {reason}")
    return 0 if args.soft else 1


if __name__ == "__main__":
    raise SystemExit(main())
