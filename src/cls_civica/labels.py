# @domain:   civica
# @module:   civica_labels
# @status:   mvp

"""Canonical strings for cls_civica. Import from here; do not hard-code."""

from __future__ import annotations

# Gatepost chain / policy ids (consumer prefix must be "civica").
CHAIN_ID = "civica.publish"
POLICY_PUBLISH_CARD = "civica.publish_card"
FINDING_MEASURE_CARD = "civica.measure_card"
FINDING_SESSION_SUMMARY = "civica.session_summary"
ACTION_PUBLISH = "publish"

# The operator's published signing key (Notitia Civica, evidence/OPERATOR_KEY.md).
# A real build must be sealed by this key; recipients pin it from that page, never from a site.
PUBLISHED_KEY_ID = "f7b1282a4a9ccf50"
PUBLISHED_PUBKEY_HEX = "c7dbbf86b2e014fad70190276f4e20969743d2fa2bc7c13e48c95fdd91a7d0ad"
PUBLISHED_KEY_SOURCE = "https://github.com/ominous-22/notitia-civica/blob/main/evidence/OPERATOR_KEY.md"

OLIS_API ="https://api.oregonlegislature.gov/odata/odataservice.svc"
OLIS_HOST_PREFIX = OLIS_API + "/"
OLIS_PUBLIC_PAGE = "https://olis.oregonlegislature.gov/liz/{session}/Measures/Overview/{prefix}{number}"

# Outcome buckets a resident sees.
OUTCOME_LAW = "law"
OUTCOME_VETOED = "vetoed"
OUTCOME_ADOPTED = "adopted"
OUTCOME_PASSED = "passed_legislature"
OUTCOME_FAILED = "failed"
OUTCOME_STOPPED = "stopped"
OUTCOME_HALTED = "unverified"

OUTCOME_LABELS = {
    OUTCOME_LAW: "Became law",
    OUTCOME_VETOED: "Vetoed",
    OUTCOME_ADOPTED: "Adopted",
    OUTCOME_PASSED: "Passed the Legislature",
    OUTCOME_FAILED: "Voted down",
    OUTCOME_STOPPED: "Did not pass",
    OUTCOME_HALTED: "Not verified",
}

# Topics.
TOPIC_BALLOT = "ballot"          # would go to voters if passed (constitutional amendments, referrals)
TOPIC_ELECTIONS = "elections"    # election administration / voting (needs measure titles: live mode)
TOPIC_VETO = "veto"

TOPIC_LABELS = {
    TOPIC_BALLOT: "Could reach your ballot",
    TOPIC_ELECTIONS: "Elections & voting",
    TOPIC_VETO: "Governor's veto",
}

# Measure prefixes.
JOINT_RESOLUTIONS = {"HJR", "SJR"}           # proposed constitutional amendments -> voters
NON_GOVERNOR_MEASURES = {"HCR", "SCR", "HJM", "SJM", "HR", "SR", "HJR", "SJR"}

CHAMBER_NAMES = {"H": "House", "S": "Senate"}
PRESIDING_OFFICER = {"H": "House Speaker", "S": "Senate President"}
