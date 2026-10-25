# @domain:   machine
# @module:   runs_index
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core

"""Read-only index of past cycle runs for the Triage Desk UI.

Nothing here writes, scores or gates. It reads what the cycle already wrote:

- cycle logs ``<run log dir>/cycle_*.log`` — the ``Run Summary:`` block the
  cycle prints, plus the ``[1/7] Harvesting`` feed list;
- structured run logs ``<run log dir>/*.json`` — any JSON object with a
  ``run_id`` (e.g. a PDX-1i run with per-adapter stats);
- the intelligence store (``SPEC1_STORE_PATH``) and its gate-decision log;
- brief provenance sidecars ``<briefs dir>/*.meta.json``.

Publish-guard status per run follows ``analysis_tier`` on the stored records:
``armed`` only when every record is ``llm_verified``; ``blocked`` when any
record has no tier (pre-migration-011) or an unknown one, or there are none;
otherwise ``triage`` (rule-based).
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from spec1_core.signal.gate_log import default_gate_log_path
from spec1_labels import ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED

RUN_LOG_DIR_ENV = "SPEC1_RUN_LOG_DIR"

GUARD_ARMED = "armed"
GUARD_TRIAGE = "triage"
GUARD_BLOCKED = "blocked"

# Gate letters shown in the desk, in the order the scorer evaluates them.
GATE_LETTERS = (("A", "credibility"), ("B", "volume"), ("C", "velocity"), ("D", "novelty"))

# Composite weights — mirrored from spec1_core.signal.scorer.score_signal for
# display only. The stored opportunity_score is what the desk reports as P.
COMPOSITE_WEIGHTS = {"credibility": 0.30, "volume": 0.20, "velocity": 0.20, "novelty": 0.30}

_SUMMARY_KEY = re.compile(r"^\s{2}([a-z_]+):\s?(.*)$")
_FEED_LINE = re.compile(r"^\s+-\s+([A-Za-z0-9_.\-]+):\s+\S+")


# ── paths ─────────────────────────────────────────────────────────────────────

def _store_path() -> Path:
    return Path(os.environ.get("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"))


def _run_log_dir() -> Path:
    return Path(os.environ.get(RUN_LOG_DIR_ENV, "logs"))


def _briefs_dir() -> Path:
    return Path(os.environ.get("SPEC1_BRIEFS_DIR", "briefs"))


# ── low-level readers ────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> Iterable[dict]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                yield obj


def _coerce(value: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return value


def parse_cycle_log(path: Path) -> Optional[dict]:
    """Return the ``Run Summary`` block of one cycle log as a dict, or None."""
    summary: dict[str, Any] = {}
    feeds: list[str] = []
    in_summary = False
    in_harvest = False
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if line.startswith("[1/7]"):
                    in_harvest = True
                    continue
                if in_harvest:
                    m = _FEED_LINE.match(line)
                    if m:
                        feeds.append(m.group(1))
                        continue
                    if line.strip():
                        in_harvest = False
                if line.startswith("Run Summary:"):
                    in_summary = True
                    continue
                if in_summary:
                    m = _SUMMARY_KEY.match(line)
                    if m:
                        summary[m.group(1)] = _coerce(m.group(2))
                    elif line.strip() and not line.startswith(" "):
                        in_summary = False
    except OSError:
        return None
    if not summary.get("run_id"):
        return None
    summary["feeds"] = feeds
    summary["log_file"] = path.name
    return summary


# ── run index ────────────────────────────────────────────────────────────────

@dataclass
class _Sources:
    runs: dict[str, dict]          # run_id → metadata from logs
    records: dict[str, list[dict]]  # run_id → stored intelligence records
    gates: dict[str, list[dict]]    # run_id → gate decisions
    metas: dict[str, dict]          # run_id → brief provenance sidecar


def _load_sources() -> _Sources:
    runs: dict[str, dict] = {}
    log_dir = _run_log_dir()
    if log_dir.is_dir():
        for path in sorted(log_dir.glob("cycle_*.log")):
            summary = parse_cycle_log(path)
            if summary:
                runs.setdefault(str(summary["run_id"]), {}).update(summary)
        for path in sorted(log_dir.glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(obj, dict) and obj.get("run_id"):
                obj = {**obj, "log_file": path.name}
                runs.setdefault(str(obj["run_id"]), {}).update(obj)

    records: dict[str, list[dict]] = {}
    store = _store_path()
    for rec in _read_jsonl(store):
        rid = rec.get("run_id")
        if rid:
            records.setdefault(str(rid), []).append(rec)

    gates: dict[str, list[dict]] = {}
    for dec in _read_jsonl(default_gate_log_path(store)):
        rid = dec.get("run_id")
        if rid:
            gates.setdefault(str(rid), []).append(dec)

    metas: dict[str, dict] = {}
    briefs = _briefs_dir()
    if briefs.is_dir():
        for path in sorted(briefs.glob("*.meta.json")):
            if path.name.startswith("spec1_brief_latest"):
                continue
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(obj, dict) and obj.get("run_id"):
                metas[str(obj["run_id"])] = {**obj, "meta_file": path.name}

    return _Sources(runs=runs, records=records, gates=gates, metas=metas)


def guard_status(records: list[dict]) -> dict:
    """Publish-guard state for one run's candidate records."""
    tiers = {ANALYSIS_TIER_LLM_VERIFIED: 0, ANALYSIS_TIER_RULE_BASED: 0, "unverified": 0}
    for rec in records:
        tier = rec.get("analysis_tier")
        if tier in (ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED):
            tiers[tier] += 1
        else:
            tiers["unverified"] += 1
    if not records:
        state, reason = GUARD_BLOCKED, "no candidate records"
    elif tiers["unverified"]:
        state, reason = GUARD_BLOCKED, (
            f"{tiers['unverified']} record(s) carry no analysis_tier (pre-011 or unknown)")
    elif tiers[ANALYSIS_TIER_RULE_BASED]:
        state, reason = GUARD_TRIAGE, (
            f"{tiers[ANALYSIS_TIER_RULE_BASED]} rule-based record(s); not publishable")
    else:
        state, reason = GUARD_ARMED, "all candidate records llm_verified"
    return {"state": state, "reason": reason, "tiers": tiers}


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_summary(run_id: str, src: _Sources) -> dict:
    meta = src.runs.get(run_id, {})
    records = src.records.get(run_id, [])
    gates = src.gates.get(run_id, [])
    written = _int(meta.get("records_stored"))
    started = meta.get("started_at") or (
        min((r.get("written_at") or "" for r in records), default="") or None)
    return {
        "run_id": run_id,
        "started_at": started,
        "finished_at": meta.get("finished_at"),
        "mode": meta.get("mode"),
        "harvested": _int(meta.get("signals_harvested", meta.get("harvested"))),
        "parsed": _int(meta.get("signals_parsed", meta.get("parsed"))),
        "written_opportunities": written if written is not None else len(records),
        "baseline_seeded": _int(meta.get("baseline_seeded")),
        "records_in_store": len(records),
        "gate_decisions_logged": len(gates),
        "guard": guard_status(records),
        "has_log": bool(meta),
    }


def list_runs(limit: int = 50) -> list[dict]:
    src = _load_sources()
    run_ids = set(src.runs) | set(src.records)
    summaries = [_run_summary(rid, src) for rid in run_ids]
    summaries.sort(key=lambda s: s["started_at"] or "", reverse=True)
    return summaries[:limit]


def _adapter_stats(run_id: str, src: _Sources) -> list[dict]:
    meta = src.runs.get(run_id, {})
    declared = meta.get("adapters")
    if isinstance(declared, list) and declared:
        out = []
        for a in declared:
            if isinstance(a, dict) and a.get("name"):
                out.append({
                    "name": str(a["name"]),
                    "parsed": _int(a.get("parsed")),
                    "passed": _int(a.get("passed")),
                    "blocked": _int(a.get("blocked")),
                    "status": str(a.get("status") or ("error" if a.get("errors") else "ok")),
                })
        return out

    counts: dict[str, dict] = {}
    for name in meta.get("feeds") or []:
        counts.setdefault(name, {"name": name, "parsed": 0, "passed": 0, "blocked": 0})
    for dec in src.gates.get(run_id, []):
        row = counts.setdefault(str(dec.get("source")),
                                {"name": str(dec.get("source")), "parsed": 0, "passed": 0, "blocked": 0})
        row["parsed"] += 1
        row["passed" if dec.get("decision") == "passed" else "blocked"] += 1
    if not src.gates.get(run_id):
        for rec in src.records.get(run_id, []):
            name = str(rec.get("signal_source"))
            row = counts.setdefault(name, {"name": name, "parsed": 0, "passed": 0, "blocked": 0})
            row["passed"] += 1
        for row in counts.values():
            row["parsed"] = None
            row["blocked"] = None
    errors = [str(e) for e in (meta.get("errors") or [])]
    for row in counts.values():
        failed = any(f":{row['name']}:" in e for e in errors)
        if failed:
            row["status"] = "error"
        elif row["passed"]:
            row["status"] = "yield"
        elif row["parsed"] == 0 and src.gates.get(run_id):
            row["status"] = "quiet"
        else:
            row["status"] = "ok"
    return sorted(counts.values(), key=lambda r: (-(r["passed"] or 0), r["name"]))


def _funnel(run_id: str, summary: dict, src: _Sources) -> list[dict]:
    meta = src.runs.get(run_id, {})
    gates = src.gates.get(run_id, [])
    passed = sum(1 for d in gates if d.get("decision") == "passed") if gates else None
    blocked = (len(gates) - passed) if gates else None
    opp = _int(meta.get("opportunities_found"))
    return [
        {"key": "ingest", "label": "Ingest", "count": summary["harvested"]},
        {"key": "normalize", "label": "Normalize", "count": summary["parsed"]},
        {"key": "rule_gates", "label": "Rule Gates", "count": passed if passed is not None else opp,
         "blocked": blocked},
        {"key": "scoring", "label": "Scoring", "count": opp},
        {"key": "graph_dedupe", "label": "Graph Dedupe",
         "count": _int(meta.get("signals_skipped_seen")), "note": "skipped as already seen"},
        {"key": "handoff", "label": "Handoff",
         "count": _int(meta.get("outcomes_verified")),
         "note": "handoff written" if meta.get("handoff_path") else None},
        {"key": "audit_store", "label": "Audit Store", "count": summary["written_opportunities"]},
    ]


def get_run(run_id: str) -> Optional[dict]:
    src = _load_sources()
    if run_id not in src.runs and run_id not in src.records:
        return None
    summary = _run_summary(run_id, src)
    meta = src.runs.get(run_id, {})
    return {
        **summary,
        "adapters": _adapter_stats(run_id, src),
        "funnel": _funnel(run_id, summary, src),
        "errors": [str(e) for e in (meta.get("errors") or [])][:50],
        "log_file": meta.get("log_file"),
        "brief_meta": src.metas.get(run_id),
    }


# ── records ──────────────────────────────────────────────────────────────────

def _is_tier1(rec: dict) -> bool:
    if str(rec.get("anomaly_tier") or "").upper() == "TIER_1":
        return True
    for key in ("sigma", "anomaly_sigma"):
        try:
            if float(rec.get(key)) >= 3.0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _shape_record(rec: dict, decision: Optional[dict], brief_meta: Optional[dict]) -> dict:
    gate_values = (decision or {}).get("gates") or {}
    gate_results = rec.get("gate_results") or {}
    gates = []
    for letter, name in GATE_LETTERS:
        g = gate_values.get(name) or {}
        passed = g.get("passed", gate_results.get(name))
        gates.append({
            "gate": letter,
            "name": name,
            "value": g.get("value"),
            "threshold": g.get("threshold"),
            "passed": passed,
        })
    credibility = (gate_values.get("credibility") or {}).get("value", rec.get("source_weight"))
    volume = (gate_values.get("volume") or {}).get("value")
    velocity = (gate_values.get("velocity") or {}).get("value")
    novelty = (gate_values.get("novelty") or {}).get("score")
    if all(g["passed"] is True for g in gates):
        gate_status = "pass"
    elif any(g["passed"] is False for g in gates):
        gate_status = "fail"
    else:
        gate_status = "unknown"
    return {
        "record_id": rec.get("record_id"),
        "source": rec.get("signal_source"),
        "url": rec.get("signal_url"),
        "composite": rec.get("opportunity_score"),
        "priority": rec.get("opportunity_priority"),
        "analysis_tier": rec.get("analysis_tier"),
        "classification": rec.get("outcome_classification") or rec.get("classification"),
        "confidence": rec.get("confidence"),
        "gate_status": gate_status,
        "tier1": _is_tier1(rec),
        "scoring": {
            "credibility": credibility,
            "volume": volume,
            "velocity": velocity,
            "novelty": novelty,
            "composite": rec.get("opportunity_score"),
            "weights": COMPOSITE_WEIGHTS,
        },
        "gates": gates,
        "gate_decision": decision,
        "written_at": rec.get("written_at"),
        "raw": rec,
        "provenance": brief_meta,
    }


def get_records(
    run_id: str,
    *,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    gate_status: Optional[str] = None,
    min_weight: Optional[float] = None,
    tier1_only: bool = False,
    limit: int = 500,
) -> Optional[list[dict]]:
    src = _load_sources()
    if run_id not in src.runs and run_id not in src.records:
        return None
    by_signal = {d.get("signal_id"): d for d in src.gates.get(run_id, [])}
    meta = src.metas.get(run_id)
    out = []
    for rec in src.records.get(run_id, []):
        row = _shape_record(rec, by_signal.get(rec.get("signal_id")), meta)
        if tier:
            want = None if tier == "unverified" else tier
            if row["analysis_tier"] != want and not (
                    tier == "unverified" and row["analysis_tier"] not in
                    (ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED)):
                continue
        if source and row["source"] != source:
            continue
        if gate_status and row["gate_status"] != gate_status:
            continue
        if min_weight is not None and (row["composite"] or 0.0) < min_weight:
            continue
        if tier1_only and not row["tier1"]:
            continue
        out.append(row)
    out.sort(key=lambda r: (not r["tier1"], -(r["composite"] or 0.0)))
    return out[:limit]
