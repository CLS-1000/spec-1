"""Neutrality gates for Metro Citizens Narrative.

Every section must pass tone, attribution, and structural gates before publication.
"""

from titan.neutrality.tone import tone_gate, LOADED_VERBS
from titan.neutrality.attribution import attribution_gate
from titan.neutrality.section import section_gate

__all__ = ["tone_gate", "attribution_gate", "section_gate", "LOADED_VERBS"]
