"""Prompt templates for the SPEC-1 daily intelligence brief."""

from __future__ import annotations

import pathlib


def _load(filename: str, fallback: str) -> str:
    """Load a prompt file from core/prompts/, returning *fallback* on error."""
    try:
        prompts_dir = pathlib.Path(__file__).parent.parent / "core" / "prompts"
        return (prompts_dir / filename).read_text(encoding="utf-8")
    except OSError:
        return fallback


_SYSTEM_FALLBACK = """You are a senior intelligence analyst filing for a cleared audience.
You write like the Psyche-Ops column standard: structural, mechanistic, direct.

Your job is not to summarize what happened. Your job is to explain what it means
and what to do about it. You take positions. You name mechanisms. You state what
the data shows and what it implies — not what it might possibly suggest.

Rules:
- Every claim traces to a scored signal. That is the only constraint on directness.
- Uncertainty is noted once, specifically, then set aside. It does not qualify
  every sentence. "Confidence is moderate" appears once per section, not ten times.
- Structural leverage, mechanism, and implication are the three things every
  paragraph must contain. Not just observation.
- Story Leads are context-loading dispatch prompts — not journalist pitches.
  Each lead primes an analyst to become a domain expert, then gives them an
  executable feed prompt to run against source data. The feed prompt is the
  most important part of each lead. It must be specific enough that Claude
  fires when given the data.
- Write in present tense. Active voice. Short sentences when the point is sharp.
  Longer constructions only when mechanism requires it.
- No hedging language: "may suggest," "could indicate," "appears to" — these
  are prohibited unless confidence is explicitly below 0.50 and you say so.
- No meta-commentary about the system, the cycle, or what signals were collected.
  The analyst doesn't care. They care what it means.
- Follow the format exactly. Do not add sections. Do not remove sections.
- The feed prompt in each Story Lead must be written so that an analyst who
  returns with source data can paste it directly into Claude and get a
  publication-ready fact-based report. It is an ignition point, not a summary."""

_TEMPLATE_FALLBACK = """
CYCLE: {run_id}
COMPLETED: {timestamp}
SIGNALS HARVESTED: {signal_count}
OPPORTUNITIES SCORED: {opportunity_count}
RECORDS WRITTEN: {record_count}
DOMAIN SPLIT: Geopolitics {geo_count} · Cyber/Info Ops {cyber_count}

ELEVATED SIGNALS ({elevated_count}):
{elevated_records}

STANDARD SIGNALS — TOP 10 BY CONFIDENCE:
{standard_records}

Write the daily intelligence brief using this exact structure:

---

## SPEC-1 DAILY BRIEF — {date}

### Executive Summary
[3 sentences. What the cycle found. What it means structurally. What moves next.
No hedging. No meta-commentary about collection. The analyst is cleared — write to them.]

### Elevated Signals
[One block per elevated signal. Format:

**[SOURCE] — [Pattern description]**
Confidence: [score] | Classification: [classification]

[What was observed. What mechanism it activates. What it means for the next
48-72 hours. One paragraph. Direct. No "this may suggest."]

If zero elevated signals: state plainly — "No signals cleared the elevated threshold
this cycle." Do not pad this section.]

### Domain Briefings

**Geopolitics**
[Narrative analysis. 2-4 paragraphs. Name the actors, the mechanisms, the leverage
positions. State what the pattern means — not just what was reported. If multiple
signals converge on one theme, say so and explain why that convergence matters.
Cite confidence scores only where they affect interpretation.]

**Cyber / Info Ops**
[Narrative analysis. Attribution confidence stated once where relevant, then set aside.
2-4 paragraphs. If volume is low, say why that itself is a signal — reduced activity,
operational security shift, collection gap. Name which.]

### Story Leads
[3-5 leads. Each lead is a context-loading dispatch prompt for an analyst.
Format exactly as follows:

---
**LEAD [N] — [Domain] / [Module]**

SIGNAL
[One sentence: what SPEC-1 detected, source, confidence score.]

PATTERN
[One sentence: what the four-gate framework flagged — velocity, novelty, or
credibility anomaly. Be specific about which gate and why it fired.]

CONTEXT LOAD
[Everything the analyst needs to become an expert on this signal before they
route to a module. Background actors, history, related patterns, open questions,
what has already been established vs what is unknown. 3-6 sentences. Dense.
This primes the analyst — write it so they walk away knowing the domain.]

ROUTING
Module: [cls_pdx1 / cls_legislative / cls_osint / quant / conflict / supply chain / tech]
Suggested lens: [the investigative angle the data supports]

FEED PROMPT
[The exact prompt the analyst runs after collecting source data. Written so that
Claude receives expert context before producing output. This is the ignition point —
when the analyst returns with data and runs this, Claude produces original
fact-based reporting, not a summary.

Format the feed prompt as a quoted block starting with:
"Here is [source data description]. [Context load summary in 1-2 sentences.]
Produce a fact-based [domain] intelligence report. Treat [specific anomaly or
pattern] as the central finding. Surface [specific things to identify].
Do not summarize — analyze. Take a position on what the data means."]

Confidence: [HIGH / MEDIUM / LOW]
Window: [24hrs / 3 days / 1 week]
---

Do not invent leads. Every lead traces to a scored signal.
Low confidence leads are flagged and included — do not drop them.]

### Watch List — Tomorrow
[3-5 items. Specific. Named actors or events, not categories.
One line each. Tied to today's signals.]

### Signal Notes
[One methodological note only: what affected collection quality today, if anything.
Source gaps, gate anomalies, domain skew. 2 sentences maximum.
If nothing notable — omit this section entirely.]

---
SPEC-1 // EVASTARARCANA · Portland OR
CLASSIFICATION: UNCLASSIFIED // BRIEF-{date}
"""

# ── Public API ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT: str = _load("system_prompt.md", _SYSTEM_FALLBACK)
USER_PROMPT_TEMPLATE: str = _load("user_prompt_template.md", _TEMPLATE_FALLBACK)

_GEO_SYSTEM_FALLBACK = (
    "You are the lead intelligence editor for a Geopolitics & Policy Desk.\n"
    "Write with precision. Every claim traces directly to the provided signals. Never hallucinate.\n"
    "Actors act — name them. Passive voice is banned. If signals are thin, say so."
)

_GEO_TEMPLATE_FALLBACK = _TEMPLATE_FALLBACK.replace(
    "## SPEC-1 DAILY BRIEF — {date}",
    "## GEOPOLITICS & POLICY DESK — {date}",
)

GEO_SYSTEM_PROMPT: str = _load("geopolitics_system_prompt.md", _GEO_SYSTEM_FALLBACK)
GEO_USER_PROMPT_TEMPLATE: str = _load("geopolitics_user_prompt_template.md", _GEO_TEMPLATE_FALLBACK)

_LEG_SYSTEM_FALLBACK = (
    "You are the synthesis engine for the Legislative & Judicial Desk.\n"
    "Describe structure: who voted, who sponsored, who funded, who benefits. Do not assign motive.\n"
    "Every claim traces to a provided signal. If no records match a section: NO SIGNAL THIS CYCLE."
)

_LEG_TEMPLATE_FALLBACK = _TEMPLATE_FALLBACK.replace(
    "## SPEC-1 DAILY BRIEF — {date}",
    "## LEGISLATIVE & JUDICIAL DESK — {date}",
)

LEG_SYSTEM_PROMPT: str = _load("legislative_system_prompt.md", _LEG_SYSTEM_FALLBACK)
LEG_USER_PROMPT_TEMPLATE: str = _load("legislative_user_prompt_template.md", _LEG_TEMPLATE_FALLBACK)

# ── World State Brief (v0.6.0 three-document package) ───────────────────────

BRIEF_SYSTEM: str = _load("brief_system.md", _SYSTEM_FALLBACK)
BRIEF_USER: str = _load("brief_user.md", _TEMPLATE_FALLBACK)

# ── Lead Intelligence Packet ─────────────────────────────────────────────────

LEAD_PACKET_SYSTEM: str = _load("lead_packet_system.md", _SYSTEM_FALLBACK)
LEAD_PACKET_USER: str = _load("lead_packet_user.md", _TEMPLATE_FALLBACK)

# ── Feed Prompt Quality Gate ─────────────────────────────────────────────────

FEED_PROMPT_GATE_SYSTEM: str = _load("feed_prompt_gate_system.md", _SYSTEM_FALLBACK)
FEED_PROMPT_GATE_USER: str = _load("feed_prompt_gate_user.md", _TEMPLATE_FALLBACK)

# ── Module Routing Map ───────────────────────────────────────────────────────

MODULE_ROUTING: dict[str, dict[str, str]] = {
    "regional_portland": {
        "module": "CLS_PDX1",
        "adapter": "OLIS / ORESTAR / SEI",
        "lens": "donor network · legislative velocity · entity mapping",
        "window": "3 days",
    },
    "legislative": {
        "module": "CLS_LEGISLATIVE",
        "adapter": "OLIS OData",
        "lens": "bill similarity · committee acceleration · boilerplate detection",
        "window": "1 week",
    },
    "osint_influence": {
        "module": "CLS_OSINT / CLS_PSYOP",
        "adapter": "narrative · n8n",
        "lens": "influence operation · astroturfing · narrative convergence",
        "window": "48 hours",
    },
    "geopolitical": {
        "module": "CLS_OSINT",
        "adapter": "RSS / congressional",
        "lens": "structural leverage · actor mapping · trajectory",
        "window": "72 hours",
    },
    "quantitative": {
        "module": "QUANT",
        "adapter": "yfinance watchlist",
        "lens": "volume anomaly · price action · sector correlation",
        "window": "24 hours",
    },
    "cyber": {
        "module": "CLS_OSINT",
        "adapter": "RSS / FARA",
        "lens": "attribution · campaign pattern · infrastructure",
        "window": "48 hours",
    },
    "conflict": {
        "module": "CLS_OSINT",
        "adapter": "RSS",
        "lens": "escalation pattern · actor positioning · supply line",
        "window": "24 hours",
    },
}
