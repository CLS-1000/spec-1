"""Neutrality gates for Metro Citizens Brief.

Every section must pass tone, attribution, and structural gates before publication.
"""

from cls_pdx1.neutrality.tone import tone_gate, LOADED_VERBS
from cls_pdx1.neutrality.attribution import attribution_gate
from cls_pdx1.neutrality.section import section_gate

__all__ = ["tone_gate", "attribution_gate", "section_gate", "LOADED_VERBS"]
