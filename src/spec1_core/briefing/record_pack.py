"""Record pack: the stored cycle records a World State Brief is written from.

A pack is a JSON file holding every stored ``intelligence_records`` row in a
window (or for given run ids), each with an explicit *tier label* saying how
its analysis was produced, plus the psyop results for the same runs. The brief
writer (``spec1_core.briefing.world_state``) takes every score, source and id
from the pack; nothing in a brief may come from anywhere else.

Tier labels
-----------
Each record gets ``tier`` = {tier_used, model, llm_session, source, log_ts}:

``source = "column"``
    The row has ``tier_used`` (migration 013 or later).
``source = "log_match"``
    The row predates migration 013. Its tier comes from the one
    ``logs/llm_fallback.jsonl`` analyze entry that succeeded within
    ``LOG_MATCH_WINDOW_S`` seconds before ``written_at``. The match must be
    unique, one log entry per record, and agree with the stored
    ``analysis_tier``; otherwise the record is ``unknown``.
``source = "unknown"``
    Neither applies. Counted, never used for analysis.

Only records whose tier is a real model (``spec1_labels.LLM_TIERS_REAL``) are
``usable_for_analysis``. Rules-tier records are counted and labelled as such.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from spec1_labels import (
    LLM_TIER_RULES,
    LLM_TIER_RULES_ALIASES,
    LLM_TIERS_REAL,
    analysis_tier_for,
)

PACK_SCHEMA_VERSION = 1
# A record is written right after its analyze call returns; the log stamps
# whole seconds. Observed offsets on 2026-11-19 were 0-1 s.
LOG_MATCH_WINDOW_S = 2.0

TIER_SOURCE_COLUMN = "column"
TIER_SOURCE_LOG = "log_match"
TIER_SOURCE_UNKNOWN = "unknown"
TIER_UNKNOWN = "unknown"

_RECORD_COLUMNS = (
    "rowid", "id", "record_id", "run_id", "signal_id", "signal_source", "source_type",
    "signal_url", "signal_published_at", "opportunity_id", "opportunity_score",
    "opportunity_priority", "gate_results", "investigation_id", "hypothesis",
    "classification", "confidence", "outcome_classification", "outcome_confidence",
    "source_weight", "analyst_weight", "environment", "written_at", "created_at",
    "signal_excerpt", "llm_reasoning", "analysis_tier", "tier_used", "model",
    "llm_session", "stamped_by",
)


class RecordPackError(RuntimeError):
    """The pack cannot be built honestly (bad inputs, empty window, ...)."""


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _columns(con: sqlite3.Connection) -> set[str]:
    return {r[1] for r in con.execute("PRAGMA table_info(intelligence_records)")}


def load_records(db_path: Path, *, since: datetime | None = None,
                 until: datetime | None = None,
                 run_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Stored records in the window / runs, oldest first. Opens the DB read-only."""
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        have = _columns(con) | {"rowid"}
        cols = [c for c in _RECORD_COLUMNS if c in have]
        where, args = [], []
        if since is not None:
            where.append("written_at >= ?")
            args.append(since.astimezone(timezone.utc).isoformat())
        if until is not None:
            where.append("written_at < ?")
            args.append(until.astimezone(timezone.utc).isoformat())
        runs = list(run_ids or [])
        if runs:
            where.append(f"run_id IN ({','.join('?' * len(runs))})")
            args.extend(runs)
        sql = f"SELECT {', '.join(cols)} FROM intelligence_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY written_at, rowid"
        rows = [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()
    for row in rows:
        for col in _RECORD_COLUMNS:
            row.setdefault(col, None)
        try:
            row["gate_results"] = json.loads(row["gate_results"] or "{}")
        except (TypeError, json.JSONDecodeError):
            row["gate_results"] = {}
    return rows


def load_log(log_path: Path) -> list[dict[str, Any]]:
    """Analyze-task entries from logs/llm_fallback.jsonl, with parsed timestamps."""
    entries = []
    path = Path(log_path)
    if not path.exists():
        return entries
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("task") != "analyze":
            continue
        ts = _parse_ts(entry.get("ts"))
        if ts is None:
            continue
        entry["_ts"] = ts
        entry["_line"] = n
        entries.append(entry)
    return entries


def _normalise_tier(tier: str | None) -> str | None:
    if tier in LLM_TIER_RULES_ALIASES:
        return LLM_TIER_RULES
    return tier


@dataclass
class _Match:
    entry: dict[str, Any] | None
    reason: str


def match_log_entries(records: list[dict[str, Any]], log: list[dict[str, Any]],
                      window_s: float = LOG_MATCH_WINDOW_S) -> dict[int, _Match]:
    """Pair pre-013 records with the analyze log entry that produced them.

    A record matches a *successful* log entry stamped within ``window_s``
    seconds at or before its ``written_at``. Records with zero or several
    candidates, and log entries claimed by more than one record, are unmatched.
    """
    window = timedelta(seconds=window_s)
    ok = [e for e in log if e.get("success") is True]
    candidates: dict[int, list[dict[str, Any]]] = {}
    for rec in records:
        wt = _parse_ts(rec.get("written_at"))
        if wt is None:
            candidates[rec["rowid"]] = []
            continue
        # the log floors to whole seconds, so allow up to 1 s "after" too
        candidates[rec["rowid"]] = [
            e for e in ok
            if timedelta(seconds=-1) < wt - e["_ts"] <= window
        ]
    claims = Counter(id(e) for cands in candidates.values() if len(cands) == 1 for e in cands)
    result: dict[int, _Match] = {}
    for rowid, cands in candidates.items():
        if not cands:
            result[rowid] = _Match(None, "no analyze log entry within the match window")
        elif len(cands) > 1:
            result[rowid] = _Match(None, f"{len(cands)} log entries within the match window")
        elif claims[id(cands[0])] > 1:
            result[rowid] = _Match(None, "log entry also matches another record")
        else:
            result[rowid] = _Match(cands[0], "unique match")
    return result


def label_tier(record: dict[str, Any], match: _Match | None) -> dict[str, Any]:
    """The tier label for one record (see module docstring)."""
    if record.get("tier_used"):
        tier = _normalise_tier(record["tier_used"])
        return {"tier_used": tier, "model": record.get("model"),
                "llm_session": record.get("llm_session"), "source": TIER_SOURCE_COLUMN,
                "log_ts": None, "log_line": None, "note": "tier_used column"}
    if match is None or match.entry is None:
        return {"tier_used": TIER_UNKNOWN, "model": None, "llm_session": None,
                "source": TIER_SOURCE_UNKNOWN, "log_ts": None, "log_line": None,
                "note": match.reason if match else "no log available"}
    entry = match.entry
    tier = _normalise_tier(entry.get("tier"))
    stored = record.get("analysis_tier")
    if stored and analysis_tier_for(tier) != stored:
        return {"tier_used": TIER_UNKNOWN, "model": None, "llm_session": None,
                "source": TIER_SOURCE_UNKNOWN, "log_ts": entry.get("ts"),
                "log_line": entry.get("_line"),
                "note": f"log tier {tier!r} disagrees with stored analysis_tier {stored!r}"}
    return {"tier_used": tier, "model": None, "llm_session": entry.get("session"),
            "source": TIER_SOURCE_LOG, "log_ts": entry.get("ts"),
            "log_line": entry.get("_line"),
            "note": "matched to logs/llm_fallback.jsonl by written_at; model not logged before migration 013"}


def _sha256(path: Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_psyop(psyop_path: Path, run_ids: set[str]) -> list[dict[str, Any]]:
    """Psyop results recorded for the pack's runs, with a topic-proximity test.

    The test looks at what the supporting excerpts actually say around the
    cluster topic: if the topic term sits in many unrelated phrases
    (``north`` in "North Korea", "North Atlantic", ...), the cluster is
    topic proximity, not message alignment.
    """
    path = Path(psyop_path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("run_id") not in run_ids:
            continue
        chains = []
        for chain in d.get("evidence_chains") or []:
            excerpts = chain.get("raw_excerpts") or []
            chains.append({
                "pattern_name": chain.get("pattern_name"),
                "confidence": chain.get("confidence"),
                "supporting_signal_count": len(chain.get("supporting_signals") or []),
                "supporting_signals": list(chain.get("supporting_signals") or []),
                "distinct_sources": sorted({e.get("source") for e in excerpts if e.get("source")}),
                "topic_test": topic_proximity_test(d.get("topic") or "", excerpts),
            })
        out.append({
            "run_id": d.get("run_id"), "topic": d.get("topic"), "score": d.get("score"),
            "classification": d.get("classification"),
            "patterns_fired": d.get("patterns_fired") or [], "timestamp": d.get("timestamp"),
            "evidence_chains": chains,
        })
    return out


def _stem(word: str) -> str:
    """Fold simple word forms together: korean/koreans/korea-china -> korea."""
    word = word.split("-", 1)[0]
    for suffix in ("ns", "n", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


# A cluster whose supporting excerpts mostly do not contain the topic term
# was not built on that topic.
TOPIC_COVERAGE_FLOOR = 0.5
# Below this share for the most common phrase, the term is a shared word
# across unrelated subjects.
TOPIC_SINGLE_SUBJECT_SHARE = 0.6


def topic_proximity_test(topic: str, excerpts: list[dict[str, Any]]) -> dict[str, Any]:
    """Test whether a cluster's excerpts share a message or only a word.

    Three measurements, all from the excerpts themselves:
    ``coverage``  share of supporting excerpts that contain the topic term;
    ``phrases``   what the term is part of ("north korea", "north atlantic"),
                  word forms folded together;
    ``sources``   which outlets carry the term-bearing excerpts.
    Verdicts: ``topic_proximity`` (coverage below the floor, or the term is
    spread across unrelated phrases), ``single_subject`` (one subject; this
    test cannot tell coverage of a subject from coordinated messaging, so the
    brief must say so), ``untested``.
    """
    import re

    term = topic.strip().lower()
    base = {"term": term or topic, "excerpts": len(excerpts)}
    if not term or not excerpts:
        return {**base, "excerpts_with_term": 0, "coverage": 0.0, "phrases": {},
                "distinct_phrases": 0, "top_phrase_share": 0.0, "term_sources": {},
                "verdict": "untested", "reason": "no topic term or no excerpts"}
    word = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    follow = re.compile(rf"\b{re.escape(term)}\s+([a-z][a-z\-]+)", re.IGNORECASE)
    phrases: Counter[str] = Counter()
    term_sources: Counter[str] = Counter()
    with_term = 0
    for e in excerpts:
        text = e.get("text_snippet") or ""
        if not word.search(text):
            continue
        with_term += 1
        term_sources[e.get("source") or "unknown"] += 1
        for nxt in follow.findall(text):
            phrases[f"{term} {_stem(nxt.lower())}"] += 1
    coverage = with_term / len(excerpts)
    share_top = (max(phrases.values()) / sum(phrases.values())) if phrases else 0.0
    top_phrase = phrases.most_common(1)[0][0] if phrases else None
    if coverage < TOPIC_COVERAGE_FLOOR:
        verdict = "topic_proximity"
        reason = (f"only {with_term} of {len(excerpts)} supporting excerpts ({coverage:.0%}) "
                  f"contain '{term}'; the cluster was not built on that topic")
    elif len(phrases) >= 3 and share_top < TOPIC_SINGLE_SUBJECT_SHARE:
        verdict = "topic_proximity"
        reason = (f"'{term}' appears in {len(phrases)} different phrases and the most common "
                  f"covers {share_top:.0%} of uses: a shared word, not a shared message")
    elif phrases:
        verdict = "single_subject"
        reason = (f"'{top_phrase}' is {share_top:.0%} of uses: one subject, which this test "
                  f"cannot tell apart from coordinated messaging")
    else:
        verdict = "untested"
        reason = f"'{term}' never leads a phrase in the excerpts"
    return {**base, "excerpts_with_term": with_term, "coverage": round(coverage, 3),
            "phrases": dict(phrases.most_common(8)), "distinct_phrases": len(phrases),
            "top_phrase": top_phrase, "top_phrase_share": round(share_top, 3),
            "term_sources": dict(term_sources.most_common(8)),
            "verdict": verdict, "reason": reason}


def build_record_pack(db_path: Path, log_path: Path, *, since: datetime | None = None,
                      until: datetime | None = None, run_ids: Iterable[str] | None = None,
                      psyop_path: Path | None = None,
                      now: datetime | None = None) -> dict[str, Any]:
    """Build the pack. Raises RecordPackError if the window holds no records."""
    now = now or datetime.now(timezone.utc)
    records = load_records(db_path, since=since, until=until, run_ids=run_ids)
    if not records:
        raise RecordPackError("no stored records in the requested window: nothing to brief from")
    pre013 = [r for r in records if not r.get("tier_used")]
    matches = match_log_entries(pre013, load_log(log_path)) if pre013 else {}
    packed = []
    for rec in records:
        tier = label_tier(rec, matches.get(rec["rowid"]))
        rec = {k: v for k, v in rec.items()}
        rec["tier"] = tier
        rec["usable_for_analysis"] = tier["tier_used"] in LLM_TIERS_REAL
        packed.append(rec)
    runs = sorted({r["run_id"] for r in packed})
    tiers = Counter(r["tier"]["tier_used"] for r in packed)
    sources = Counter(r["tier"]["source"] for r in packed)
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "built_at": now.isoformat(),
        "window": {"since": since.isoformat() if since else None,
                   "until": until.isoformat() if until else None,
                   "run_ids": list(run_ids or [])},
        "inputs": {"db_path": str(db_path), "log_path": str(log_path),
                   "log_sha256": _sha256(log_path),
                   "psyop_path": str(psyop_path) if psyop_path else None,
                   "log_match_window_s": LOG_MATCH_WINDOW_S},
        "runs": runs,
        "counts": {
            "records": len(packed),
            "usable_for_analysis": sum(r["usable_for_analysis"] for r in packed),
            "by_tier": dict(sorted(tiers.items())),
            "by_tier_source": dict(sorted(sources.items())),
            "by_source": dict(Counter(r["signal_source"] for r in packed).most_common()),
            "by_priority": dict(Counter(r["opportunity_priority"] for r in packed).most_common()),
        },
        "psyop": load_psyop(psyop_path, set(runs)) if psyop_path else [],
        "records": packed,
    }


def write_record_pack(pack: dict[str, Any], out_path: Path, *, overwrite: bool = False) -> Path:
    out = Path(out_path)
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} exists; record packs are never overwritten")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return out


def read_record_pack(path: Path) -> dict[str, Any]:
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    if pack.get("schema_version") != PACK_SCHEMA_VERSION:
        raise RecordPackError(f"unsupported pack schema_version {pack.get('schema_version')!r}")
    return pack
