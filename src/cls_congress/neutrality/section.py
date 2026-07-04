from __future__ import annotations

from cls_congress.neutrality.attribution import has_attribution
from cls_congress.neutrality.tone import neutral_tone


def section_is_publishable(text: str) -> bool:
    return neutral_tone(text) and has_attribution(text)
