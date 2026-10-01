# @domain:   citizens_source
# @module:   neutrality_tone
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Tone gate: reject loaded or editorialising vocabulary."""

from __future__ import annotations

import re
from typing import Optional

# Verbs/phrases that imply editorial characterisation; banned from publication copy.
LOADED_VERBS: frozenset[str] = frozenset(
    {
        "admitted",
        "claimed",
        "alleged",
        "denied",
        "slammed",
        "blasted",
        "accused",
        "lied",
        "misled",
        "deceived",
        "covered up",
        "doubled down",
        "backpedalled",
        "backpedaled",
        "caved",
        "capitulated",
        "attacked",
        "defended",
        "lambasted",
        "excoriated",
    }
)

# Neutral verbs that are always allowed replacements.
NEUTRAL_VERBS: frozenset[str] = frozenset(
    {"said", "stated", "wrote", "proposed", "voted", "responded", "noted", "added"}
)

_WORD_RE = re.compile(r"\b(\w[\w\s]*?\w|\w)\b", re.IGNORECASE)


def _words_in(text: str) -> list[str]:
    return [m.group().lower() for m in _WORD_RE.finditer(text)]


def tone_gate(text: str) -> tuple[bool, Optional[str]]:
    """Return (ok, reason). Fails if loaded vocabulary found in text."""
    words = _words_in(text)
    found = [w for w in words if w in LOADED_VERBS]
    if found:
        return False, f"TONE_001: loaded vocabulary detected: {found[:5]}"
    return True, None
