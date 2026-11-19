"""Terminal banner and status glyph for SPEC-1.

Part of the shared CLS-1000 TUI mark: the four-gate block (U+259A) plus the
project name. Stdlib only. Nothing imports this yet; call it from a CLI entry
point when you want it.

    python -m spec1_core.tui_banner

Rules it follows on its own:
- NO_COLOR set, or output is not a terminal -> no ANSI codes.
- Terminal narrower than the banner -> the one-line status form.
- Output encoding can't draw block characters -> plain ASCII fallback.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import TextIO

NAME = 'SPEC-1'
SUBTITLE = 'SPEC-1 RESEARCH ENGINE'

# Four-gate block: one cell, upper-left + lower-right quadrants.
GLYPH = "\u259a"
GLYPH_ASCII = "#"

BANNER = """\
███████╗██████╗ ███████╗ ██████╗  ██╗
██╔════╝██╔══██╗██╔════╝██╔════╝ ███║
███████╗██████╔╝█████╗  ██║█████╗╚██║
╚════██║██╔═══╝ ██╔══╝  ██║╚════╝ ██║
███████║██║     ███████╗╚██████╗  ██║
╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚═╝"""

BANNER_WIDTH = max(len(line) for line in BANNER.splitlines())

_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _use_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def _can_draw_blocks(stream: TextIO) -> bool:
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        (GLYPH + "\u2588\u2557").encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def status(stream: TextIO | None = None) -> str:
    """One-line form for a status bar or prompt, e.g. '\u259a SPEC-1'."""
    stream = stream or sys.stdout
    glyph = GLYPH if _can_draw_blocks(stream) else GLYPH_ASCII
    return f"{glyph} {NAME}"


def banner(stream: TextIO | None = None, width: int | None = None) -> str:
    """Full boot banner, falling back to the status line when it won't fit."""
    stream = stream or sys.stdout
    if width is None:
        width = shutil.get_terminal_size((80, 24)).columns
    color = _use_color(stream)

    if width < BANNER_WIDTH or not _can_draw_blocks(stream):
        line = f"{status(stream)}  {SUBTITLE}"
        return f"{_BOLD}{line}{_RESET}" if color else line

    sub = f"{SUBTITLE} \u2588"
    if color:
        return f"{_BOLD}{BANNER}{_RESET}\n{_DIM}{sub}{_RESET}"
    return f"{BANNER}\n{sub}"


def print_banner(stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    print(banner(stream), file=stream)


if __name__ == "__main__":
    print_banner()
    print()
    print(status())
