
Today's cycle: {run_id}
Completed: {timestamp}
Signals harvested: {signal_count}
Opportunities scored: {opportunity_count}
Records written: {record_count}

ELEVATED SIGNALS ({elevated_count}):
{elevated_records}

STANDARD SIGNALS — TOP 10 BY CONFIDENCE:
{standard_records}

DOMAIN BREAKDOWN:
Geopolitics: {geo_count} signals
Cyber / Info Ops: {cyber_count} signals

PSYOP / NARRATIVE DETECTION:
psyop_classification: {psyop_classification}
psyop_score: {psyop_score}
patterns_fired: {psyop_patterns_fired}

Evidence chains ({evidence_count}):
{evidence_chains}

Write the daily Geopolitics & Policy Desk brief using this exact structure:

---

## GEOPOLITICS & POLICY DESK — {date}

### Executive Summary
[High-level overview of the most critical verified developments. Focus on the intersection
of global geopolitical events and domestic policy. 3-5 sentences. What happened, why it
matters, what remains uncertain.]

### The Geopolitics Brief
[Synthesize the top geopolitical signals — strategic realignments, energy security hedges,
conflict zone updates. Explain *why* these signals matter and point out any coordinated
framing or influence operations detected. Patterns, not lists. 2-4 paragraphs.]

### Capitol Hill & Lobbying Watch
[Analyze signals from Congressional sources and FARA filings. Highlight:
- New legislation or committee hearings introduced.
- Foreign lobbying money tracked against U.S. lawmakers.
- Any Conflicts of Interest based on member financial disclosures vs. committee assignments.
If no FARA or congressional signals exist this cycle, say so explicitly.]

### Local Government Impact
[Summarize local government signals. Connect local developments to broader federal or
geopolitical trends where applicable. If no local signals exist, say so in one sentence.]

### Actionable Story Leads
[2-3 specific, actionable leads for investigative reporters. Each lead must follow this
exact format:

**LEAD: [Headline-style title]**
Signal: [source name, pattern summary, confidence score]
**The Question:** [The core anomaly or mystery a reporter needs to answer.]
**Who to Call:** [Specific agencies, cleared staff, or domain experts to contact.]
**Documents to Request:** [Exact public records, FOIA requests, budget amendments, or dockets to pull.]
**Window & Confidence:** [Freshness window (e.g., 72 hours) and the composite confidence score.]

> **CLAUDE PROMPT:**
> "You are an investigative journalist working this lead: [lead title].
>  The signal: [signal description, source, confidence score].
>  The core question: [the question].
>
>  Step 1 — Draft a 3-paragraph background memo on this topic using
>  only publicly available information. Cite specific sources.
>
>  Step 2 — Write 5 specific questions for [who to call].
>  Each question should be answerable with a yes/no or a specific fact.
>  Avoid open-ended questions that give a spokesperson room to deflect.
>
>  Step 3 — Write a FOIA request draft targeting [documents to request].
>  Use formal FOIA language. Specify the agency, the date range,
>  and the specific records requested.
>
>  Step 4 — Write a 150-word pitch memo for an editor meeting.
>  State the story, the stakes, what you have, what you still need."

Do not invent leads. Every lead traces to a scored signal.
Every lead must include the CLAUDE PROMPT blockquote — it is not optional.]

---
