# @domain:   publisher
# @module:   briefing_generator
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core/schemas

"""Daily intelligence brief generator.

Local-first: the brief is written by Qwen 2.5 on the local Ollama server,
then Claude Sonnet if Ollama is unavailable, then a rule-based raw-stats brief
if both fail — never crashes the cycle.
"""

import os
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

import logging
import re
from datetime import datetime, timezone


from spec1_labels import BRIEF_RULE_FALLBACK_NOTE, VERIF_CORROBORATED
from spec1_core.briefing.templates import (
    GEO_SYSTEM_PROMPT,
    GEO_USER_PROMPT_TEMPLATE,
    LEG_SYSTEM_PROMPT,
    LEG_USER_PROMPT_TEMPLATE,
)
from spec1_core.briefing.brief_package_templates import BRIEF_SYSTEM, BRIEF_USER, LEAD_PACKET_USER

try:
    from zoneinfo import ZoneInfo
    _PT_ZONE: object = ZoneInfo("America/Los_Angeles")
except Exception:
    from datetime import timedelta
    _PT_ZONE = timezone(timedelta(hours=-7))

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000

# Sources that map to Cyber / Info Ops domain
_CYBER_SOURCES = {
    "cipher_brief", "just_security", "lawfare",
    "cyberscoop", "recordedfuture", "krebs",
}

# Sources that map to Geopolitics domain
_GEO_SOURCES = {
    "war_on_the_rocks", "rand", "atlantic_council",
    "defense_one", "foreign_affairs", "bellingcat",
}


def _classify_domain(record: dict) -> str:
    """Return 'cyber' or 'geo' based on signal source."""
    src = str(record.get("signal_source", "")).lower()
    if src in _CYBER_SOURCES:
        return "cyber"
    return "geo"


def _format_record(record: dict) -> str:
    """Format a single record for the prompt — readable, not raw JSON."""
    source = record.get("signal_source", record.get("source", "unknown"))
    pattern = record.get("pattern", "—")
    confidence = record.get("confidence", record.get("outcome_confidence", 0.0))
    classification = record.get("outcome_classification", record.get("classification", "—"))
    priority = record.get("opportunity_priority", "—")
    url = record.get("signal_url", "")
    url_str = f" | {url}" if url else ""
    line = (
        f"{source.upper()} | {pattern} | "
        f"confidence={float(confidence):.2f} | classification={classification} | "
        f"priority={priority}{url_str}"
    )
    excerpt = str(record.get("signal_excerpt") or "").strip()
    reasoning = str(record.get("llm_reasoning") or "").strip()
    if excerpt:
        line += f"\n    Excerpt: {excerpt}"
    if reasoning:
        line += f"\n    Model assessment: {reasoning}"
    return line


def _build_prompt(records: list[dict], cycle_stats: dict, mode: str = "standard") -> str:
    """Build the filled prompt template string for the given mode."""
    elevated = [
        r for r in records
        if r.get("outcome_classification", r.get("classification", "")) in (VERIF_CORROBORATED, "ESCALATE")
    ]
    remaining = [r for r in records if r not in elevated]
    standard_top10 = sorted(
        remaining,
        key=lambda r: float(r.get("confidence", r.get("outcome_confidence", 0.0))),
        reverse=True,
    )[:10]

    geo_count = sum(1 for r in records if _classify_domain(r) == "geo")
    cyber_count = sum(1 for r in records if _classify_domain(r) == "cyber")

    elevated_block = (
        "\n".join(_format_record(r) for r in elevated)
        if elevated else "(none)"
    )
    standard_block = (
        "\n".join(_format_record(r) for r in standard_top10)
        if standard_top10 else "(none)"
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pt_now = datetime.now(_PT_ZONE)
    date_long = pt_now.strftime("%A, %d %B %Y")
    time_pt = pt_now.strftime("%H:%M")
    _doms = []
    if geo_count > 0:
        _doms.append("Geopolitics")
    if cyber_count > 0:
        _doms.append("Cyber · Info Ops")
    active_domains = " · ".join(_doms) if _doms else "—"
    issue_number = cycle_stats.get("issue_number", "—")

    # Format evidence chains for the template
    raw_chains: list[dict] = cycle_stats.get("psyop_evidence_chains", [])
    if raw_chains:
        chain_blocks = []
        for ec in raw_chains:
            sources_str = ", ".join(
                m.get("source", "") for m in ec.get("source_metadata", [])
            ) or "—"
            excerpts = ec.get("raw_excerpts", [])
            excerpts_str = " | ".join(
                f"[{x.get('source', '')}] {x.get('text_snippet', '')[:200]}"
                for x in excerpts[:3]
            ) or "—"
            xrefs = ec.get("cross_references", [])
            xrefs_str = ", ".join(xrefs[:5]) or "none"
            block = (
                f"  Pattern: {ec.get('pattern_name', '—')} | "
                f"Confidence: {ec.get('confidence', 0.0):.2f}\n"
                f"  Summary: {ec.get('summary', '—')}\n"
                f"  Sources: {sources_str}\n"
                f"  Excerpts: {excerpts_str}\n"
                f"  Cross-references: {xrefs_str}"
            )
            chain_blocks.append(block)
        evidence_chains_str = "\n\n".join(chain_blocks)
    else:
        evidence_chains_str = "(none)"

    if mode == "geopolitics":
        tmpl = GEO_USER_PROMPT_TEMPLATE
    elif mode == "legislative":
        tmpl = LEG_USER_PROMPT_TEMPLATE
    else:
        tmpl = BRIEF_USER

    return tmpl.format(
        run_id=cycle_stats.get("run_id", "—"),
        timestamp=cycle_stats.get("finished_at", cycle_stats.get("timestamp", "—")),
        signal_count=cycle_stats.get("signals_harvested", cycle_stats.get("signal_count", 0)),
        opportunity_count=cycle_stats.get("opportunities_found", 0),
        record_count=cycle_stats.get("records_stored", cycle_stats.get("record_count", len(records))),
        elevated_count=len(elevated),
        elevated_records=elevated_block,
        standard_records=standard_block,
        geo_count=geo_count,
        cyber_count=cyber_count,
        date=date_str,
        date_long=date_long,
        time_pt=time_pt,
        active_domains=active_domains,
        issue_number=issue_number,
        psyop_classification=cycle_stats.get("psyop_classification", "—"),
        psyop_score=cycle_stats.get("psyop_score", "—"),
        psyop_patterns_fired=cycle_stats.get("psyop_patterns_fired", []),
        evidence_count=len(raw_chains),
        evidence_chains=evidence_chains_str,
    )


def _record_conf(record: dict) -> float:
    try:
        return float(record.get("confidence", record.get("outcome_confidence", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _record_summary(record: dict, limit: int = 160) -> str:
    """One-line human-readable summary of a record's pattern text."""
    text = str(record.get("pattern", "—")).split(" | gates=")[0]
    text = " ".join(re.sub(r"^\s*\[[A-Z]+\]\s*", "", text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _fallback_brief(
    cycle_stats: dict,
    records: list[dict] | None = None,
    reason: str = "API key not configured",
) -> str:
    """Rule-based brief in the canonical layout. No LLM required.

    Marks ``cycle_stats["brief_fallback"] = True`` so the caller (and the
    publish guard) know this brief is rule-based, not model output.
    """
    cycle_stats["brief_fallback"] = True
    records = records or []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = cycle_stats.get("run_id", "—")
    harvested = cycle_stats.get("signals_harvested", 0)
    opportunities = cycle_stats.get("opportunities_found", 0)
    stored = cycle_stats.get("records_stored", 0)
    errors = cycle_stats.get("errors", [])
    finished = cycle_stats.get("finished_at", "—")

    elevated = [
        r for r in records
        if r.get("outcome_classification", r.get("classification", "")) in (VERIF_CORROBORATED, "ESCALATE")
    ]
    remaining = sorted(
        (r for r in records if r not in elevated), key=_record_conf, reverse=True
    )
    geo = [r for r in remaining if _classify_domain(r) == "geo"][:5]
    cyber = [r for r in remaining if _classify_domain(r) == "cyber"][:5]

    def _bullet(r: dict) -> str:
        url = r.get("signal_url", "")
        url_str = f" <{url}>" if url else ""
        return (
            f"- **{str(r.get('signal_source', 'unknown')).upper()}** — {_record_summary(r)} "
            f"(confidence {_record_conf(r):.2f}){url_str}"
        )

    lines = [
        f"## SPEC-1 DAILY BRIEF — {date_str}",
        "",
        f"*AI brief unavailable — {reason}. {BRIEF_RULE_FALLBACK_NOTE}.*",
        "",
        f"**Run:** {run_id}  ",
        f"**Completed:** {finished}  ",
        f"**Signals harvested:** {harvested}  ",
        f"**Opportunities found:** {opportunities}  ",
        f"**Records stored:** {stored}",
        "",
        "### Executive Summary",
        f"The cycle harvested {harvested} signals, {opportunities} cleared all four gates "
        f"and {stored} records were stored. {len(elevated)} record(s) were elevated "
        "(CORROBORATED or ESCALATE). No narrative synthesis was performed; "
        "treat every entry as unverified until reviewed.",
        "",
        "### Elevated Signals",
    ]
    if elevated:
        lines += [_bullet(r) for r in sorted(elevated, key=_record_conf, reverse=True)]
    else:
        lines.append("No signals cleared the elevated threshold this cycle.")

    lines += ["", "### Domain Briefings", "", "**Geopolitics**"]
    lines += [_bullet(r) for r in geo] or ["No geopolitics signals this cycle."]
    lines += ["", "**Cyber / Info Ops**"]
    lines += [_bullet(r) for r in cyber] or ["No cyber / info-ops signals this cycle."]

    patterns = cycle_stats.get("psyop_patterns_fired", [])
    chains = cycle_stats.get("psyop_evidence_chains", [])
    lines += ["", "**Psyop / Narrative Analysis**"]
    if chains:
        for ec in chains:
            lines.append(
                f"- {ec.get('pattern_name', '—')} "
                f"(confidence {float(ec.get('confidence', 0.0)):.2f}): {ec.get('summary', '—')}"
            )
    else:
        lines.append("No psyop patterns detected this cycle.")

    lines += ["", "### Story Leads"]
    lead_pool = (sorted(elevated, key=_record_conf, reverse=True) + remaining)[:3]
    if lead_pool:
        for r in lead_pool:
            lines += [
                "",
                f"**LEAD: {_record_summary(r, 90)}**",
                f"Signal: {r.get('signal_source', 'unknown')}, "
                f"confidence {_record_conf(r):.2f}",
                f"The question: {_record_summary(r, 200)}",
                f"Documents to request: {r.get('signal_url') or '—'}",
                f"Confidence: {'HIGH' if _record_conf(r) >= 0.7 else 'MEDIUM' if _record_conf(r) >= 0.4 else 'LOW'}",
            ]
    else:
        lines.append("No leads this cycle.")

    lines += ["", "### Watch List — Tomorrow"]
    watch = (sorted(elevated, key=_record_conf, reverse=True) + remaining)[:3]
    lines += [f"- {r.get('signal_source', 'unknown')}: {_record_summary(r, 100)}" for r in watch] \
        or ["- Nothing to monitor."]

    lines += [
        "",
        "### Psyop Assessment",
        f"Classification: {cycle_stats.get('psyop_classification', '—')} · "
        f"Score: {cycle_stats.get('psyop_score', '—')} · "
        f"Patterns fired: {', '.join(patterns) if patterns else 'none'}",
        "",
        "### Signal Notes",
    ]
    if errors:
        lines.append(f"**Harvest errors ({len(errors)}):**")
        lines += [f"  - {e}" for e in errors]
    else:
        lines.append("No harvest errors this cycle.")
    return "\n".join(lines)


def build_brief_prompts(records: list[dict], cycle_stats: dict, mode: str = "standard") -> tuple[str, str]:
    """(system prompt, filled user prompt) for a run — exactly what the API would get."""
    if mode == "geopolitics":
        sys_prompt = GEO_SYSTEM_PROMPT
    elif mode == "legislative":
        sys_prompt = LEG_SYSTEM_PROMPT
    else:
        sys_prompt = BRIEF_SYSTEM
    return sys_prompt, _build_prompt(records, cycle_stats, mode=mode)


def _feed_prompt_format() -> str:
    """The FEED PROMPT block of the Lead Packet template, verbatim.

    The brief's Story Leads section says to use the Lead Packet format and
    that the feed prompt is mandatory; without this block a hand-written
    brief has no format to follow.
    """
    start = LEAD_PACKET_USER.find("F E E D   P R O M P T")
    end = LEAD_PACKET_USER.find("ROUTING", start)
    if start < 0 or end < 0:
        return ""
    return LEAD_PACKET_USER[start:end].rstrip(" ━\n") + "\n"


def handoff_doc(records: list[dict], cycle_stats: dict, mode: str = "standard") -> str:
    """One file to hand to Claude by hand (chat, not API) to write the brief.

    Contains the same system and user prompt the API path sends, so a brief
    written from it follows the same house rules. No API key needed.
    """
    sys_prompt, user_prompt = build_brief_prompts(records, cycle_stats, mode=mode)
    run_id = cycle_stats.get("run_id", "unknown")
    return (
        f"# SPEC-1 brief handoff — {run_id}\n\n"
        f"Records: {len(records)} · Mode: {mode} · "
        f"Analysis tier: {cycle_stats.get('records_tier', 'unknown')} "
        f"{cycle_stats.get('analysis_tiers', {})}\n\n"
        "If the tier is rule_based, these records were not checked by a model: "
        "do not write a publishable brief from them.\n\n"
        "How to use: give this whole file to Claude and ask for the brief. "
        "Section 1 is the standing instruction set; section 2 is this run's data.\n\n"
        "---\n\n"
        f"## 1. Instructions\n\n{sys_prompt.strip()}\n\n"
        "---\n\n"
        f"## 2. This run\n\n{user_prompt.strip()}\n"
        + (f"\n---\n\n## 3. Feed prompt format (every Story Lead carries one)\n\n{feed}"
           if (feed := _feed_prompt_format()) else "")
    )


def _require_content(brief: str, backend: str) -> None:
    """Raise if *brief* is below the content floor, so the caller falls through a tier."""
    from spec1_core.briefing.writer import BRIEF_MIN_WORDS, brief_content_words

    words = brief_content_words(brief)
    if words < BRIEF_MIN_WORDS:
        raise ValueError(f"{backend} returned a degenerate brief ({words} words, minimum {BRIEF_MIN_WORDS})")


def generate_brief(records: list[dict], cycle_stats: dict, mode: str = "standard") -> tuple[str, str]:
    """Generate the daily intelligence brief: local Qwen 2.5, then Claude, then rules.

    ``cycle_stats["brief_backend"]`` records which model wrote it ("local" or
    "claude"); the rule-based path sets ``brief_fallback`` instead.

    Returns a (brief, prompts_text) tuple where *brief* is the generated
    markdown and *prompts_text* is the full prompts payload (system + user)
    that was sent to the model.  On any failure the brief is a fallback
    string; prompts_text is still populated when available.
    Never raises.

    mode: "standard" (default SPEC-1 brief), "geopolitics" (Geopolitics & Policy Desk),
          or "legislative" (Legislative & Judicial Desk).
          Legislative mode is triggered by cls_legislative when that module
          feeds into the brief pipeline. Not yet auto-triggered by cycle.py.
    """
    try:
        sys_prompt, user_prompt = build_brief_prompts(records, cycle_stats, mode=mode)
        prompts_text = f"## SYSTEM PROMPT\n\n{sys_prompt.strip()}\n\n---\n\n## USER PROMPT\n\n{user_prompt.strip()}\n"
    except Exception as exc:
        logger.error("Brief prompt build failed: %s", exc)
        return _fallback_brief(cycle_stats, records, reason="prompt build failed"), ""

    # Tier 1: local Qwen 2.5 via Ollama.
    try:
        from spec1_core.llm.fallback_client import LocalTier3Client

        brief = LocalTier3Client().chat(user_prompt, system_prompt=sys_prompt)
        _require_content(brief, "local model")
        cycle_stats["brief_backend"] = "local"
        logger.info("Brief generated via local qwen2.5 (mode=%s) — %d words", mode, len(brief.split()))
        return brief, prompts_text
    except Exception as exc:
        print(f"[briefing] Local model unavailable: {type(exc).__name__}: {exc}")
        logger.warning("Local brief generation failed: %s", exc)

    # Tier 2: Anthropic Claude.
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip().lstrip('\ufeff')
    if not api_key:
        print("[briefing] ANTHROPIC_API_KEY not set in environment — returning fallback brief")
        logger.warning("ANTHROPIC_API_KEY not set — returning fallback brief")
        return _fallback_brief(
            cycle_stats, records, reason="local model unavailable and API key not configured"
        ), prompts_text

    try:
        import anthropic  # only needed when Claude is called from here

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=sys_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        brief = message.content[0].text.strip()
        _require_content(brief, "Claude")
        cycle_stats["brief_backend"] = "claude"
        logger.info("Brief generated via Claude (mode=%s) — %d words", mode, len(brief.split()))
        return brief, prompts_text
    except Exception as exc:
        print(f"[briefing] API call failed: {type(exc).__name__}: {exc}")
        logger.error("Brief generation failed: %s", exc)
        return _fallback_brief(
            cycle_stats, records, reason="local model unavailable and API call failed"
        ), prompts_text
