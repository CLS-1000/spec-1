from __future__ import annotations


def has_attribution(text: str) -> bool:
    lowered = text.lower()
    return "according to" in lowered or "source:" in lowered
