# @domain:   citizens_source
# @module:   neutrality_section
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Section-level composite neutrality gate."""

from __future__ import annotations


from cls_pdx1.neutrality.attribution import attribution_gate
from cls_pdx1.neutrality.tone import tone_gate


def section_gate(title: str, body: str, source_uri: str) -> tuple[bool, list[str]]:
    """Run tone + attribution gates on a section. Return (ok, failures)."""
    failures: list[str] = []

    ok, reason = tone_gate(title + " " + body)
    if not ok and reason:
        failures.append(reason)

    ok, reason = attribution_gate(body, source_uri)
    if not ok and reason:
        failures.append(reason)

    return len(failures) == 0, failures
