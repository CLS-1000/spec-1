# @domain:   publisher
# @module:   app_legislative_desk
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core/app/cycle, cls_leg_jud/bridge

"""Legislative & Judicial Desk cycle — ``python -m spec1_core.app.cycle --desk legislative``.

  OLIS measures + interim committees + state bills (cls_leg_jud.bridge)
    → parse → Opportunity (4 gates evaluated and recorded, NOT enforced)
    → investigation → verify (local-first model, or Tier 3 with --triage-only)
    → analyze → spec1_legislative.jsonl + SQLite intelligence_records
    → generate_brief(mode="legislative") → briefs/spec1_legislative_<date>.md (+ .meta.json)
    → cls_leg_jud.produce_brief → leg_jud_briefs.jsonl (rule-based desk view, /api/v1/leg-jud)

Legislative records rarely clear the RSS gates (OLIS is not a weighted source
and bill actions are not 72-hour news), so the bridge's recency window and
cap take their place. Priority comes from the bill's status. The gate values
are still stored so calibration can see what the gates would have said.

The publish guard is unchanged: a brief is publishable only if every record
behind it is ``llm_verified``; triage-only runs write no brief.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cls_leg_jud.bridge import DEFAULT_LIMIT, DEFAULT_SINCE_DAYS, collect_candidates
from spec1_core.app.cycle import build_record_dict, make_store
from spec1_core.core.logging_utils import get_logger
from spec1_core.intelligence.analyzer import analyze
from spec1_core.intelligence.store import JsonlStore
from spec1_core.investigation.generator import generate_investigation
from spec1_core.investigation.verifier import verify_investigation
from spec1_core.schemas.models import Opportunity
from spec1_core.signal.parser import parse_signal
from spec1_core.signal.scorer import composite_score, evaluate_gates
from spec1_labels import ANALYSIS_TIER_LLM_VERIFIED, ANALYSIS_TIER_RULE_BASED

logger = get_logger(__name__)

BRIEF_PREFIX = "spec1_legislative"
BRIEF_MODE = "legislative"


def _opportunity(sig, ps, run_id: str) -> Opportunity:
    """Opportunity with the gates evaluated for the record but not enforced."""
    ev = evaluate_gates(sig, ps)
    gate_results = {name: gate["passed"] for name, gate in ev["gates"].items()}
    gate_results["bypassed"] = True
    return Opportunity(
        opportunity_id=f"opp-{sig.signal_id}",
        signal_id=sig.signal_id,
        score=composite_score(ev),
        priority=sig.metadata.get("priority", "STANDARD"),
        gate_results=gate_results,
        run_id=run_id,
    )


def _desk_fields(sig, record_dict: dict) -> dict:
    """Fields cls_leg_jud.producer reads, kept on the stored record."""
    meta = sig.metadata
    return {
        "desk": BRIEF_MODE,
        "domain": meta.get("domain", ""),
        "composite_confidence": record_dict.get("confidence", 0.0),
        "title": meta.get("title", ""),
        "summary": " ".join(sig.text.split())[:400],
        "published_at": sig.published_at.isoformat(),
        "metadata": {k: v for k, v in meta.items() if k != "priority"},
    }


def run_legislative_desk(
    *,
    store_path: Path,
    run_id: str,
    environment: str = "production",
    max_signals: Optional[int] = None,
    verbose: bool = True,
    skip_seen: bool = True,
    triage_only: bool = False,
    since_days: Optional[int] = None,
    collect=collect_candidates,
) -> dict:
    """Run one legislative desk cycle and return its stats dict. Never raises on source failure."""
    since_days = since_days or DEFAULT_SINCE_DAYS
    limit = max_signals or DEFAULT_LIMIT
    store = make_store(store_path)
    started_at = datetime.now(timezone.utc).isoformat()

    if verbose:
        print(f"\n{'='*60}")
        print("  SPEC-1 Legislative & Judicial Desk — Cycle Start")
        print(f"  run_id    : {run_id}")
        print(f"  store     : {store_path}")
        print(f"  window    : last {since_days} days (+ upcoming hearings), cap {limit}")
        print(f"  mode      : {'triage-only (no model)' if triage_only else 'full'}")
        print(f"{'='*60}\n")

    stats: dict = {
        "run_id": run_id,
        "started_at": started_at,
        "desk": BRIEF_MODE,
        "mode": "triage_only" if triage_only else "full",
        "signals_harvested": 0,
        "signals_parsed": 0,
        "opportunities_found": 0,
        "investigations_generated": 0,
        "outcomes_verified": 0,
        "records_stored": 0,
        "signals_skipped_seen": 0,
        "analysis_tiers": {ANALYSIS_TIER_LLM_VERIFIED: 0, ANALYSIS_TIER_RULE_BASED: 0},
        "errors": [],
    }

    # ── Candidates ────────────────────────────────────────────────────────────
    seen: set[str] = set()
    if skip_seen:
        try:
            seen = JsonlStore(store_path).signal_ids()
        except Exception as exc:
            # Fail closed, as the standard desk does: without `seen` every item is re-stored.
            stats["errors"].append(f"dedup:{exc}")
            stats["finished_at"] = datetime.now(timezone.utc).isoformat()
            if verbose:
                print(f"[ERROR] Could not read stored signal IDs — nothing processed: {exc}")
            return stats

    if verbose:
        print("[1/6] Collecting OLIS measures, interim committees and state bills...")
    signals, report = collect(run_id=run_id, environment=environment,
                              since_days=since_days, limit=limit, seen_ids=seen)
    stats["candidate_report"] = report
    stats["signals_harvested"] = len(signals)
    stats["signals_skipped_seen"] = report["counts"].get("dropped_seen", 0)
    stats["errors"].extend(f"legislative:{e}" for e in report["errors"])
    if verbose:
        print(f"      Sources: {report['per_source']}")
        print(f"      Dropped: {report['counts']}")
        print(f"      Candidates this run: {len(signals)}")
        for e in report["errors"]:
            print(f"      [WARN] {e}")

    # ── Parse → Investigate → Verify → Analyze → Store ───────────────────────
    if verbose:
        print("\n[2/6] Parsing · [3/6] Investigating · [4/6] Verifying · [5/6] Analyzing · "
              f"[6/6] Writing to {store_path}\n")
    stored_records: list[dict] = []
    for sig in signals:
        try:
            ps = parse_signal(sig)
            stats["signals_parsed"] += 1
            opp = _opportunity(sig, ps, run_id)
            stats["opportunities_found"] += 1
            inv = generate_investigation(opp, sig, ps)
            stats["investigations_generated"] += 1
            outcome = verify_investigation(
                inv, article=ps.cleaned_text, source=sig.source, use_llm=not triage_only)
            stats["outcomes_verified"] += 1
            record = analyze(opp, inv, outcome, sig)
            record_dict = build_record_dict(
                record, sig=sig, ps=ps, opp=opp, inv=inv, outcome=outcome,
                run_id=run_id, environment=environment)
            record_dict.update(_desk_fields(sig, record_dict))
            store.append(record_dict)
            stored_records.append(record_dict)
            stats["analysis_tiers"][outcome.analysis_tier] = (
                stats["analysis_tiers"].get(outcome.analysis_tier, 0) + 1)
            if verbose:
                print(f"  [{len(stored_records):03d}] [{opp.priority:8s}] "
                      f"class={outcome.classification:14s} conf={outcome.confidence:.2f} "
                      f"tier={outcome.analysis_tier} {sig.metadata.get('domain')} "
                      f"{sig.metadata.get('bill', '')[:40]}")
        except Exception as exc:
            stats["errors"].append(f"pipeline:{sig.signal_id}:{exc}")
            if verbose:
                print(f"  [ERR] {sig.signal_id}: {exc}")

    stats["records_stored"] = len(stored_records)
    stats["finished_at"] = datetime.now(timezone.utc).isoformat()
    stats["records_tier"] = (
        ANALYSIS_TIER_LLM_VERIFIED
        if stored_records and stats["analysis_tiers"].get(ANALYSIS_TIER_RULE_BASED, 0) == 0
        else ANALYSIS_TIER_RULE_BASED
    )

    if triage_only:
        if verbose:
            print(f"\n[Triage-only] {len(stored_records)} record(s) stored, all rule_based. "
                  "No brief in this mode.")
        return stats

    # ── Model brief (local-first) ─────────────────────────────────────────────
    if stored_records:
        _write_model_brief(stored_records, stats, verbose)
    elif verbose:
        print("\n[Briefing] No new legislative records — no brief written.")

    # ── Rule-based desk view ──────────────────────────────────────────────────
    try:
        from cls_leg_jud import LegJudStore, produce_brief
        leg_store = LegJudStore(Path(os.environ.get("SPEC1_LEG_JUD_PATH", "leg_jud_briefs.jsonl")))
        leg_store.save(produce_brief(stored_records, run_id=run_id))
        stats["leg_jud_store_path"] = str(leg_store.path)
    except Exception as exc:
        logger.error("Leg-Jud desk view failed: %s", exc)
        stats["errors"].append(f"leg_jud:{exc}")

    if verbose:
        print(f"\n{'='*60}\n  Legislative Desk Complete\n  Records stored : {len(stored_records)}"
              f"\n  Records tier   : {stats['records_tier']}"
              f"\n  Errors         : {len(stats['errors'])}\n{'='*60}\n")
    return stats


def _write_model_brief(records: list[dict], stats: dict, verbose: bool) -> None:
    """generate_brief(mode="legislative") → own files + provenance sidecar. Never raises."""
    try:
        from spec1_core.briefing.generator import generate_brief
        from spec1_core.briefing.writer import write_brief, write_brief_meta
        from spec1_labels import BRIEF_SOURCE_MODEL, BRIEF_SOURCE_RULES

        if verbose:
            print("\n[Briefing] Generating legislative brief...")
        brief_md, prompts = generate_brief(records, stats, mode=BRIEF_MODE)
        brief_path = write_brief(brief_md, stats["run_id"], stats["finished_at"],
                                 prompts=prompts, prefix=BRIEF_PREFIX)
        meta_path = write_brief_meta(
            brief_path,
            run_id=stats["run_id"],
            records_tier=stats["records_tier"],
            brief_source=BRIEF_SOURCE_RULES if stats.get("brief_fallback") or not brief_md
            else BRIEF_SOURCE_MODEL,
            record_tiers=stats["analysis_tiers"],
            latest_name=f"{BRIEF_PREFIX}_latest.md",
        )
        stats["brief_path"] = brief_path
        stats["brief_meta_path"] = str(meta_path)
        stats["brief_analysis_tier"] = json.loads(meta_path.read_text(encoding="utf-8"))["analysis_tier"]
        stats["brief_word_count"] = len(brief_md.split())
        if verbose:
            print(f"  Brief written: {brief_path} ({stats['brief_word_count']} words, "
                  f"backend={stats.get('brief_backend', 'rules')}, "
                  f"tier={stats['brief_analysis_tier']})")
    except Exception as exc:
        logger.error("Legislative brief failed: %s", exc)
        stats["errors"].append(f"briefing:{exc}")
