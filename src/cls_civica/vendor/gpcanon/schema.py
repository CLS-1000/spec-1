"""gp-canon/1 sealed-zone schema (SCHEMA §3–4). Stdlib only.

validate_sealed(s) returns a list of (reason_code, detail); empty means valid.
"""
from __future__ import annotations

import re
from datetime import datetime

from .canon import CANON_VERSION

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")
HEX16 = re.compile(r"^[0-9a-f]{16}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")

KINDS = ("intent", "outcome", "failure", "seal", "finding")
DECISIONS = ("allow", "deny")
REASONS = ("policy_allowed", "policy_denied", "policy_unknown", "policy_raised",
           "policy_prefix_mismatch", "inputs_invalid")
RESULTS = ("ok", "raised", "skipped")
FAILURE_CODES = ("outcome_unwritten",)

COMMON = ("canon_version", "chain_id", "seq", "prev_hash", "kind", "recorded_at", "occurred_at")
GATED = ("gate_id", "actor", "detail")
FIELDS = {
    "intent": COMMON + GATED + ("policy_id", "subject", "action", "decision", "reason",
                                "policy_version", "policy_digest", "inputs_digest"),
    "outcome": COMMON + GATED + ("result",),
    "failure": COMMON + GATED + ("failure_code",),
    "seal": COMMON + ("key_id",),
    "finding": COMMON + ("actor", "subject", "finding_type", "claim", "evidence_digest", "detail"),
}
NULLABLE = {"detail", "policy_version", "policy_digest", "inputs_digest"}


def utc_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ts_ok(v) -> bool:
    if not isinstance(v, str) or not TS.match(v):
        return False
    try:
        datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%fZ")   # rejects Feb 30, second 60
        return True
    except ValueError:
        return False


def _nonempty(v) -> bool:
    return isinstance(v, str) and v != ""


FORMAT = {
    "canon_version": lambda v: v == CANON_VERSION,
    "chain_id": lambda v: isinstance(v, str) and bool(ID_RE.match(v)),
    "seq": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0,
    "prev_hash": lambda v: isinstance(v, str) and bool(HEX64.match(v)),
    "kind": lambda v: v in KINDS,
    "recorded_at": _ts_ok,
    "occurred_at": _ts_ok,
    "gate_id": lambda v: isinstance(v, str) and bool(HEX32.match(v)),
    "policy_id": lambda v: isinstance(v, str) and bool(ID_RE.match(v)),
    "finding_type": lambda v: isinstance(v, str) and bool(ID_RE.match(v)),
    "evidence_digest": lambda v: isinstance(v, str) and bool(DIGEST.match(v)),
    "claim": _nonempty,
    "policy_version": lambda v: isinstance(v, str) and bool(VERSION.match(v)),
    "policy_digest": lambda v: isinstance(v, str) and bool(DIGEST.match(v)),
    "inputs_digest": lambda v: isinstance(v, str) and bool(DIGEST.match(v)),
    "subject": _nonempty,
    "action": _nonempty,
    "actor": _nonempty,
    "detail": lambda v: isinstance(v, str),
    "decision": lambda v: v in DECISIONS,
    "reason": lambda v: v in REASONS,
    "result": lambda v: v in RESULTS,
    "failure_code": lambda v: v in FAILURE_CODES,
    "key_id": lambda v: isinstance(v, str) and bool(HEX16.match(v)),
}


def validate_sealed(s) -> list[tuple[str, str]]:
    """Every SCHEMA reason code that applies, as (code, detail); [] means valid.

    Error semantics match ref/gp_canon.py and the schema vectors: an absent kind is
    missing_field, an unknown kind is bad_field, and canon_version_unsupported is
    collected alongside other errors rather than stopping the check.
    """
    if not isinstance(s, dict):
        return [("bad_field", "sealed zone is not an object")]
    kind = s.get("kind")
    if kind not in KINDS:
        return [("bad_field", f"kind={kind!r}")] if "kind" in s else [("missing_field", "kind")]
    errs = []
    if "canon_version" in s and s["canon_version"] != CANON_VERSION:
        errs.append(("canon_version_unsupported", repr(s["canon_version"])))
    want = FIELDS[kind]
    for f in want:
        if f not in s:
            errs.append(("missing_field", f))
    for f in s:
        if f not in want:
            errs.append(("unknown_field", f))
    for f in want:
        if f not in s or f == "canon_version":
            continue
        v = s[f]
        if v is None:
            if f not in NULLABLE:
                errs.append(("null_not_allowed", f))
            continue
        if not FORMAT[f](v):
            errs.append(("bad_field", f"{f}={v!r}"[:120]))
    if errs:
        return errs
    if kind == "finding":
        if s["finding_type"].split(".")[0] != s["chain_id"].split(".")[0]:
            errs.append(("type_prefix_mismatch", f"{s['finding_type']} on {s['chain_id']}"))
        return errs
    if kind != "intent":
        return errs

    # SCHEMA §4 intent rules
    reason, decision = s["reason"], s["decision"]
    if (decision == "allow") != (reason == "policy_allowed"):
        errs.append(("decision_reason_mismatch", f"{decision}/{reason}"))
    no_policy = reason in ("policy_unknown", "policy_prefix_mismatch")
    for f in ("policy_version", "policy_digest"):
        if no_policy and s[f] is not None:
            errs.append(("null_required", f))
        if not no_policy and s[f] is None:
            errs.append(("null_not_allowed", f))
    if (reason == "inputs_invalid") != (s["inputs_digest"] is None):
        errs.append(("null_required" if reason == "inputs_invalid" else "null_not_allowed", "inputs_digest"))
    consumer = s["chain_id"].split(".")[0]
    same = s["policy_id"].split(".")[0] == consumer
    if same == (reason == "policy_prefix_mismatch"):
        errs.append(("policy_prefix_mismatch", f"{s['policy_id']} on {s['chain_id']}"))
    return errs
