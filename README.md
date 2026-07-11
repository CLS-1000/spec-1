# SPEC-1: Automated Research Engine

**Version:** 0.6.0 | **Status:** Production-Ready  
**Organization:** EVASTARARCANA LLC • Portland, OR

---

## The Problem

Public information is everywhere. Finding the signal inside it is the job.

Every day, credible reporting flows from dozens of authoritative public sources — congressional records, FARA filings, think tank publications, newswires, civic databases. The problem isn't access. It's triage. By the time a journalist or researcher manually works through the week's feeds, the story has moved.

SPEC-1 does the triage work automatically so you can focus on the reporting.

---

## What SPEC-1 Is

SPEC-1 is an automated open-source research engine. It monitors 40+ curated public sources, filters every signal through a deterministic four-gate pipeline, and produces structured research reports written to the standard of serious long-form journalism.

The engine writes the first draft. You filter length and tone. You decide what to publish.

**Built for:** journalists, investigative reporters, nonprofit researchers, policy analysts, students, and small organizations doing civic and public-interest work.

---

## How It Works

### The Four-Gate Filter

Every signal passes through four independent gates. All four must pass or the signal is discarded. Nothing reaches a report that hasn't cleared every gate.

| Gate | What It Checks |
|------|---------------|
| **Source credibility** | Known source with a verified track record |
| **Substance** | Enough content to be meaningful |
| **Freshness** | Recent enough to act on |
| **Novelty** | Contains indicators of something new or unusual |

Every gate decision is logged. You can see exactly why a signal passed or was discarded. No black box, no hidden scoring.

### The Pipeline

```
Harvest → Filter (4 gates) → Investigate → Verify → Analyze → Report
```

Signals that pass are cross-referenced, scored with a confidence level, and passed to the report generator. The pipeline never crashes — if the language model is unavailable, it falls back to a local model, then to deterministic rules. A report always comes out.

### Three-Tier Language Model Fallback

| Tier | Backend | Notes |
|------|---------|-------|
| 1 | Anthropic Claude | Default; fastest |
| 2 | Local Ollama | Zero-cost local fallback |
| 3 | Deterministic rules | Always available; no API required |

---

## What You Get

### Daily Research Brief
A structured first-draft report written to the standard of NYT, Washington Post, ProPublica. Every claim is sourced. Confidence is stated explicitly — not as adjectives, but as tier labels: *confirmed by two independent sources*, *single-source unconfirmed*, *insufficient signal*. The human edits length and tone before anything goes out.

### Story Leads
Not summaries. Each lead is a dispatch package: the specific anomaly, who has the answer, what documents to request (with FOIA language pre-written), and a Claude prompt pre-loaded with context for immediate use.

### Influence Operation Detection
Narrative anomaly scoring across harvested signals — coordinated framing detection, consensus velocity analysis, origin traceability checks.

### Topic Dossiers (Research Mode)
Define a research topic with keywords, entities, and sub-questions. Run it repeatedly. Each cycle adds to the dossier. Accumulates across runs without LLM calls or gate filtering — this mode is for deep research, not daily triage.

### Portland Metro Civic Brief (PDX-1i)
Local civic intelligence for the Portland bi-state metro: campaign finance anomalies, legislative bill tracking, infrastructure monitoring, entity relationship mapping. The architectural template for future regional modules.

### Legislative & Judicial Desk
Federal and state legislative tracking, FARA filing analysis, judicial record monitoring, stated-purpose vs. beneficiary analysis.

### Feedback Loop
File verdicts on any report — correct, incorrect, partial, unclear. The calibration system surfaces drift over time. You decide whether thresholds need adjustment. Nothing auto-tunes.

---

## Interfaces

| Interface | What It Does |
|-----------|-------------|
| **REST API** | 15+ endpoints under `/api/v1/` |
| **MCP Server** | 16 tools exposed to Claude Desktop |
| **CLI Workspace** | Case file management from the terminal |
| **PDF Export** | Formatted reports for distribution |
| **Verdict UI** | Browser form for filing feedback at `/verdicts/` |

---

## Data Sources

40+ public sources including: War on the Rocks, The Cipher Brief, Just Security, RAND, Atlantic Council, Defense One, 38 North, NK News, CSIS Korea Chair, Yonhap, Reuters, AP, ProPublica, congressional records, FARA filings, Oregon and Washington state legislative databases, Portland civic records.

---

## Getting Started

```bash
git clone https://github.com/CLS-1000/spec-1V0.7.git
cd spec-1V0.7
pip install -e ".[dev]"
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env (optional — system works without it via Tier 3)
```

```bash
make cycle        # Run a full research cycle
make run          # Start the API server
make test         # Run the test suite
```

See [docs/runbook.md](docs/runbook.md) for production deployment and [docs/quickstart.md](docs/quickstart.md) for a guided first run.

---

## Key Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Enables Claude (Tier 1 LLM) | unset → Tier 3 |
| `SPEC1_STORE_PATH` | JSONL output file | `spec1_intelligence.jsonl` |
| `SPEC1_API_PORT` | API server port | `8000` |
| `SPEC1_API_KEY` | API authentication (opt-in) | unset → open |
| `SPEC1_DEV_MODE` | Skip Claude, use local Ollama | `false` |

Full variable reference in [.env.example](.env.example).

---

## Design Principles

**The system does mechanical work. You make the judgment.**  
SPEC-1 filters noise, scores signals, and writes the first draft of a research brief. What to publish, what to spike, how to frame — that's yours.

**Every claim traces to a source.**  
Confidence is explicit. The difference between *confirmed*, *assessed*, and *unverified* is stated in every report, not implied.

**Thresholds never auto-change.**  
The four gate thresholds are set by the operator. The calibration system surfaces drift. A human decides whether to act on it.

**All data is append-only.**  
Every signal, report, and verdict is written once, never overwritten. The full history is always available.

**The pipeline never crashes.**  
Every stage is failure-first — log the error, continue the cycle. A Tier 3 rule-based report is noted as such in the output.

---

## Performance

| Metric | Value |
|--------|-------|
| Harvest cycle | ~30 seconds |
| Filter latency | <100ms per gate |
| Brief generation | <5s (Tier 1) |
| API response | <100ms |
| Test suite | 64 test files, Python 3.9–3.12 |

---

**SPEC-1** — Automated Research Engine  
Built by EVASTARARCANA in Portland, OR

The system handles the triage. You do the reporting.
