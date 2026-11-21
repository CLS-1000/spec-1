"""World State Brief: April 24 structure, April 28 print layout, record-pack facts.

The brief is written as a *spec* (JSON) against a record pack
(``spec1_core.briefing.record_pack``). The spec holds the prose and points at
records by ``rowid``; every score, source, record id, signal id, gate list and
tier shown in the brief is filled in from the pack by the renderer.

Prose placeholders (expanded from the pack)::

    {{score:<rowid>}}  {{source:<rowid>}}  {{record:<rowid>}}  {{signal:<rowid>}}
    {{conf:<rowid>}}   {{class:<rowid>}}   {{tier:<rowid>}}
    {{count:records}} {{count:usable}} {{count:elevated}} {{count:rules}}
    {{count:unknown}} {{count:sources}} {{top:score}} {{top:source}} {{top:record}}
    {{threshold:elevated}}
    {{psyop:<field>}}  (topic, classification, score, pattern, supporting,
                        coverage, with_term, top_phrase, top_share, verdict,
                        nk_share: share of term excerpts from the top outlet,
                        top_term_source)

``validate`` fails loudly (``BriefValidationError`` listing every problem)
on: a missing section; fewer than 3 or more than 5 leads; a lead missing any
field or any of Claude-prompt Steps 1-4; a step that looks cut off; a score
typed into prose instead of a placeholder; a rowid not in the pack; analysis
citing a record whose tier is not a real model; an elevated signal that is
not ELEVATED. Nothing is written when validation fails.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from spec1_core.config.calibration import PRIORITY_ELEVATED
from spec1_core.briefing.record_pack import TIER_UNKNOWN, read_record_pack
from spec1_labels import LLM_TIER_RULES, LLM_TIERS_REAL

PUBLISHER_LINE = "Notitia Civica — published by Matthew J. Lakamp"
MASTHEAD_TITLE = "WORLD STATE BRIEF"
MASTHEAD_KICKER = "Open-Source Intelligence · Daily Analysis"
DOMAIN_NAMES = ("Geopolitics", "Cyber / Info Ops", "Psyop / Narrative Analysis")
LEAD_FIELDS = ("title", "rowids", "question", "who_to_call", "documents", "window",
               "confidence", "prompt")
PROMPT_STEPS = ("step1", "step2", "step3", "step4")
MIN_LEADS, MAX_LEADS = 3, 5
# Words a complete step needs. The April 24 run cut a lead off after Step 2.
MIN_STEP_WORDS = {"step1": 25, "step2": 25, "step3": 35, "step4": 12}
STEP_MUST_MENTION = {
    "step1": ("background memo",),
    "step2": ("5 ", "yes/no"),
    "step3": ("FOIA",),
    "step4": ("150-word", "pitch memo"),
}
_TRUNCATION_MARKERS = ("…", "...", "[truncated", "added by hand", "TODO", "TBD", "lorem")
_TERMINAL = (".", "?", "!", '"', "”", ")", "'")
# A bare score in prose: 0.xx / 0.xxx / 1.0. Scores must come from placeholders.
_BARE_SCORE = re.compile(r"(?<![\w.{])(?:0\.\d{2,3}|1\.00?)(?![\w}])")
_PLACEHOLDER = re.compile(r"\{\{([a-z_]+):([a-z0-9_]+)\}\}")


class BriefValidationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("brief failed validation:\n  - " + "\n  - ".join(problems))


@dataclass
class Brief:
    spec: dict[str, Any]
    pack: dict[str, Any]
    pack_sha256: str

    @property
    def records(self) -> dict[int, dict[str, Any]]:
        return {int(r["rowid"]): r for r in self.pack["records"]}


def load(spec_path: Path, pack_path: Path) -> Brief:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    pack = read_record_pack(pack_path)
    sha = hashlib.sha256(Path(pack_path).read_bytes()).hexdigest()
    return Brief(spec=spec, pack=pack, pack_sha256=sha)


# ── Facts from the pack ────────────────────────────────────────────────────────

def _usable(rec: dict[str, Any]) -> bool:
    return rec["tier"]["tier_used"] in LLM_TIERS_REAL


def _elevated(rec: dict[str, Any]) -> bool:
    return (rec.get("opportunity_score") or 0) >= PRIORITY_ELEVATED


def facts(brief: Brief) -> dict[str, Any]:
    recs = list(brief.records.values())
    usable = [r for r in recs if _usable(r)]
    top = max(usable, key=lambda r: r["opportunity_score"] or 0) if usable else None
    return {
        "records": len(recs),
        "usable": len(usable),
        "elevated": sum(1 for r in usable if _elevated(r)),
        "rules": sum(1 for r in recs if r["tier"]["tier_used"] == LLM_TIER_RULES),
        "unknown": sum(1 for r in recs if r["tier"]["tier_used"] == TIER_UNKNOWN),
        "sources": len({r["signal_source"] for r in recs}),
        "top": top,
        "runs": brief.pack.get("runs", []),
    }


def tier_label(rec: dict[str, Any]) -> str:
    t = rec["tier"]
    name = t["tier_used"]
    if name == TIER_UNKNOWN:
        return "tier unknown — not used for analysis"
    how = "tier_used column" if t["source"] == "column" else "matched to llm_fallback.jsonl"
    label = f"{name}"
    if t.get("model"):
        label += f" ({t['model']})"
    if name == LLM_TIER_RULES:
        return f"rules tier ({how}) — counted, not analysis"
    return f"{label}, {how}"


def gates_text(rec: dict[str, Any]) -> str:
    gates = rec.get("gate_results") or {}
    passed = [g for g in ("credibility", "volume", "velocity", "novelty") if gates.get(g) is True]
    failed = [g for g in ("credibility", "volume", "velocity", "novelty") if gates.get(g) is False]
    text = " + ".join(passed) if passed else "no gate results stored"
    if failed:
        text += f" (failed: {', '.join(failed)})"
    return text


def _fmt(score: Any) -> str:
    return f"{float(score):.3f}" if score is not None else "n/a"


def _psyop_fields(brief: Brief) -> dict[str, str]:
    runs = brief.pack.get("psyop") or []
    if not runs or not runs[0].get("evidence_chains"):
        return {}
    run = runs[0]
    chain = run["evidence_chains"][0]
    test = chain["topic_test"]
    term_sources = test.get("term_sources") or {}
    top_src, top_n = (max(term_sources.items(), key=lambda kv: kv[1]) if term_sources
                      else ("n/a", 0))
    with_term = test.get("excerpts_with_term") or 0
    return {
        "topic": str(run.get("topic")),
        "classification": str(run.get("classification")),
        "score": str(run.get("score")),
        "pattern": str(chain.get("pattern_name")),
        "pattern_conf": _fmt(chain.get("confidence")),
        "supporting": str(chain.get("supporting_signal_count")),
        "sources": str(len(chain.get("distinct_sources") or [])),
        "coverage": f"{(test.get('coverage') or 0):.0%}",
        "with_term": str(with_term),
        "top_phrase": str(test.get("top_phrase")),
        "top_share": f"{(test.get('top_phrase_share') or 0):.0%}",
        "verdict": str(test.get("verdict")),
        "top_term_source": str(top_src),
        "nk_share": f"{(top_n / with_term if with_term else 0):.0%}",
    }


def expand(text: str, brief: Brief, problems: list[str], where: str) -> str:
    recs = brief.records
    f = facts(brief)
    psy = _psyop_fields(brief)

    def sub(m: re.Match) -> str:
        kind, key = m.group(1), m.group(2)
        if kind in ("score", "source", "record", "signal", "conf", "class", "tier"):
            try:
                rec = recs[int(key)]
            except (ValueError, KeyError):
                problems.append(f"{where}: placeholder {m.group(0)} names a rowid not in the pack")
                return m.group(0)
            return {
                "score": _fmt(rec["opportunity_score"]),
                "source": rec["signal_source"],
                "record": rec["record_id"],
                "signal": rec["signal_id"] or "n/a",
                "conf": _fmt(rec["confidence"]),
                "class": rec["classification"],
                "tier": tier_label(rec),
            }[kind]
        if kind == "count" and key in ("records", "usable", "elevated", "rules", "unknown",
                                       "sources"):
            return str(f[key])
        if kind == "top" and f["top"] is not None and key in ("score", "source", "record"):
            top = f["top"]
            return {"score": _fmt(top["opportunity_score"]), "source": top["signal_source"],
                    "record": top["record_id"]}[key]
        if kind == "psyop" and key in psy:
            return psy[key]
        if kind == "threshold" and key == "elevated":
            return f"{PRIORITY_ELEVATED:.2f}"
        problems.append(f"{where}: unknown placeholder {m.group(0)}")
        return m.group(0)

    return _PLACEHOLDER.sub(sub, text)


# ── Validation ─────────────────────────────────────────────────────────────────

def _words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _prose_items(spec: dict[str, Any]):
    """Yield (where, text) for every prose string in the spec."""
    yield "executive_summary", spec.get("executive_summary", "")
    yield "elevated_note", spec.get("elevated_note", "")
    for i, e in enumerate(spec.get("elevated") or []):
        yield f"elevated[{i}].headline", e.get("headline", "")
        yield f"elevated[{i}].note", e.get("note", "")
    for d in spec.get("domains") or []:
        for j, p in enumerate(d.get("paragraphs") or []):
            yield f"domain[{d.get('name')}].paragraphs[{j}]", p
        for k, v in (d.get("trajectory") or {}).items():
            yield f"domain[{d.get('name')}].trajectory.{k}", v
    for i, lead in enumerate(spec.get("leads") or []):
        for k in ("title", "question"):
            yield f"lead[{i}].{k}", lead.get(k, "")
        for j, w in enumerate(lead.get("who_to_call") or []):
            yield f"lead[{i}].who_to_call[{j}]", w
        docs = lead.get("documents") or {}
        for kind in ("foia", "pull_now"):
            for j, d in enumerate(docs.get(kind) or []):
                yield f"lead[{i}].documents.{kind}[{j}]", d
        yield f"lead[{i}].window.value", (lead.get("window") or {}).get("value", "")
        yield f"lead[{i}].window.reason", (lead.get("window") or {}).get("reason", "")
        yield f"lead[{i}].confidence.reason", (lead.get("confidence") or {}).get("reason", "")
        for s in PROMPT_STEPS:
            yield f"lead[{i}].prompt.{s}", (lead.get("prompt") or {}).get(s, "")
    for i, w in enumerate(spec.get("watch") or []):
        yield f"watch[{i}].item", w.get("item", "")


def _rowids_cited(spec: dict[str, Any]):
    for i, e in enumerate(spec.get("elevated") or []):
        yield f"elevated[{i}]", e.get("rowid")
    for d in spec.get("domains") or []:
        for r in d.get("rowids") or []:
            yield f"domain[{d.get('name')}]", r
    for i, lead in enumerate(spec.get("leads") or []):
        for r in lead.get("rowids") or []:
            yield f"lead[{i}]", r
    for i, w in enumerate(spec.get("watch") or []):
        for r in w.get("rowids") or []:
            yield f"watch[{i}]", r
    for where, text in _prose_items(spec):
        for m in _PLACEHOLDER.finditer(text or ""):
            if m.group(1) in ("score", "source", "record", "signal", "conf", "class"):
                yield where, m.group(2)


def _check_step(where: str, step: str, text: str, problems: list[str]) -> None:
    text = (text or "").strip()
    if not text:
        problems.append(f"{where}: {step} is missing (truncated lead)")
        return
    if _words(text) < MIN_STEP_WORDS[step]:
        problems.append(f"{where}: {step} has {_words(text)} words, needs {MIN_STEP_WORDS[step]}"
                        " (looks truncated)")
    if not text.endswith(_TERMINAL):
        problems.append(f"{where}: {step} does not end a sentence (looks truncated): "
                        f"…{text[-40:]!r}")
    for marker in _TRUNCATION_MARKERS:
        if marker.lower() in text.lower():
            problems.append(f"{where}: {step} contains truncation marker {marker!r}")
    for needle in STEP_MUST_MENTION[step]:
        if needle.lower() not in text.lower():
            problems.append(f"{where}: {step} must ask for {needle.strip()!r}")


def validate(brief: Brief) -> None:
    spec, recs = brief.spec, brief.records
    problems: list[str] = []

    for key in ("brief_date", "executive_summary", "elevated_note", "domains", "leads"):
        if not spec.get(key) and spec.get(key) != []:
            problems.append(f"missing section: {key}")
    names = [d.get("name") for d in spec.get("domains") or []]
    if tuple(names) != DOMAIN_NAMES:
        problems.append(f"domain briefings must be exactly {list(DOMAIN_NAMES)} in order, got {names}")
    for d in spec.get("domains") or []:
        if not d.get("paragraphs"):
            problems.append(f"domain[{d.get('name')}]: no paragraphs")
        if not (d.get("trajectory") or {}).get("limits"):
            problems.append(f"domain[{d.get('name')}]: trajectory.limits is required "
                            "(state what the signal pool cannot support)")
    psy = next((d for d in spec.get("domains") or [] if d.get("name") == DOMAIN_NAMES[2]), None)
    if psy is not None:
        joined = " ".join(psy.get("paragraphs") or [])
        if "{{psyop:verdict}}" not in joined and "{{psyop:coverage}}" not in joined:
            problems.append("psyop section must cite its own pattern test "
                            "({{psyop:coverage}} / {{psyop:verdict}})")
        verdict = _psyop_fields(brief).get("verdict")
        if verdict == "topic_proximity" and "NOISE" not in joined:
            problems.append("psyop test says topic proximity: the section must say NOISE")

    leads = spec.get("leads") or []
    if not MIN_LEADS <= len(leads) <= MAX_LEADS:
        problems.append(f"story leads: {len(leads)} given, need {MIN_LEADS}-{MAX_LEADS}")
    for i, lead in enumerate(leads):
        where = f"lead[{i}] {lead.get('title', '')!r}"
        for fld in LEAD_FIELDS:
            if not lead.get(fld):
                problems.append(f"{where}: missing {fld}")
        docs = lead.get("documents") or {}
        if not docs.get("foia"):
            problems.append(f"{where}: documents.foia (FOIA targets) missing")
        if not docs.get("pull_now"):
            problems.append(f"{where}: documents.pull_now (public records to pull now) missing")
        for k in ("value", "reason"):
            if not (lead.get("window") or {}).get(k):
                problems.append(f"{where}: window.{k} missing")
        if not (lead.get("confidence") or {}).get("level"):
            problems.append(f"{where}: confidence.level missing")
        if not (lead.get("confidence") or {}).get("reason"):
            problems.append(f"{where}: confidence.reason missing")
        prompt = lead.get("prompt") or {}
        for s in PROMPT_STEPS:
            _check_step(where, s, prompt.get(s, ""), problems)

    for i, e in enumerate(spec.get("elevated") or []):
        rec = recs.get(int(e.get("rowid", -1))) if str(e.get("rowid", "")).isdigit() else None
        if rec is not None and not _elevated(rec):
            problems.append(f"elevated[{i}]: rowid {e['rowid']} scored "
                            f"{_fmt(rec['opportunity_score'])}, below {PRIORITY_ELEVATED}")

    for where, rowid in _rowids_cited(spec):
        try:
            rec = recs[int(rowid)]
        except (TypeError, ValueError, KeyError):
            problems.append(f"{where}: rowid {rowid!r} is not in the pack")
            continue
        if not _usable(rec):
            problems.append(f"{where}: rowid {rowid} is {tier_label(rec)}; "
                            "only model-tier records may be used for analysis")

    for where, text in _prose_items(spec):
        for m in _BARE_SCORE.finditer(text or ""):
            problems.append(f"{where}: bare score {m.group(0)!r}; use a {{{{score:<rowid>}}}} "
                            "placeholder so it comes from the pack")
        expand(text or "", brief, problems, where)

    if problems:
        raise BriefValidationError(problems)


# ── Rendering ──────────────────────────────────────────────────────────────────

def _date_line(d: str) -> str:
    dt = date.fromisoformat(d)
    return dt.strftime("%A, %B ") + str(dt.day) + dt.strftime(", %Y")


def _signal_line(rec: dict[str, Any]) -> str:
    return (f"{rec['signal_source']} · score {_fmt(rec['opportunity_score'])} · "
            f"{rec['opportunity_priority']} · gates: {gates_text(rec)} · "
            f"{rec['classification']} {_fmt(rec['confidence'])} · "
            f"record {rec['record_id']} · signal {rec['signal_id']} · rowid {rec['rowid']} · "
            f"{tier_label(rec)}")


def _headline(rec: dict[str, Any]) -> str:
    text = html.unescape(rec.get("signal_excerpt") or "").strip()
    hyp = rec.get("hypothesis") or ""
    return text[:110].rsplit(" ", 1)[0] + "…" if len(text) > 110 else (text or hyp[:110])


def _prompt_text(lead: dict[str, Any], brief: Brief, problems: list[str], i: int) -> list[str]:
    recs = brief.records
    primary = recs[int(lead["rowids"][0])]
    ex = lambda t, w: expand(t, brief, problems, f"lead[{i}].{w}")  # noqa: E731
    lines = [
        f"You are an investigative journalist working this lead: {ex(lead['title'], 'title')}.",
        (f"The signal: {primary['signal_source']}, score {_fmt(primary['opportunity_score'])}, "
         f"gates: {gates_text(primary)}; record {primary['record_id']}, signal "
         f"{primary['signal_id']}. Treat the record as a pointer to a published article, "
         f"not as a verified fact."),
        f"The core question: {ex(lead['question'], 'question')}",
    ]
    for n, s in enumerate(PROMPT_STEPS, 1):
        lines.append(f"Step {n} — {ex(lead['prompt'][s], 'prompt.' + s)}")
    return lines


def render_markdown(brief: Brief) -> str:
    validate(brief)
    spec, recs, f = brief.spec, brief.records, facts(brief)
    problems: list[str] = []
    ex = lambda t, w: expand(t, brief, problems, w)  # noqa: E731
    out: list[str] = []
    a = out.append
    a(f"# {MASTHEAD_TITLE} — {spec['brief_date']}")
    a("")
    a(f"*{PUBLISHER_LINE}*")
    a("")
    a(f"Runs: {', '.join(f['runs'])} · Records in pack: {f['records']} "
      f"({f['usable']} model-tier, {f['rules']} rules-tier, {f['unknown']} tier unknown) · "
      f"Pack sha256 {brief.pack_sha256[:12]}")
    a("")
    a("---")
    a("")
    a("### Executive Summary")
    a("")
    a(ex(spec["executive_summary"], "executive_summary"))
    a("")
    a("---")
    a("")
    a("### Elevated Signals")
    a("")
    a(ex(spec["elevated_note"], "elevated_note"))
    a("")
    for i, e in enumerate(spec.get("elevated") or []):
        rec = recs[int(e["rowid"])]
        a(f"- **{ex(e['headline'], f'elevated[{i}].headline')}** — {_signal_line(rec)}. "
          f"{ex(e.get('note', ''), f'elevated[{i}].note')}".rstrip())
    a("")
    a("---")
    a("")
    a("### Domain Briefings")
    a("")
    for d in spec["domains"]:
        a(f"**{d['name']}**")
        a("")
        for j, p in enumerate(d["paragraphs"]):
            a(ex(p, f"domain[{d['name']}].paragraphs[{j}]"))
            a("")
        t = d.get("trajectory") or {}
        a("> **Trajectory Assessment**  ")
        for key, label in (("next_48h", "Next 48 hours"), ("seven_day", "7-day outlook"),
                           ("limits", "Limits")):
            if t.get(key):
                where = "domain[" + d["name"] + "].trajectory." + key
                a(f"> {label}: {ex(t[key], where)}  ")
        a("")
        if d.get("rowids"):
            a("Records: " + "; ".join(
                f"{recs[int(r)]['signal_source']} {_fmt(recs[int(r)]['opportunity_score'])} "
                f"({recs[int(r)]['record_id']})" for r in d["rowids"]))
            a("")
    a("---")
    a("")
    a("### Story Leads")
    a("")
    for i, lead in enumerate(spec["leads"]):
        primary = recs[int(lead["rowids"][0])]
        a("---")
        a("")
        a(f"**LEAD: {ex(lead['title'], f'lead[{i}].title')}**")
        a("")
        a(f"Signal: {_signal_line(primary)}")
        if len(lead["rowids"]) > 1:
            a("")
            a("Supporting records: " + "; ".join(_signal_line(recs[int(r)])
                                                 for r in lead["rowids"][1:]))
        a("")
        a(f"The question: {ex(lead['question'], f'lead[{i}].question')}")
        a("")
        a("Who to call: " + "; ".join(ex(w, f"lead[{i}].who") for w in lead["who_to_call"]))
        a("")
        docs = lead["documents"]
        a("Documents to request: FOIA — " + "; ".join(ex(x, f"lead[{i}].foia")
                                                      for x in docs["foia"]))
        a("")
        a("Public records to pull now: " + "; ".join(ex(x, f"lead[{i}].pull")
                                                     for x in docs["pull_now"]))
        a("")
        a(f"Window: {ex(lead['window']['value'], 'w')} — {ex(lead['window']['reason'], 'w')}")
        a("")
        a(f"Confidence: {lead['confidence']['level']} — "
          f"{ex(lead['confidence']['reason'], f'lead[{i}].confidence')}")
        a("")
        a("> **CLAUDE PROMPT:**")
        a(">")
        for line in _prompt_text(lead, brief, problems, i):
            a(f"> {line}")
            a(">")
        out.pop()
        a("")
    a("---")
    a("")
    if spec.get("watch"):
        a("### 24-Hour Watch List")
        a("")
        for i, w in enumerate(spec["watch"]):
            refs = ", ".join(recs[int(r)]["record_id"] for r in w.get("rowids") or [])
            a(f"- {ex(w['item'], f'watch[{i}]')}" + (f" ({refs})" if refs else ""))
        a("")
        a("---")
        a("")
    not_analysed = [r for r in recs.values() if not _usable(r)]
    a("### Records counted, not analysed")
    a("")
    if not_analysed:
        for r in not_analysed:
            a(f"- {r['signal_source']} · score {_fmt(r['opportunity_score'])} · record "
              f"{r['record_id']} · signal {r['signal_id']} · rowid {r['rowid']} · {tier_label(r)}")
    else:
        a("- None.")
    a("")
    a("---")
    a("")
    a(f"WORLD STATE BRIEF · {PUBLISHER_LINE}  ")
    a("Every score, source and id above comes from the stored cycle records in the pack "
      f"(sha256 {brief.pack_sha256}). Not for publication without editor review.")
    if problems:
        raise BriefValidationError(problems)
    md = "\n".join(out) + "\n"
    check_rendered(md, len(spec["leads"]))
    return md


def check_rendered(md: str, leads: int) -> None:
    """Re-read the rendered markdown: every lead must carry Steps 1-4 in full."""
    problems = []
    blocks = md.split("**LEAD: ")[1:]
    if len(blocks) != leads:
        problems.append(f"rendered {len(blocks)} leads, spec has {leads}")
    for n, block in enumerate(blocks):
        for s in range(1, 5):
            m = re.search(rf"> Step {s} — (.+)", block)
            if not m:
                problems.append(f"rendered lead {n}: Step {s} missing")
            elif not m.group(1).strip().endswith(_TERMINAL):
                problems.append(f"rendered lead {n}: Step {s} cut off")
    if problems:
        raise BriefValidationError(problems)


# The April 28 print layout (world-state-brief-2026-04-28.html), extended with
# lead and record styles in the same idiom.
PRINT_CSS = """
  :root { --ink:#111; --muted:#777; --rule:#111; }
  @page { size: Letter; margin: 0.6in; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 40px 0; background: #fff; color: var(--ink);
    font-family: "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace;
    font-size: 12.5px; line-height: 1.75;
  }
  .page { max-width: 760px; margin: 0 auto; padding: 0 28px; }
  .masthead { border: 2px solid var(--rule); padding: 44px 40px 28px; text-align: center; margin-bottom: 60px; }
  .masthead h1 { margin: 0; font-size: 36px; font-weight: 700; letter-spacing: 0.22em; }
  .masthead .kicker { margin: 18px 0 30px; font-size: 10px; letter-spacing: 0.35em; text-transform: uppercase; }
  .masthead .dateline { display: flex; justify-content: space-between; border-top: 1px solid var(--rule);
    padding-top: 18px; font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase; }
  .section-title { font-size: 11px; font-weight: 700; letter-spacing: 0.4em; text-transform: uppercase;
    border-bottom: 2px solid var(--rule); padding-bottom: 12px; margin: 0 0 26px; }
  section { margin-bottom: 70px; }
  .item { border-left: 2px solid var(--rule); padding-left: 20px; margin-bottom: 36px; }
  .region { font-size: 10px; font-weight: 700; letter-spacing: 0.35em; text-transform: uppercase; margin: 0 0 6px; }
  .item h2 { font-size: 16px; font-weight: 700; margin: 0 0 6px; letter-spacing: 0.02em; }
  .domains { font-size: 9.5px; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 14px; }
  .item p { margin: 0 0 14px; text-align: justify; }
  .box { border: 1px solid var(--rule); padding: 16px 18px; margin: 22px 0 6px; font-size: 11.5px; line-height: 1.7; }
  .box h3 { margin: 0 0 8px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.3em; text-transform: uppercase; }
  .box p { margin: 0 0 8px; text-align: left; }
  .box p:last-child { margin-bottom: 0; }
  .watch { border: 2px solid var(--rule); padding: 26px 30px; margin: 10px 0 60px; }
  .watch h3 { margin: 0 0 18px; font-size: 11px; font-weight: 700; letter-spacing: 0.35em; text-transform: uppercase; }
  .watch ul { list-style: none; margin: 0; padding: 0; font-size: 11.5px; }
  .watch li { margin: 0 0 10px; }
  .watch li::before { content: "▸ "; }
  .field { margin: 0 0 10px; text-align: left; }
  .field b { font-size: 9.5px; letter-spacing: 0.25em; text-transform: uppercase; }
  .ids { font-size: 9.5px; color: var(--muted); letter-spacing: 0.04em; margin: 0 0 14px; word-break: break-word; }
  .prompt p { text-align: left; }
  footer { border-top: 1px solid var(--rule); padding-top: 18px; text-align: center; font-size: 10px;
    letter-spacing: 0.12em; line-height: 1.9; }
  @media print {
    body { padding: 0; }
    .page { max-width: 100%; padding: 0; }
    p { orphans: 3; widows: 3; }
    /* Short blocks stay whole, as in the April 28 layout; long blocks
       (domain briefings, leads, the elevated list) may break across pages. */
    .item.keep, .watch, .field, .trajectory, .prompt, footer { break-inside: avoid; }
    .item { break-inside: auto; }
    .section-title, .region, .item h2, .box h3 { break-after: avoid; }
    .item h2, .field { break-inside: avoid; }
  }
"""


def _e(text: str) -> str:
    return html.escape(text, quote=False)


def render_print_html(brief: Brief) -> str:
    validate(brief)
    spec, recs, f = brief.spec, brief.records, facts(brief)
    problems: list[str] = []
    ex = lambda t, w="": _e(expand(t, brief, problems, w))  # noqa: E731
    h: list[str] = []
    a = h.append
    a("<!DOCTYPE html>")
    a('<html lang="en">')
    a("<head>")
    a('<meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width, initial-scale=1">')
    a(f"<title>{MASTHEAD_TITLE} | {_e(_date_line(spec['brief_date']))}</title>")
    a(f"<style>{PRINT_CSS}</style>")
    a("</head>")
    a("<body>")
    a('<div class="page">')
    a('  <header class="masthead">')
    a(f"    <h1>{MASTHEAD_TITLE}</h1>")
    a(f'    <div class="kicker">{_e(MASTHEAD_KICKER)}</div>')
    a(f'    <div class="dateline"><span>{_e(_date_line(spec["brief_date"]))}</span>'
      f'<span>{f["records"]} records · {f["usable"]} model-tier</span></div>')
    a("  </header>")

    a("  <section>")
    a('    <div class="section-title">Executive Summary</div>')
    a('    <article class="item">')
    a(f"      <p>{ex(spec['executive_summary'])}</p>")
    a(f'      <div class="ids">Runs: {_e(", ".join(f["runs"]))} · pack sha256 '
      f'{brief.pack_sha256[:12]} · {f["rules"]} rules-tier and {f["unknown"]} tier-unknown '
      f"records counted, not analysed</div>")
    a("    </article>")
    a("  </section>")

    a("  <section>")
    a('    <div class="section-title">Elevated Signals</div>')
    a(f'    <article class="item keep"><p>{ex(spec["elevated_note"])}</p></article>')
    compact = [e for e in spec.get("elevated") or [] if not e.get("note")]
    for e in [e for e in spec.get("elevated") or [] if e.get("note")]:
        rec = recs[int(e["rowid"])]
        a('    <article class="item keep">')
        a(f'      <div class="region">{_e(rec["signal_source"])} · score '
          f'{_fmt(rec["opportunity_score"])}</div>')
        a(f"      <h2>{ex(e['headline'])}</h2>")
        a(f'      <div class="domains">Gates: {_e(gates_text(rec))} · {_e(rec["classification"])} '
          f'{_fmt(rec["confidence"])} · {_e(tier_label(rec))}</div>')
        if e.get("note"):
            a(f"      <p>{ex(e['note'])}</p>")
        a(f'      <div class="ids">record {_e(rec["record_id"])} · signal {_e(rec["signal_id"])} '
          f'· rowid {rec["rowid"]}</div>')
        a("    </article>")
    if compact:
        a('    <article class="item">')
        a('      <div class="region">Also elevated</div>')
        for e in compact:
            rec = recs[int(e["rowid"])]
            a(f'      <p class="field">{_e(rec["signal_source"])} · score '
              f'{_fmt(rec["opportunity_score"])} · {ex(e["headline"])}<br>'
              f'<span class="ids">{_e(rec["classification"])} {_fmt(rec["confidence"])} · '
              f'record {_e(rec["record_id"])} · signal {_e(rec["signal_id"])} · '
              f'{_e(tier_label(rec))}</span></p>')
        a("    </article>")
    a("  </section>")

    a("  <section>")
    a('    <div class="section-title">Domain Briefings</div>')
    for d in spec["domains"]:
        a('    <article class="item">')
        a(f'      <div class="region">{_e(d["name"])}</div>')
        if d.get("rowids"):
            a('      <div class="domains">Records: ' + _e(" · ".join(
                f"{recs[int(r)]['signal_source']} {_fmt(recs[int(r)]['opportunity_score'])}"
                for r in d["rowids"])) + "</div>")
        for p in d["paragraphs"]:
            a(f"      <p>{ex(p)}</p>")
        t = d.get("trajectory") or {}
        a('      <div class="box trajectory">')
        a("        <h3>Trajectory Assessment</h3>")
        lines = [f"{label}: {ex(t[k])}" for k, label in (
            ("next_48h", "Next 48 hours"), ("seven_day", "7-day outlook"), ("limits", "Limits"))
            if t.get(k)]
        a("        <p>" + "<br>\n        ".join(lines) + "</p>")
        a("      </div>")
        if d.get("rowids"):
            a('      <div class="ids">' + _e(" · ".join(
                recs[int(r)]["record_id"] for r in d["rowids"])) + "</div>")
        a("    </article>")
    a("  </section>")

    a("  <section>")
    a('    <div class="section-title">Story Leads</div>')
    for i, lead in enumerate(spec["leads"]):
        primary = recs[int(lead["rowids"][0])]
        docs = lead["documents"]
        a('    <article class="item lead">')
        a(f'      <div class="region">Lead {i + 1} · {_e(primary["signal_source"])} · score '
          f'{_fmt(primary["opportunity_score"])}</div>')
        a(f"      <h2>{ex(lead['title'])}</h2>")
        a(f'      <div class="domains">Gates: {_e(gates_text(primary))} · '
          f'{_e(tier_label(primary))}</div>')
        a(f'      <div class="ids">Signal: {_e(_signal_line(primary))}</div>')
        for r in lead["rowids"][1:]:
            a(f'      <div class="ids">Supporting: {_e(_signal_line(recs[int(r)]))}</div>')
        a(f'      <p class="field"><b>The question</b><br>{ex(lead["question"])}</p>')
        a('      <p class="field"><b>Who to call</b><br>'
          + "<br>".join(ex(w) for w in lead["who_to_call"]) + "</p>")
        a('      <p class="field"><b>Documents to request (FOIA)</b><br>'
          + "<br>".join(ex(x) for x in docs["foia"]) + "</p>")
        a('      <p class="field"><b>Public records to pull now</b><br>'
          + "<br>".join(ex(x) for x in docs["pull_now"]) + "</p>")
        a(f'      <p class="field"><b>Window</b><br>{ex(lead["window"]["value"])} — '
          f'{ex(lead["window"]["reason"])}</p>')
        a(f'      <p class="field"><b>Confidence</b><br>{_e(lead["confidence"]["level"])} — '
          f'{ex(lead["confidence"]["reason"])}</p>')
        a('      <div class="box prompt">')
        a("        <h3>Claude Prompt</h3>")
        for line in _prompt_text(lead, brief, problems, i):
            a(f"        <p>{_e(line)}</p>")
        a("      </div>")
        a("    </article>")
    a("  </section>")

    if spec.get("watch"):
        a('  <div class="watch">')
        a("    <h3>24-Hour Watch List</h3>")
        a("    <ul>")
        for w in spec["watch"]:
            refs = ", ".join(recs[int(r)]["record_id"] for r in w.get("rowids") or [])
            a(f"      <li>{ex(w['item'])}" + (f" <span class=\"ids\">({_e(refs)})</span>"
                                              if refs else "") + "</li>")
        a("    </ul>")
        a("  </div>")

    not_analysed = [r for r in recs.values() if not _usable(r)]
    a("  <section>")
    a('    <div class="section-title">Records Counted, Not Analysed</div>')
    a('    <article class="item">')
    if not_analysed:
        for r in not_analysed:
            a(f'      <p class="field">{_e(r["signal_source"])} · score '
              f'{_fmt(r["opportunity_score"])} · {_e(tier_label(r))}<br>'
              f'<span class="ids">record {_e(r["record_id"])} · signal {_e(r["signal_id"])} · '
              f'rowid {r["rowid"]}</span></p>')
    else:
        a("      <p>None.</p>")
    a("    </article>")
    a("  </section>")

    a("  <footer>")
    a(f"    WORLD STATE BRIEF · {_e(PUBLISHER_LINE)}<br>")
    a("    Every score, source and id comes from stored cycle records "
      f"(pack sha256 {brief.pack_sha256[:12]}). Not for publication without editor review.")
    a("  </footer>")
    a("</div>")
    a("</body>")
    a("</html>")
    if problems:
        raise BriefValidationError(problems)
    return "\n".join(h) + "\n"


def output_stem(brief: Brief) -> str:
    """Versioned name: date, run ids and pack hash. Never reused for other inputs."""
    runs = "+".join(brief.pack.get("runs") or ["norun"])
    return f"world-state-brief_{brief.spec['brief_date']}_{runs}_{brief.pack_sha256[:8]}"


def write_outputs(brief: Brief, out_dir: Path) -> dict[str, Path]:
    """Validate, render and write .md + .html. Refuses to overwrite anything."""
    md = render_markdown(brief)
    page = render_print_html(brief)
    out_dir = Path(out_dir)
    stem = output_stem(brief)
    paths = {"md": out_dir / f"{stem}.md", "html": out_dir / f"{stem}.html"}
    for p in paths.values():
        if p.exists():
            raise FileExistsError(f"{p} exists; briefs are never overwritten")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths["md"].write_text(md, encoding="utf-8")
    paths["html"].write_text(page, encoding="utf-8")
    meta = {"stem": stem, "rendered_at": datetime.now().astimezone().isoformat(),
            "pack_sha256": brief.pack_sha256, "runs": brief.pack.get("runs"),
            "counts": brief.pack.get("counts"), "leads": len(brief.spec["leads"]),
            "writer": brief.spec.get("writer"), "published": False}
    paths["meta"] = out_dir / f"{stem}.meta.json"
    paths["meta"].write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return paths
