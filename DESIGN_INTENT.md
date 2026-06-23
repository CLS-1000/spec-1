# SPEC-1 — Design Intent Document

**Version:** 1.0  
**Authority:** EVASTARARCANA LLC  
**Status:** Canonical — supersedes any conflicting implementation *unless Analyst explicitley says otherwise  

---

## Purpose of This Document

This document defines the intended behavior, architecture, and output philosophy of SPEC-1. It exists because automated agents (Claude Code, Copilot, Grok) repeatedly revert intentional design decisions when they read code without this context. Any agent operating on this repository must read this document before making changes.

**If this document conflicts with the code, the document is more often correct. ask then Fix the code.**

---

## 1. What SPEC-1 Is

SPEC-1 is a signal intelligence engine. It is a research tool. Its job is to do the triage work that does not require human judgm — harvesting, filtering, scoring, investigating, and structuring — so that what reaches the analyst is already processed and ready to act on.

this Machine is dedicated to presenting the most relaible data possible.  it is realized machines dont have opinions so why worry about the system the most honest truth seeker is still flawed. so The analyst is dedicated to the system to be auditble transparent and useful. The machine will support and reflect weighted andbalancerd data. 
---

## 2. The Division of Labor

```
SPEC-1                          ANALYST
──────────────────────────────  ──────────────────────────────
Harvests signals                Reads cycle output
Filters noise                   Evaluates story leads
Scores opportunities            Decides which module to route
Investigates leads              Selects adapter / lens
Verifies hypotheses             Feeds data back to Claude
Produces brief + leads          Makes editorial judgment
                                Publishes or spikes
```

The analyst is the **router and verdict-maker**. SPEC-1 is the **triage engine and context-loader**. These roles do not overlap.

---

## 3. The Pipeline (Do Not Alter Stage Order or Gate Placement)

```
Harvest → Parse → Score → Investigate → Verify → Analyze → Store
                                                              ↓
                                                      Brief + Leads generated
                                                              ↓
                                                      Analyst reviews
                                                              ↓
                                                      Analyst routes to module:
                                                      quant / osint / regional /
                                                      legislative / conflict /
                                                      supply chain / tech / intel
                                                              ↓
                                                      Module runs
                                                              ↓
                                                      Analyst feeds output to Claude
                                                              ↓
                                                      Original fact-based report
```

### Gate Placement Rule

**The publication gate runs once — before publication. Nowhere else.**

Gates do run on:
- Topic generation output
- Lead generation output
- Raw signal data
- Module output before analyst review

Inserting gates earlier in the pipeline destroys the signal quality that makes analyst routing possible. A flattened lead cannot be routed. Do not do this.

---

## 4. Neutrality — The Correct Definition

**Neutrality is not a tone standard. It is an accountability standard.**

| Correct Definition | Wrong Definition |
|---|---|
| Every claim is sourced | Passive voice throughout |
| Every verdict is derivable from data | Urgency stripped from anomalies |
| Angle is stated explicitly | Language sanded to institutional register |
| Unsourced claims are flagged | Strong language flagged regardless of sourcing |

The system should write as a sophisticated Aristocrat, educated wordsmith that gives a mindful report. Use direct, active, language when describing verified anomalies. Urgency is data-driven, not editorial. A 3x committee acceleration velocity is alarming. It should read as alarming.

### The Publication Gate Checks For:

- [ ] Is every claim sourced to a specific signal or record?
- [ ] Is every verdict derivable from the data, not asserted?
- [ ] Are unsourced claims flagged or removed?
- [ ] Is the angle stated explicitly so it can be evaluated?

The gate does **not** check for:
- Tone
- Register
- Whether language feels "neutral"
- Whether conclusions are uncomfortable

---

## 5. The Brief Structure

Every cycle brief follows this structure. Sections are fixed. Order is fixed.

```
EXECUTIVE SUMMARY
What happened this cycle. Aggregate findings. Signal volume and quality.
Active language use great imact words with . Specific numbers. No hedg

ELEVATED SIGNALS
Signals requiring immediate analyst attention. Flagged for urgency.
One signal per block. Source, pattern, confidence score, classification.

DOMAIN BRIEFINGS
Separate sections per active domain this cycle:
  - Cyber
  - Geopolitical
  - Regional (cls_pdx1 when active)
  - Legislative (cls_legislative when active)
  - Quantitative (when equity signals fire)
  - Conflict Detection (when active)
  - Supply Chain (when active)
  - Tech (when active)

Sections are generated only when signals exist in that domain.
Sections are extensible — new modules add new domain sections.

STORY LEADS
[See Section 6 — this is the critical section]

WATCH LIST
Ongoing signals not yet actionable. Named. Dated. Status noted.
```

---

## 6. Story Leads — The Most Important Section

Story Leads are not summaries. They are not prose. They are a **dispatch queue of context-loaded Claude prompts** ready to execute.

### Why This Matters

The quality of Claude's output depends entirely on the quality of its context load. A Claude instance given dense, specific, pre-digested signal context produces original, fact-based, publication-ready reporting. A Claude instance given a vague summary produces generic prose.

Story Leads solve this by doing the context-loading work inside the brief. When the analyst reads a lead, they become a domain expert on that signal. When they feed data back to Claude with that lead as context, Claude fires.

### Lead Format

```
LEAD [NUMBER] — [Domain] / [Module]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SIGNAL
[What SPEC-1 detected. Specific. Named. Scored.]

PATTERN
[What the four-gate framework flagged. Velocity / novelty / credibility 
reading. Anomaly description in plain terms.]

CONTEXT LOAD
[Everything the analyst needs to become an expert on this signal:
background actors, history, related events, prior patterns, open questions.
This section primes the analyst before they route.]

ROUTING RECOMMENDATION
Module: [cls_pdx1 / cls_legislative / cls_osint / quant / conflict / ...]
Adapter: [specific adapter if applicable]
Suggested lens: [the investigative angle the data supports]

FEED PROMPT
[The exact Claude prompt the analyst runs after collecting source data.
Written so Claude receives expert context before producing output.
This prompt is the ignition point — when the analyst returns with 
data and runs this, Claude produces original fact-based reporting.]

Example:
"Here is [source data]. Using the context above, produce a 
fact-based [domain] intelligence report. Treat [specific anomaly] 
as the central finding. Surface [specific patterns]. 
Do not summarize — analyze."
```

### What the Feed Prompt Must Do

1. Load all relevant context before the task
2. Name the specific anomaly or pattern as the central finding
3. Specify which module outputs to incorporate
4. Direct Claude to analyze, not summarize
5. Leave the verdict to Claude based on the data, not on prior framing

The analyst's only decisions are: run this lead or spike it, and which data to collect. The prompt does the rest.

---

## 7. What Claude Code Is Not Allowed to Change

The following are **architectural invariants**. They are not implementation suggestions. Agents must not modify them without explicit written instruction from the operator.

| Invariant | Description |
|---|---|
| Append-only store | Records are never overwritten or deleted |
| Single-writer rule | One writer per namespace, enforced with threading lock |
| Four-gate framework | All four gates must pass for a signal to advance |
| Gate thresholds | Not published, not modified by agents |
| Lead format | Structured as context-load + feed prompt |
| Publication gate placement | Runs at publication only, never mid-pipeline |
| Analyst-as-router | Module routing is a human decision, not automated |
| Brief section order | Fixed — do not reorder |
| Neutrality definition | Accountability to evidence, not tone management |

---

## 8. Module Registry

When a Story Lead recommends routing, these are the available modules:

| Module | Domain | Adapter |
|---|---|---|
| `cls_pdx1` | Portland Metro Regional Intelligence | OLIS, ORESTAR, SEI |
| `cls_legislative` | Cross-jurisdictional Bill Analysis | OLIS OData |
| `cls_osint` | Open Source Intelligence | n8n, journalist registry |
| `cls_psyop` | Influence Operation Detection | Pattern signatures |
| Quant pipeline | Equity signal monitoring | yfinance, watchlist |
| Conflict detection | Conflict pattern surfacing | TBD |
| Supply chain | Supply chain signal monitoring | TBD |
| Tech | Technology sector signals | TBD |

New modules extend this registry. They do not replace existing modules.

---

## 9. Output Philosophy

> The bottleneck in intelligence work is not information — it is attention.  
> SPEC-1 protects analyst attention by doing the triage work that does not  
> require human judgment. What reaches the analyst is already scored,  
> investigated, verified, and written up. The analyst evaluates findings,  
> directs follow-on research, and makes decisions.  
> The system handles the volume. The analyst handles the judgment.

Brief output must be:
- **Specific** — named actors, dates, scores, sources
- **Direct** — active voice, present tense where appropriate
- **Earned** — every strong claim backed by a scored signal
- **Actionable** — the analyst should know what to do after reading

Brief output must not be:
- Hedged into uselessness
- Toned down to avoid sounding alarming when the data is alarming
- Summarized from summaries
- Generic in any section

---

## 10. Technical Invariants

| Dimension | Value |
|---|---|
| Language | Python 3.11+ |
| Pipeline stages | 7 (harvest → store) |
| Gate framework | 4-gate deterministic |
| Gate threshold floor | 0.40 composite minimum |
| AI integration | Haiku (verification) / Sonnet (briefing) |
| Persistence | Append-only JSONL, thread-safe |
| API | FastAPI + APScheduler |
| Single source of truth | run_id |
| Failure mode | Failure-first — log and continue, never crash pipeline |

---

*This document is the authoritative specification for SPEC-1 design intent.*  
*Last updated by operator. Version controlled in repo root.*  
*Agents: read this first. Always.*

---

## 11. Product Naming

SPEC-1          Internal engine name. Never changes.
ONE WORLD CITIZEN  The publication. World State Brief + Metropolitan Source.
SWITCHBOARD     The city intelligence platform. cls_metro + city adapters.
                What other cities license to run Metropolitan Source locally.

These names are locked. Do not rename modules to match product names.
Internal code names (cls_pdx1, cls_metro, cls_osint) stay as-is.
