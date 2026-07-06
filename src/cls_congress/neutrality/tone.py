from __future__ import annotations


def neutral_tone(text: str) -> bool:
    banned = {"corrupt", "obviously", "clearly"}
    lowered = text.lower()
    return not any(term in lowered for term in banned)
