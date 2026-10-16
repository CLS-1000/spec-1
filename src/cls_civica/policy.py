# @domain:   civica
# @module:   civica_policy
# @status:   mvp

"""Publication gate for one measure card (Gatepost policy `civica.publish_card`).

This file IS the policy: Gatepost hashes it into every intent's policy_digest,
so `bin/verify.py --policy civica.publish_card=<this file>` proves which rules
each published card was checked against. Change it and the digest changes.

What the gate checks (DESIGN_INTENT §4 — accountability, not tone):
  1. The card makes at least one claim, and every claim is non-empty.
  2. Every claim cites official action rows, and every cited row is in the
     sealed evidence for this card. No unsourced sentence reaches the page.
  3. The card's source is the official Oregon Legislature API.
  4. A history proc_track could not verify is labelled "Not verified" and says
     why; it is never presented as verified.
  5. The evidence was recorded on the chain before the decision (digest present).

The gate does not check tone, register or whether the result is uncomfortable.
"""

from __future__ import annotations

POLICY_VERSION = "1"
OLIS_PREFIX = "https://api.oregonlegislature.gov/odata/odataservice.svc/"


def decide(inputs) -> tuple[bool, str | None]:
    card = inputs["card"]
    evidence_rows = set(inputs["source_row_ids"])
    digest = inputs.get("evidence_digest") or ""

    if not digest.startswith("sha256:"):
        return False, "evidence not recorded before decision"
    if not str(card.get("source_url", "")).startswith(OLIS_PREFIX):
        return False, "source is not the official Oregon Legislature API"
    claims = card.get("claims") or []
    if not claims:
        return False, "card makes no claims"
    for i, c in enumerate(claims):
        if not str(c.get("text", "")).strip():
            return False, f"claim {i} is empty"
        cited = c.get("row_ids") or []
        if not cited:
            return False, f"claim {i} is unsourced"
        missing = [r for r in cited if r not in evidence_rows]
        if missing:
            return False, f"claim {i} cites rows not in evidence: {missing[:3]}"
    if not card.get("verified"):
        if not card.get("halt_reason"):
            return False, "unverified history without a stated reason"
        if card.get("outcome") != "unverified":
            return False, "unverified history presented with a verified outcome"
    return True, f"{len(claims)} sourced claims"
