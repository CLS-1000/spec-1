# @domain:   spec-1
# @module:   mcp_server
# @loc:      _SCRATCH
# @status:   drafting
# @depends:  NONE

"""SPEC-1 MCP Server — exposes SPEC-1 tools to Claude via Model Context Protocol.

Tools exposed:
  - run_cycle          Run a full SPEC-1 intelligence cycle
  - get_signals        Return recent harvested signals
  - get_intel          Return intelligence records
  - get_leads          Return actionable leads
  - get_brief          Return the latest world brief
  - get_psyop          Return psyop detection scores
  - get_fara           Return FARA filing records
  - analyse_psyop      Score text for psyop patterns
  - get_stats          Return system statistics
  - file_verdict       File a human verdict on an intelligence record
  - get_verdicts       Return verdicts (optionally for a single record)
  - get_calibration    Produce a calibration drift report from intel + verdicts
  - run_psyop          Score every intelligence record for psyop patterns (operator tool)
  - generate_brief     Build a daily brief for one run_id (operator tool, Claude + fallback)
  - generate_leads     Derive Lead objects from intelligence records (operator tool)
  - run_research       Run analyst-defined topic research dossier expansion

This server uses a simple JSON-RPC 2.0 over stdio protocol compatible
with the Claude MCP specification.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# MCP protocol helpers
# ---------------------------------------------------------------------------

def _make_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _store_path(env_var: str, default: str) -> Path:
    return Path(os.environ.get(env_var, default))


def _read_jsonl(path: Path, limit: int = 20) -> list[dict]:
    """Read the last `limit` records from a JSONL file."""
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records[-limit:]


def tool_run_cycle(args: dict) -> dict:
    """Run a full SPEC-1 intelligence cycle (all steps: psyop, brief, publication, workspace)."""
    from spec1_core.app.cycle import run_cycle

    max_signals = args.get("max_signals")
    environment = args.get("environment", "production")
    store_path = _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")

    return run_cycle(
        store_path=store_path,
        environment=environment,
        max_signals=int(max_signals) if max_signals else None,
        verbose=False,
    )


def tool_get_signals(args: dict) -> list[dict]:
    """Return recent OSINT signals."""
    limit = int(args.get("limit", 20))
    path = _store_path("SPEC1_OSINT_PATH", "osint_records.jsonl")
    return _read_jsonl(path, limit=limit)


def tool_get_intel(args: dict) -> list[dict]:
    """Return intelligence records."""
    limit = int(args.get("limit", 20))
    min_confidence = float(args.get("min_confidence", 0.0))
    path = _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    records = _read_jsonl(path, limit=200)
    if min_confidence > 0:
        records = [r for r in records if float(r.get("confidence", 0)) >= min_confidence]
    return records[-limit:]


def tool_get_leads(args: dict) -> list[dict]:
    """Return actionable intelligence leads."""
    limit = int(args.get("limit", 20))
    priority = args.get("priority")
    path = _store_path("SPEC1_LEADS_PATH", "leads.jsonl")
    records = _read_jsonl(path, limit=200)
    if priority:
        records = [r for r in records if r.get("priority") == priority.upper()]
    return records[-limit:]


def tool_get_brief(args: dict) -> dict:
    """Return the latest world brief."""
    path = _store_path("SPEC1_BRIEFS_PATH", "world_briefs.jsonl")
    records = _read_jsonl(path, limit=1)
    if not records:
        return {"message": "No brief available yet"}
    return records[-1]


def tool_get_psyop(args: dict) -> list[dict]:
    """Return psyop detection scores."""
    limit = int(args.get("limit", 20))
    min_risk = args.get("min_classification", "LOW_RISK")
    path = _store_path("SPEC1_PSYOP_PATH", "psyop_scores.jsonl")
    records = _read_jsonl(path, limit=200)
    order = {"CLEAN": 0, "LOW_RISK": 1, "MEDIUM_RISK": 2, "HIGH_RISK": 3}
    threshold = order.get(min_risk, 1)
    filtered = [r for r in records if order.get(r.get("classification", "CLEAN"), 0) >= threshold]
    return filtered[-limit:]


def tool_get_fara(args: dict) -> list[dict]:
    """Return FARA filing records."""
    limit = int(args.get("limit", 20))
    country = args.get("country")
    path = _store_path("SPEC1_OSINT_PATH", "osint_records.jsonl")
    records = _read_jsonl(path, limit=500)
    fara_records = [r for r in records if r.get("source_type") == "fara"]
    if country:
        fara_records = [
            r for r in fara_records
            if r.get("metadata", {}).get("country", "").lower() == country.lower()
        ]
    return fara_records[-limit:]


def tool_analyse_psyop(args: dict) -> dict:
    """Score text for psychological operation patterns."""
    text = args.get("text", "")
    if not text:
        return {"error": "text is required"}
    from cls_psyop.scorer import score_text
    result = score_text(str(text))
    return result.to_dict()


def tool_get_stats(args: dict) -> dict:
    """Return system statistics (record counts across all stores)."""
    stats: dict[str, int] = {}
    paths = {
        "intelligence": _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"),
        "osint": _store_path("SPEC1_OSINT_PATH", "osint_records.jsonl"),
        "leads": _store_path("SPEC1_LEADS_PATH", "leads.jsonl"),
        "psyop": _store_path("SPEC1_PSYOP_PATH", "psyop_scores.jsonl"),
        "briefs": _store_path("SPEC1_BRIEFS_PATH", "world_briefs.jsonl"),
        "verdicts": _store_path("SPEC1_VERDICTS_PATH", "verdicts.jsonl"),
    }
    for name, path in paths.items():
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                stats[name] = sum(1 for line in fh if line.strip())
        else:
            stats[name] = 0
    stats["checked_at"] = datetime.now(timezone.utc).isoformat()  # type: ignore[assignment]
    return stats


def tool_file_verdict(args: dict) -> dict:
    """File a human verdict on a stored intelligence record."""
    from cls_verdicts.schemas import VALID_VERDICTS, Verdict
    from cls_verdicts.store import VerdictStore

    record_id = str(args.get("record_id", "")).strip()
    kind = str(args.get("verdict", "")).strip().lower()
    reviewer = str(args.get("reviewer", "anonymous")).strip() or "anonymous"
    notes = str(args.get("notes", ""))

    if not record_id:
        return {"error": "record_id is required"}
    if kind not in VALID_VERDICTS:
        return {"error": f"verdict must be one of {sorted(VALID_VERDICTS)}, got {kind!r}"}

    reviewed_at = datetime.now(timezone.utc)
    verdict = Verdict(
        verdict_id=Verdict.make_id(record_id, reviewer, reviewed_at),
        record_id=record_id,
        verdict=kind,  # type: ignore[arg-type]
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        notes=notes,
    )
    store = VerdictStore(_store_path("SPEC1_VERDICTS_PATH", "verdicts.jsonl"))
    return store.save(verdict)


def tool_get_verdicts(args: dict) -> list[dict]:
    """Return verdicts. If record_id is given, returns every verdict for that record."""
    from cls_verdicts.store import VerdictStore

    record_id = args.get("record_id")
    limit = int(args.get("limit", 20))
    store = VerdictStore(_store_path("SPEC1_VERDICTS_PATH", "verdicts.jsonl"))

    if record_id:
        return store.for_record(str(record_id))
    # Tail of the JSONL — last `limit` verdicts in insertion order.
    return list(store.read_all())[-limit:]


def tool_run_psyop(args: dict) -> dict:
    """Score every intelligence record for psyop patterns and persist the scores.

    Reads from $SPEC1_STORE_PATH (default spec1_intelligence.jsonl) and
    writes one PsyopScore per scored record to the configured psyop store.
    """
    from cls_psyop.scorer import filter_risky, score_records
    from cls_psyop.store import PsyopStore

    intel_path = _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    out_path = Path(args.get("out") or os.environ.get("SPEC1_PSYOP_PATH", "generated/psyop_scores.jsonl"))
    min_classification = args.get("min_classification", "CLEAN")

    records = _read_jsonl(intel_path, limit=10**9)
    scores = score_records(records)
    if min_classification != "CLEAN":
        scores = filter_risky(scores, min_classification=min_classification)

    written = PsyopStore(out_path).save_batch(scores)
    by_class: dict[str, int] = {}
    for s in scores:
        by_class[s.classification] = by_class.get(s.classification, 0) + 1

    return {
        "intel_path": str(intel_path),
        "out_path": str(out_path),
        "records_read": len(records),
        "scores_kept": len(scores),
        "scores_written": len(written),
        "by_classification": by_class,
    }


def tool_generate_brief(args: dict) -> dict:
    """Generate a daily intelligence brief for one run_id (default: latest).

    Tries Claude Sonnet first; falls back to the rule-based producer on failure
    or when ANTHROPIC_API_KEY is unset. Writes to generated/briefs/ by default.
    """
    from spec1_core.tools.generate_brief import (
        _cycle_stats_for,
        _group_by_run_id,
        _pick_run,
        _read_jsonl as _read_intel_jsonl,
        _rule_based_fallback,
        _try_claude,
        _write_outputs,
    )

    intel_path = _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    out_dir = Path(args.get("out_dir") or os.environ.get("SPEC1_BRIEFS_DIR", "generated/briefs"))
    run_id_arg = args.get("run_id", "latest")
    rule_based = bool(args.get("rule_based", False))

    records = _read_intel_jsonl(intel_path)
    if not records:
        return {"records_read": 0, "out_path": None, "note": "no records"}

    groups = _group_by_run_id(records)
    run_id, run_records = _pick_run(groups, run_id_arg)
    cycle_stats = _cycle_stats_for(run_id, run_records)

    brief_md = ""
    prompts = ""
    used_fallback = False
    mode = args.get("mode", "standard")
    if not rule_based:
        result = _try_claude(run_records, cycle_stats, mode=mode)
        if result is not None:
            brief_md, prompts = result
    if not brief_md:
        brief_md = _rule_based_fallback(run_records)
        used_fallback = True

    out_path = _write_outputs(out_dir, brief_md, prompts, run_id, cycle_stats["finished_at"])
    return {
        "run_id": run_id,
        "records_used": len(run_records),
        "word_count": len(brief_md.split()),
        "source": "rule-based" if used_fallback else "claude",
        "out_path": str(out_path),
    }


def tool_generate_leads(args: dict) -> dict:
    """Derive Lead objects from intelligence records and persist them.

    Reads from $SPEC1_STORE_PATH and writes Lead JSONL to the configured leads store.
    """
    from cls_leads.generator import generate_leads
    from cls_leads.store import LeadStore

    intel_path = _store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl")
    out_path = Path(args.get("out") or os.environ.get("SPEC1_LEADS_PATH", "generated/leads.jsonl"))
    min_confidence = float(args.get("min_confidence", 0.3))
    max_leads = int(args.get("max_leads", 50))
    priority_filter = args.get("priority")

    records = _read_jsonl(intel_path, limit=10**9)
    leads = generate_leads(records, min_confidence=min_confidence, max_leads=max_leads)
    if priority_filter:
        leads = [lead for lead in leads if lead.priority == priority_filter]

    written = LeadStore(out_path).save_batch(leads)
    by_priority: dict[str, int] = {}
    for lead in leads:
        by_priority[lead.priority] = by_priority.get(lead.priority, 0) + 1

    return {
        "intel_path": str(intel_path),
        "out_path": str(out_path),
        "records_read": len(records),
        "leads_kept": len(leads),
        "leads_written": len(written),
        "by_priority": by_priority,
    }


def tool_get_calibration(args: dict) -> dict:
    """Produce a calibration drift report from the current intel + verdicts stores."""
    from cls_calibration.aggregator import produce_report
    from cls_calibration.proposer import propose_adjustments

    include_proposals = bool(args.get("include_proposals", False))
    sample_floor = int(args.get("sample_floor", 5))
    delta_floor = float(args.get("delta_floor", 0.15))

    intel = _read_jsonl(_store_path("SPEC1_STORE_PATH", "spec1_intelligence.jsonl"), limit=10**9)
    verdicts = _read_jsonl(_store_path("SPEC1_VERDICTS_PATH", "verdicts.jsonl"), limit=10**9)

    report = produce_report(intel, verdicts)
    out = report.to_dict()
    if include_proposals:
        proposal = propose_adjustments(
            report,
            sample_floor=sample_floor,
            delta_floor=delta_floor,
        )
        out["proposal"] = proposal.to_dict()
    return out


def tool_score_signal(args: dict) -> dict:
    """Score a signal through the 3-pass operator evaluation framework.

    Pass 1 — evidence quality (credibility + volume)
    Pass 2 — deviation strength (velocity + novelty)
    Pass 3 — beneficiary analysis (only when gate_score > 0.40)

    Returns a fully structured OperatorOutput with a queryable ESCALATE/ARCHIVE/HOLD verdict.
    """
    from datetime import datetime, timezone

    from spec1_core.schemas.models import Signal, ParsedSignal
    from spec1_core.signal.parser import parse_signal
    from spec1_core.signal.operator_evaluator import evaluate

    signal_text = str(args.get("signal_text", "")).strip()
    if not signal_text:
        return {"error": "signal_text is required"}

    source = str(args.get("source", "unknown")).strip() or "unknown"
    run_id = str(args.get("run_id", "")).strip()

    # Parse timestamp
    ts_raw = args.get("timestamp")
    try:
        published_at = (
            datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            if ts_raw
            else datetime.now(timezone.utc)
        )
    except ValueError:
        published_at = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)

    sig = Signal(
        signal_id=f"sig-mcp-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        source=source,
        source_type="mcp",
        text=signal_text,
        url="",
        author="",
        published_at=published_at,
        velocity=0.0,
        engagement=0.0,
        run_id=run_id,
        environment="mcp",
        metadata={},
    )
    parsed = parse_signal(sig)
    output = evaluate(sig, parsed, run_id=run_id)
    return output.to_dict()


def tool_run_research(args: dict) -> dict:
    """Run analyst-defined topic research dossier expansion."""
    from spec1_core.tools.run_research import run_research

    topic_name = args.get("topic_name")
    topics_path = _store_path("SPEC1_RESEARCH_TOPICS_PATH", "research/topics")
    dossier_path = _store_path("SPEC1_RESEARCH_DOSSIER_PATH", "research/dossiers")

    return run_research(
        topic_name=topic_name,
        topics_path=topics_path,
        dossier_path=dossier_path,
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict] = {
    "run_cycle": {
        "description": "Run a full SPEC-1 intelligence cycle (harvest, score, investigate, store).",
        "parameters": {
            "type": "object",
            "properties": {
                "max_signals": {"type": "integer", "description": "Limit number of signals (optional)"},
                "environment": {"type": "string", "default": "production"},
            },
        },
        "fn": tool_run_cycle,
    },
    "get_signals": {
        "description": "Return recent harvested OSINT signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "maximum": 200},
            },
        },
        "fn": tool_get_signals,
    },
    "get_intel": {
        "description": "Return intelligence records from the analysis store.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "min_confidence": {"type": "number", "default": 0.0},
            },
        },
        "fn": tool_get_intel,
    },
    "get_leads": {
        "description": "Return actionable intelligence leads.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
            },
        },
        "fn": tool_get_leads,
    },
    "get_brief": {
        "description": "Return the latest world intelligence brief.",
        "parameters": {"type": "object", "properties": {}},
        "fn": tool_get_brief,
    },
    "get_psyop": {
        "description": "Return psychological operation detection scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "min_classification": {
                    "type": "string",
                    "enum": ["LOW_RISK", "MEDIUM_RISK", "HIGH_RISK"],
                    "default": "LOW_RISK",
                },
            },
        },
        "fn": tool_get_psyop,
    },
    "get_fara": {
        "description": "Return FARA (Foreign Agents Registration Act) filing records.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "country": {"type": "string", "description": "Filter by country"},
            },
        },
        "fn": tool_get_fara,
    },
    "analyse_psyop": {
        "description": "Score a text snippet for psychological operation patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to analyse"},
            },
            "required": ["text"],
        },
        "fn": tool_analyse_psyop,
    },
    "get_stats": {
        "description": "Return record counts across all SPEC-1 stores.",
        "parameters": {"type": "object", "properties": {}},
        "fn": tool_get_stats,
    },
    "file_verdict": {
        "description": (
            "File a human verdict on a stored intelligence record. "
            "Verdicts are append-only — multiple verdicts may exist per record."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Target IntelligenceRecord id"},
                "verdict": {
                    "type": "string",
                    "enum": ["correct", "incorrect", "partial", "unclear"],
                },
                "reviewer": {"type": "string", "default": "anonymous"},
                "notes": {"type": "string", "default": ""},
            },
            "required": ["record_id", "verdict"],
        },
        "fn": tool_file_verdict,
    },
    "get_verdicts": {
        "description": "Return verdicts. With record_id, returns every verdict for that record.",
        "parameters": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "description": "Filter to a single record (optional)"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "fn": tool_get_verdicts,
    },
    "get_calibration": {
        "description": (
            "Produce a calibration drift report from the current intel + verdicts stores. "
            "Descriptive only — never auto-applies tuning. Set include_proposals=true to "
            "also return suggested adjustments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "include_proposals": {"type": "boolean", "default": False},
                "sample_floor": {"type": "integer", "default": 5},
                "delta_floor": {"type": "number", "default": 0.15},
            },
        },
        "fn": tool_get_calibration,
    },
    "run_psyop": {
        "description": (
            "Score every intelligence record for psyop patterns and append the scores to "
            "the psyop store. Operator tool — runs out of band from the cycle."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "out": {"type": "string", "description": "Output JSONL path (default generated/psyop_scores.jsonl)"},
                "min_classification": {
                    "type": "string",
                    "enum": ["CLEAN", "LOW_RISK", "MEDIUM_RISK", "HIGH_RISK"],
                    "default": "CLEAN",
                },
            },
        },
        "fn": tool_run_psyop,
    },
    "generate_brief": {
        "description": (
            "Generate a daily intelligence brief for one run_id (default: latest run). "
            "Tries Claude Sonnet first; falls back to the rule-based producer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "default": "latest"},
                "out_dir": {"type": "string", "description": "Output directory (default generated/briefs)"},
                "rule_based": {"type": "boolean", "default": False, "description": "Skip Claude entirely"},
                "mode": {
                    "type": "string",
                    "enum": ["standard", "geopolitics", "legislative"],
                    "default": "standard",
                    "description": (
                        "Brief template: 'standard' (default SPEC-1 brief), "
                        "'geopolitics' (Geopolitics & Policy Desk), "
                        "or 'legislative' (Legislative & Judicial Desk)"
                    ),
                },
            },
        },
        "fn": tool_generate_brief,
    },
    "generate_leads": {
        "description": (
            "Derive actionable Lead objects from intelligence records and persist them. "
            "Operator tool — runs out of band from the cycle."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "out": {"type": "string", "description": "Output JSONL path (default generated/leads.jsonl)"},
                "min_confidence": {"type": "number", "default": 0.3},
                "max_leads": {"type": "integer", "default": 50},
                "priority": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
            },
        },
        "fn": tool_generate_leads,
    },
    "run_research": {
        "description": (
            "Run analyst-defined topic research dossier expansion. "
            "Expands topic definitions with automated signal collection and analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic_name": {"type": "string", "description": "Topic name to expand (optional; if not provided, expands all topics)"},
            },
        },
        "fn": tool_run_research,
    },
    "score_signal": {
        "description": (
            "Score a signal through the 3-pass operator evaluation framework and return a "
            "structured OperatorOutput with a queryable ESCALATE / ARCHIVE / HOLD verdict. "
            "Pass 1 = evidence quality (credibility + volume). "
            "Pass 2 = deviation strength (velocity + novelty). "
            "Pass 3 = beneficiary analysis — runs only when gate_score > 0.40. "
            "HOLD is a first-class verdict, not an error state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "signal_text": {
                    "type": "string",
                    "description": "Full text of the signal to evaluate",
                },
                "source": {
                    "type": "string",
                    "description": "Source identifier (e.g. 'reuters_world', 'propublica')",
                    "default": "unknown",
                },
                "timestamp": {
                    "type": "string",
                    "description": "ISO8601 publication timestamp (defaults to now if omitted)",
                },
                "run_id": {
                    "type": "string",
                    "description": "Cycle run_id to associate with this evaluation",
                },
            },
            "required": ["signal_text"],
        },
        "fn": tool_score_signal,
    },
}


# ---------------------------------------------------------------------------
# MCP method handlers
# ---------------------------------------------------------------------------

def handle_initialize(request_id: Any, params: dict) -> dict:
    return _make_response(request_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "spec1-mcp-server", "version": "0.5.0"},
    })


def handle_tools_list(request_id: Any, params: dict) -> dict:
    tools_list = []
    for name, meta in TOOLS.items():
        tools_list.append({
            "name": name,
            "description": meta["description"],
            "inputSchema": meta["parameters"],
        })
    return _make_response(request_id, {"tools": tools_list})


def handle_tools_call(request_id: Any, params: dict) -> dict:
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in TOOLS:
        return _make_error(request_id, -32601, f"Tool not found: {tool_name}")

    try:
        result = TOOLS[tool_name]["fn"](arguments)
        content = [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
        return _make_response(request_id, {"content": content, "isError": False})
    except Exception as exc:
        tb = traceback.format_exc()
        return _make_response(request_id, {
            "content": [{"type": "text", "text": f"Error: {exc}\n{tb}"}],
            "isError": True,
        })


def handle_request(line: str) -> None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        _send(_make_error(None, -32700, f"Parse error: {exc}"))
        return

    request_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        _send(handle_initialize(request_id, params))
    elif method == "tools/list":
        _send(handle_tools_list(request_id, params))
    elif method == "tools/call":
        _send(handle_tools_call(request_id, params))
    elif method == "notifications/initialized":
        pass  # No response needed for notifications
    else:
        _send(_make_error(request_id, -32601, f"Method not found: {method}"))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP server, reading JSON-RPC requests from stdin."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        handle_request(line)


if __name__ == "__main__":
    main()
