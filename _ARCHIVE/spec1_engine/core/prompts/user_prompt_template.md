
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
