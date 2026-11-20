"""Validate and render a World State Brief from a spec and a record pack.

    PYTHONPATH=src python -m spec1_core.tools.render_world_state_brief \\
        --spec brief_spec.json --pack pack.json --out-dir briefs/world_state [--pdf]

Writes <stem>.md, <stem>.html and <stem>.meta.json, where the stem carries the
date, run ids and pack hash, and refuses to overwrite. ``--pdf`` also prints
the HTML to <stem>.pdf with headless Chromium, in a subprocess; there is no
PDF unless asked. Exits 1, writing nothing, when the brief fails validation
(missing section, truncated lead, a score not taken from the pack, a
non-model record used as analysis, ...). Publishes nothing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from spec1_core.briefing.world_state import BriefValidationError, load, write_outputs

_CHROMIUM_NAMES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


def find_chromium() -> str | None:
    for name in _CHROMIUM_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None


def print_pdf(html_path: Path, pdf_path: Path, chromium: str | None = None) -> Path:
    """Print *html_path* to *pdf_path* with headless Chromium. Raises on failure."""
    exe = chromium or find_chromium()
    if exe is None:
        raise RuntimeError("no Chromium found for PDF printing; install chromium or pass --chromium")
    if pdf_path.exists():
        raise FileExistsError(f"{pdf_path} exists; briefs are never overwritten")
    result = subprocess.run(
        [exe, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"PDF print failed (exit {result.returncode}): "
                           f"{(result.stderr or result.stdout).strip()[-400:]}")
    return pdf_path


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spec1_core.tools.render_world_state_brief")
    p.add_argument("--spec", required=True)
    p.add_argument("--pack", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pdf", action="store_true", help="also print a PDF (off by default)")
    p.add_argument("--chromium", help="path to a Chromium/Chrome binary")
    p.add_argument("--check", action="store_true", help="validate only; write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    try:
        brief = load(Path(args.spec), Path(args.pack))
        if args.check:
            from spec1_core.briefing.world_state import render_markdown, render_print_html

            render_markdown(brief)
            render_print_html(brief)
            print("OK: brief passes validation")
            return 0
        paths = write_outputs(brief, Path(args.out_dir))
        if args.pdf:
            paths["pdf"] = print_pdf(paths["html"], paths["html"].with_suffix(".pdf"),
                                     args.chromium)
    except BriefValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (FileExistsError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
