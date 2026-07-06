# @domain:   machine
# @module:   spec1_labels
# @loc:      _SCRATCH
# @status:   drafting
# @depends:  NONE

"""Canonical label constants for SPEC-1.

All enum-like string values used across packages are defined here.
Every module should import from this file rather than hard-coding strings.
"""

# ── Source types ──────────────────────────────────────────────────────────────
SOURCE_RSS           = "RSS"
SOURCE_FARA          = "FARA"
SOURCE_CONGRESSIONAL = "CONGRESSIONAL"
SOURCE_NARRATIVE     = "NARRATIVE"

# ── Congressional record types ────────────────────────────────────────────────
RECORD_BILL       = "BILL"
RECORD_RESOLUTION = "RESOLUTION"
RECORD_HEARING    = "HEARING"
RECORD_AMENDMENT  = "AMENDMENT"

# ── Chamber ───────────────────────────────────────────────────────────────────
CHAMBER_HOUSE   = "HOUSE"
CHAMBER_SENATE  = "SENATE"
CHAMBER_UNKNOWN = "UNKNOWN"

# ── FARA registration status ──────────────────────────────────────────────────
FARA_STATUS_ACTIVE     = "ACTIVE"
FARA_STATUS_TERMINATED = "TERMINATED"

# ── Congressional bill status ─────────────────────────────────────────────────
CONGRESS_STATUS_INTRODUCED    = "INTRODUCED"
CONGRESS_STATUS_PASSED_HOUSE  = "PASSED_HOUSE"
CONGRESS_STATUS_PASSED_SENATE = "PASSED_SENATE"
CONGRESS_STATUS_ENACTED       = "ENACTED"
CONGRESS_STATUS_FAILED        = "FAILED"

# ── Narrative sentiment ───────────────────────────────────────────────────────
SENTIMENT_POSITIVE = "POSITIVE"
SENTIMENT_NEGATIVE = "NEGATIVE"
SENTIMENT_NEUTRAL  = "NEUTRAL"
SENTIMENT_MIXED    = "MIXED"

# ── Operator structured-output verdict ───────────────────────────────────────
OPERATOR_VERDICT_ESCALATE = "ESCALATE"
OPERATOR_VERDICT_ARCHIVE  = "ARCHIVE"
OPERATOR_VERDICT_HOLD     = "HOLD"

# ── Investigation outcome classification ──────────────────────────────────────
OUTCOME_CORROBORATED = "CORROBORATED"
OUTCOME_ESCALATE     = "ESCALATE"
OUTCOME_INVESTIGATE  = "INVESTIGATE"
OUTCOME_MONITOR      = "MONITOR"
OUTCOME_CONFLICTED   = "CONFLICTED"
OUTCOME_ARCHIVE      = "ARCHIVE"

# ── Cross-source verification classification ──────────────────────────────────
VERIF_CORROBORATED = "CORROBORATED"
VERIF_PARTIAL      = "PARTIAL"
VERIF_UNVERIFIED   = "UNVERIFIED"
VERIF_CONFLICTED   = "CONFLICTED"

# ── Psyop risk classification ─────────────────────────────────────────────────
PSYOP_HIGH_RISK   = "HIGH_RISK"
PSYOP_MEDIUM_RISK = "MEDIUM_RISK"
PSYOP_LOW_RISK    = "LOW_RISK"
PSYOP_CLEAN       = "CLEAN"

# ── Psyop pattern threat level ────────────────────────────────────────────────
THREAT_HIGH   = "HIGH"
THREAT_MEDIUM = "MEDIUM"
THREAT_LOW    = "LOW"

# ── Lead priority ─────────────────────────────────────────────────────────────
PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_HIGH     = "HIGH"
PRIORITY_MEDIUM   = "MEDIUM"
PRIORITY_LOW      = "LOW"

# ── Lead category ─────────────────────────────────────────────────────────────
CATEGORY_MILITARY     = "MILITARY"
CATEGORY_CYBER        = "CYBER"
CATEGORY_GEOPOLITICAL = "GEOPOLITICAL"
CATEGORY_FARA         = "FARA"
CATEGORY_PSYOP        = "PSYOP"
CATEGORY_QUANT        = "QUANT"

# ── Legislative & Judicial Desk — source types ────────────────────────────────
SOURCE_JUDICIAL  = "JUDICIAL"
SOURCE_STATE_LEG = "STATE_LEG"

# ── Legislative & Judicial Desk — domain prefixes ─────────────────────────────
DOMAIN_CONGRESS_VOTE       = "congress.vote"
DOMAIN_CONGRESS_HEARING    = "congress.hearing"
DOMAIN_CONGRESS_SPONSOR    = "congress.sponsor"
DOMAIN_FARA_FILING         = "fara.filing"
DOMAIN_LDA_FILING          = "lda.filing"
DOMAIN_JUDICIAL_RULING     = "judicial.ruling"
DOMAIN_JUDICIAL_RECUSAL    = "judicial.recusal"
DOMAIN_JUDICIAL_DISCLOSURE = "judicial.disclosure"
DOMAIN_JUDICIAL_GIFT       = "judicial.gift"
DOMAIN_JUDICIAL_ENGAGEMENT = "judicial.speaking_engagement"
DOMAIN_STATE_LEG_BILL      = "state_leg.bill"
DOMAIN_STATE_LEG_VOTE      = "state_leg.vote"

# ── Disclosure regime ─────────────────────────────────────────────────────────
DISCLOSURE_FULL       = "FULL"
DISCLOSURE_PARTIAL    = "PARTIAL"
DISCLOSURE_NONE       = "NONE"
DISCLOSURE_GAP_MARKER = "DISCLOSURE GAP"

# ── Research Mode — dossier status ────────────────────────────────────────────
RESEARCH_STATUS_DRAFT     = "DRAFT"
RESEARCH_STATUS_FINAL     = "FINAL"
RESEARCH_GAP_MARKER       = "COLLECTION GAP"

# ── Research Mode — expansion rule tags ───────────────────────────────────────
EXPANSION_RULE_KEYWORD            = "keyword"
EXPANSION_RULE_ENTITY             = "entity"
EXPANSION_RULE_ALIAS              = "alias"
EXPANSION_RULE_SUBQUESTION        = "subquestion"
EXPANSION_RULE_KEYWORD_X_ENTITY   = "keyword_x_entity"
EXPANSION_RULE_KEYWORD_X_GEO      = "keyword_x_geography"
EXPANSION_RULE_ENTITY_X_GEO       = "entity_x_geography"

# ── Founder Brain — pattern categories ────────────────────────────────────────
FOUNDER_PATTERN_FAILURE      = "FAILURE"
FOUNDER_PATTERN_SUCCESS      = "SUCCESS"
FOUNDER_PATTERN_PIVOT        = "PIVOT"
FOUNDER_PATTERN_EXIT_SIGNAL  = "EXIT_SIGNAL"

# ── Founder Brain — conviction levels ─────────────────────────────────────────
FOUNDER_CONVICTION_HIGH   = "HIGH"
FOUNDER_CONVICTION_MEDIUM = "MEDIUM"
FOUNDER_CONVICTION_LOW    = "LOW"
FOUNDER_CONVICTION_NOISE  = "NOISE"

# ── Founder Brain — fire triage classifications ───────────────────────────────
FOUNDER_FIRE_IGNORE   = "IGNORE"
FOUNDER_FIRE_DELEGATE = "DELEGATE"
FOUNDER_FIRE_ATTACK   = "ATTACK"

# ── Type aliases ──────────────────────────────────────────────────────────────
from typing import Literal  # noqa: E402

PriorityT      = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
ThreatLevelT   = Literal["HIGH", "MEDIUM", "LOW"]
PsyopRiskT     = Literal["HIGH_RISK", "MEDIUM_RISK", "LOW_RISK", "CLEAN"]
VerificationT  = Literal["CORROBORATED", "PARTIAL", "UNVERIFIED", "CONFLICTED"]
ResearchStatusT = Literal["DRAFT", "FINAL"]
FounderConvictionT = Literal["HIGH", "MEDIUM", "LOW", "NOISE"]
FounderFireT       = Literal["IGNORE", "DELEGATE", "ATTACK"]
FounderPatternT    = Literal["FAILURE", "SUCCESS", "PIVOT", "EXIT_SIGNAL"]


def is_valid_priority(value: str) -> bool:
    return value in {PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW}


def is_valid_threat_level(value: str) -> bool:
    return value in {THREAT_HIGH, THREAT_MEDIUM, THREAT_LOW}


def is_valid_psyop_risk(value: str) -> bool:
    return value in {PSYOP_HIGH_RISK, PSYOP_MEDIUM_RISK, PSYOP_LOW_RISK, PSYOP_CLEAN}


def is_valid_verification(value: str) -> bool:
    return value in {VERIF_CORROBORATED, VERIF_PARTIAL, VERIF_UNVERIFIED, VERIF_CONFLICTED}


def is_valid_research_status(value: str) -> bool:
    return value in {RESEARCH_STATUS_DRAFT, RESEARCH_STATUS_FINAL}
