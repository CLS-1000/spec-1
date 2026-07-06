# SPEC-1 Intelligence Engine — Architecture Guide

## Overview

SPEC-1 is a real-time open-source intelligence (OSINT) platform that:
- Harvests signals from RSS feeds, FARA filings, congressional records, judicial filings, and narrative sources
- Scores and prioritises signals through a 4-gate pipeline
- Generates and verifies investigations
- Detects psychological-operation patterns
- Produces quantitative market intelligence
- Publishes daily world briefs, PDX-1i Metro Citizens Briefs, and Legislative & Judicial Desk briefs
- Generates and tracks actionable leads through an analyst workflow chain of custody
- Supports analyst-defined Research Mode (topic dossiers, no LLM required)
- Records human verdicts and surfaces calibration drift (descriptive, not auto-tuning)
- Persists all data to JSONL and SQLite via dual-write
- Exposes a FastAPI HTTP API, Prometheus metrics, webhook delivery, and an MCP server for Claude integration

## Repository Layout

```
spec-1/
├── src/
│   ├── spec1_core/              # CANONICAL OSINT pipeline (replaces spec1_engine as the active package)
│   │   ├── schemas/models.py        # Signal, ParsedSignal, Opportunity, Investigation, Outcome,
│   │   │                            # IntelligenceRecord, AnalystRecord
│   │   ├── core/                    # FROZEN: engine, ids, logging_utils, settings, prompts/
│   │   │   └── prompts/             # Authoritative prompt .md files (no inline prompt strings allowed)
│   │   ├── signal/                  # harvester, parser, scorer, complexity, gates
│   │   ├── investigation/           # generator, verifier
│   │   ├── intelligence/            # analyzer, store
│   │   ├── analysts/                # registry, credibility, discovery
│   │   ├── briefing/                # generator (Claude via fallback client) + writer + templates
│   │   │                            # rule-based fallback if all LLM tiers fail
│   │   ├── llm/                     # Three-tier LLM fallback client
│   │   │   ├── fallback_client.py   # Tier 1: Anthropic Claude | Tier 2: Ollama | Tier 3: rules
│   │   │   ├── ollama_manager.py    # Ollama lifecycle (spawn, health-check, model pull)
│   │   │   └── tier3_rules.py       # Rule-based mock fallback
│   │   ├── config/                  # Configuration and calibration settings
│   │   ├── congressional/           # collector, parser, scorer, analyzer, cycle
│   │   ├── psyop/                   # scorer (cls_psyop wrapper)
│   │   ├── workspace/               # persistent investigation case files (case, tracker,
│   │   │                            # researcher, CLI)
│   │   ├── tools/                   # Operational CLIs
│   │   │   ├── generate_brief.py        # Build daily brief for one run_id
│   │   │   ├── generate_leads.py        # Derive Lead objects from intel records
│   │   │   ├── historical_briefs.py     # Backfill briefs for past run_ids
│   │   │   ├── calibration_propose.py   # Build calibration report from verdicts
│   │   │   ├── pdf_render.py            # Out-of-process weasyprint subprocess
│   │   │   ├── publication_generator.py # ReportLab PDF (Psyche-Ops Issue layout)
│   │   │   ├── run_psyop.py             # Score intel records for psyop patterns
│   │   │   ├── backfill_jsonl_to_db.py  # Migrate JSONL → SQLite
│   │   │   ├── radar_dashboard.py       # Signal radar view
│   │   │   ├── snapshot_manager.py      # JSONL snapshot management
│   │   │   └── workspace_sanitizer.py   # Case file cleanup
│   │   ├── api/                     # Internal FastAPI sub-app (legacy mount /api/v1)
│   │   ├── app/cycle.py             # `python -m spec1_core.app.cycle` — one-shot cycle
│   │   └── main.py                  # `python -m spec1_core.main` — uvicorn entry point
│   │
│   ├── spec1_engine/            # LEGACY PACKAGE — kept for backward compat; mirrors spec1_core
│   │   │                        # All new code should target spec1_core imports
│   │   └── (same subdirectory structure as spec1_core; imports from spec1_engine.* namespace)
│   │
│   ├── cls_osint/               # Extended OSINT adapters
│   │   ├── schemas.py           # OSINTRecord, FaraRecord, CongressRecord, NarrativeRecord
│   │   ├── sources.py           # Source registry
│   │   ├── feed.py              # Generic feed fetcher
│   │   ├── pipeline.py          # Full OSINT processing pipeline
│   │   ├── store.py             # JSONL persistence
│   │   └── adapters/            # fara, congressional, narrative, verifier, judicial,
│   │                            # state_legislative, pdx911, quant, registry
│   │
│   ├── cls_world_brief/         # Daily world intelligence brief
│   │   └── schemas / producer / formatter / store / synthetic
│   │
│   ├── cls_leads/               # Actionable intelligence leads
│   │   └── schemas / generator / formatter / store
│   │
│   ├── cls_psyop/               # Psychological-operation detection
│   │   └── schemas / patterns / scorer / pipeline / evidence / store
│   │
│   ├── cls_verdicts/            # Phase 1 feedback loop — human ground truth
│   │   ├── schemas.py           # Verdict, VerdictKind ('correct'|'incorrect'|'partial'|'unclear')
│   │   └── store.py             # Append-only JSONL; multiple verdicts per record allowed
│   │
│   ├── cls_calibration/         # Phase 2 feedback loop — drift surfacing
│   │   ├── schemas.py           # Bucket, CalibrationReport, ProposalReport, SuggestedAdjustment
│   │   ├── aggregator.py        # produce_report, score_verdict
│   │   ├── proposer.py          # propose_adjustments (descriptive only — no auto-tune)
│   │   └── formatter.py         # to_markdown
│   │
│   ├── cls_db/                  # Structured persistence layer
│   │   ├── database.py          # SQLite connection pool + session factory
│   │   ├── models.py            # Table schemas (signals, records, leads, briefs, psyop,
│   │   │                        # verdicts, calibration)
│   │   ├── repository.py        # Generic CRUD repository
│   │   ├── dual_write.py        # Atomic JSONL + SQLite write
│   │   └── migrate.py           # Schema migration runner
│   │
│   ├── cls_pdx1/                # PDX-1i — Portland Metro Intelligence module
│   │   ├── models.py            # Official, Affiliation, Bill, Signal, Anomaly, Issue
│   │   │                        # ConfidenceTier, EdgeType, AnomalyTier (Pydantic v2)
│   │   ├── pipeline.py          # CycleResult orchestrator (adapter errors skipped, not fatal)
│   │   ├── gates.py             # Publication gates (signal-gated, neutrality-gated)
│   │   ├── triggers.py          # TriggerPolicy / TriggerDecision — when to publish
│   │   ├── anomaly.py           # RollingBaseline sigma-based anomaly detection
│   │   ├── resolver.py          # Entity resolution across sources
│   │   ├── sources/             # ORESTAR (OR campaign finance), OLIS (OR legislature),
│   │   │                        # SEI (financial disclosures), WA-PDC (WA campaign finance)
│   │   ├── watch/               # Infrastructure watch: OHSU, PPB, TriMet, PGE,
│   │   │                        # NW Natural, Schnitzer, Water Bureau
│   │   ├── legislation/         # bills.py — OR/WA legislative bill tracker
│   │   ├── neutrality/          # tone, attribution, section neutrality checks
│   │   ├── publication/         # newsletter.py (Markdown+PDF), builder, diagram
│   │   ├── explain/             # summarize.py — LLM-assisted signal explanation
│   │   └── demos/               # Runnable demos (e.g. metro_president_vacancy)
│   │
│   ├── cls_leg_jud/             # Legislative & Judicial Desk
│   │   ├── schemas.py           # LegJudBrief, LegJudSection, SECTION_TITLES, SECTION_KINDS
│   │   ├── producer.py          # produce_brief() — rule-based synthesis
│   │   ├── formatter.py         # to_markdown, section_to_markdown, to_json_summary
│   │   └── store.py             # LegJudStore (JSONL)
│   │
│   ├── cls_research/            # Research Mode — analyst-defined topic dossiers
│   │   ├── schemas.py           # TopicProfile, ResearchArtifact (dataclasses)
│   │   ├── topics.py            # Topic CRUD (JSONL)
│   │   ├── expansion.py         # Keyword/entity expansion rules
│   │   ├── collector.py         # Signal collection for a topic (uses spec1_core harvester)
│   │   ├── dossier.py           # build_dossier() — aggregates collected signals
│   │   ├── formatter.py         # dossier_to_markdown()
│   │   ├── pipeline.py          # run_research_pipeline() — topic → dossier → markdown
│   │   └── store.py             # DossierStore (JSONL, append-only)
│   │
│   ├── cls_analyst_loop/        # Analyst workflow chain of custody
│   │   ├── schemas.py           # AnalystCase, AnalystOutput, AnalystVerdict, AuditResult,
│   │   │                        # AnalystVerdictKind
│   │   ├── store.py             # AnalystLoopStore (JSONL)
│   │   ├── audit.py             # run_audit() — LLM audit of analyst outputs
│   │   └── cli.py               # click CLI: new-case, submit-output, run-audit,
│   │                            # file-verdict, list-cases, show
│   │
│   ├── spec1_api/               # FastAPI application (canonical HTTP surface)
│   │   ├── main.py              # App factory + lifespan + CORS + auth middleware + metrics middleware
│   │   ├── auth.py              # ApiKeyMiddleware (opt-in via SPEC1_API_KEY)
│   │   ├── scheduler.py         # APScheduler daily cycle
│   │   ├── webhooks.py          # cycle.completed webhook delivery (HMAC-SHA256 signing)
│   │   ├── metrics.py           # Prometheus-format request metrics
│   │   ├── dependencies.py      # DI for stores, db, engine
│   │   ├── schemas/             # Pydantic request/response models (incl. node_signal.py)
│   │   ├── db/                  # DB helpers (signals.py)
│   │   ├── static/              # verdicts.html, spec1_political_web.html,
│   │   │                        # portland_political_web.html
│   │   └── routers/
│   │       ├── health.py        # GET /health
│   │       ├── metrics.py       # GET /metrics (Prometheus text), GET /metrics/json
│   │       ├── signals.py       # GET /api/v1/signals
│   │       ├── intel.py         # GET /api/v1/intel
│   │       ├── leads.py         # GET/POST /api/v1/leads
│   │       ├── brief.py         # GET /api/v1/brief
│   │       ├── psyop.py         # GET /api/v1/psyop
│   │       ├── fara.py          # GET /api/v1/fara
│   │       ├── verdicts.py      # GET/POST /api/v1/verdicts
│   │       ├── calibration.py   # GET /api/v1/calibration
│   │       ├── cycle.py         # POST /api/v1/cycle/run (fires webhook on completion)
│   │       ├── publication.py   # GET /api/v1/publication/latest|list, POST /api/v1/publication/generate
│   │       ├── workspace.py     # GET/POST /api/v1/workspace/cases
│   │       ├── leg_jud.py       # GET /api/v1/leg-jud/...
│   │       ├── adapters.py      # GET /api/v1/adapters (adapter registry status)
│   │       ├── nodes.py         # GET /api/v1/nodes/{node_id}/signal (Portland Political Web)
│   │       └── ingest.py        # POST /api/v1/ingest (conditional on SPEC1_POLITICAL_WEB)
│   │
│   ├── data/                    # Bundled JSONL fixtures (e.g. psyop_signals.jsonl)
│   └── spec1_labels.py          # Canonical label/enum strings — import from here, never hard-code
│
├── tests/                       # pytest suite — ~60 files
│   ├── test_engine.py / test_pipeline.py / test_cycle.py
│   ├── test_harvester.py / test_scorer.py / test_verifier.py
│   ├── test_feed.py / test_fara.py / test_congressional.py / test_narrative.py
│   ├── test_world_brief.py / test_briefing.py / test_leads.py
│   ├── test_psyop.py / test_psyop_evidence.py
│   ├── test_persistence.py / test_store.py
│   ├── test_analysts.py / test_workspace.py
│   ├── test_verdicts.py / test_calibration.py / test_calibration_proposer.py
│   ├── test_pdf_render.py / test_logging_utils.py
│   ├── test_api.py / test_mcp_server.py / test_spec1_api_scheduler.py
│   ├── test_analyst_loop.py / test_research.py / test_leg_jud.py
│   ├── test_pdx1_*.py           # pdx1 anomaly, gates, legislation, models, neutrality,
│   │                            # pipeline, publication, sources, triggers, watch
│   ├── test_adapter_registry.py / test_pdx911.py / test_resolver.py
│   ├── test_auth.py / test_webhooks.py / test_metrics.py
│   ├── test_fallback_client.py / test_cursor_reader.py / test_indexed_queries.py
│   ├── test_labels_compliance.py / test_brief_schemas.py
│   ├── test_tools_generate_brief.py / test_tools_generate_leads.py / test_tools_run_psyop.py
│   ├── test_publication_generator.py / test_x_publisher.py
│   ├── test_ui_route.py / test_e2e_metro_president_vacancy.py
│   ├── test_olis_live.py / test_orestar_resolver.py  # live integration tests (network)
│   └── test_credibility.py
│
├── briefs/                      # Generated daily briefs + per-day analyst prompts
├── scripts/                     # Standalone scripts (e.g. anthropic_smoke.py)
├── monitor.py                   # Terminal curses monitor (standalone, cosmetic)
├── mcp_server.py                # MCP server exposing SPEC-1 tools to Claude
├── pyproject.toml               # Version: 0.6.0
├── requirements.txt
├── .env.example
├── CASE_STUDY.md
├── PORTFOLIO_SUMMARY.md
└── README.md
```

## Data Flow

```
RSS / FARA / Congress / Narrative / Judicial / State-Leg / PDX-911
         │
         ▼
   cls_osint.feed ───────────────────────────────────────┐
         │                                               │
         ▼                                               ▼
  spec1_core.signal                              cls_osint.adapters
  ├── harvester  → Signal[]                      ├── fara             → FaraRecord[]
  ├── parser     → ParsedSignal[]                ├── congressional    → CongressRecord[]
  └── scorer     → Opportunity[]                 ├── narrative        → NarrativeRecord[]
         │                                       ├── judicial         → OSINTRecord[]
         ▼                                       ├── state_legislative → OSINTRecord[]
  spec1_core.investigation                       └── pdx911           → OSINTRecord[]
  ├── generator  → Investigation[]
  └── verifier   → Outcome[]  (via FallbackLLMClient: Claude→Ollama→rules)
         │
         ▼
  spec1_core.intelligence
  ├── analyzer   → IntelligenceRecord[]
  └── store      → spec1_intelligence.jsonl
         │
         ├──────────────┬────────────────────┬────────────────────┬──────────────────┐
         ▼              ▼                    ▼                    ▼                  ▼
  cls_world_brief  cls_leads           spec1_core.briefing  cls_leg_jud        cls_verdicts
  → WorldBrief[]   → Lead[]            → daily brief .md    → LegJudBrief[]     (human input)
                        │               + analyst prompts                              │
                        ▼                                                              ▼
                cls_analyst_loop                                              cls_calibration
                → AnalystCase[]                                               → CalibrationReport
                → AnalystOutput[]                                               (drift report —
                → AnalystVerdict[]                                               descriptive only)
         │
         ├────────────────────────────────────────────────────────────────────────────┐
         ▼                                                                            ▼
  cls_pdx1.pipeline               cls_research.pipeline
  → Affiliation / Bill /          → ResearchArtifact[]
    Signal / Anomaly / Issue      → dossiers/<topic_id>/dossier_v<n>.md
  → Metro Citizens Brief
         │
         ▼
  cls_db.dual_write
  ├── JSONL (append-only)
  └── SQLite (queryable)
         │
         ├──────────────────────────────────────────────────────────────────────────────┐
         ▼                                                                              ▼
  spec1_api (FastAPI)                                                       spec1_api.webhooks
  ├── /health, /metrics                                                     → POST cycle.completed
  ├── /api/v1/signals, /intel, /leads, /brief                                 to SPEC1_WEBHOOK_URLS
  ├── /api/v1/psyop, /fara, /verdicts, /calibration, /cycle
  ├── /api/v1/publication, /workspace, /leg-jud, /adapters
  ├── /api/v1/nodes (Portland Political Web tooltips)
  ├── /api/v1/ingest (conditional: SPEC1_POLITICAL_WEB=true)
  └── /verdicts/ (HTML UI), /portland-web (HTML UI), /spec1_political_web.html
         │
  mcp_server.py (Claude MCP)
```

## Key Data Models

### spec1_core (canonical pipeline)
- `Signal` — raw RSS/OSINT item
- `ParsedSignal` — cleaned + keywords/entities extracted
- `Opportunity` — passed all 4 gates (credibility, volume, velocity, novelty)
- `Investigation` — hypothesis + queries + analyst leads
- `Outcome` — verified classification (Corroborated / Escalate / Investigate / Monitor / Archive)
- `IntelligenceRecord` — final analyzed record with confidence score
- `AnalystRecord` — name, affiliation, domains, credibility_score (used by signal scorer)

### cls_osint
- `OSINTRecord`, `FaraRecord`, `CongressRecord`, `NarrativeRecord`

### cls_world_brief
- `WorldBrief` — (brief_id, date, headline, sections, sources, confidence)
- `BriefSection`

### cls_leads
- `Lead` — (lead_id, title, summary, priority, source_record_ids, generated_at)

### cls_psyop
- `PsyopPattern`, `PsyopScore`

### cls_verdicts
- `Verdict` — human ground-truth on a record (`record_id`, `kind`, reviewer, notes, ts)
- `VerdictKind` — `correct | incorrect | partial | unclear`

### cls_calibration
- `Bucket` — verdict-kind counts + accuracy (correct=1.0, partial=0.5, incorrect=0.0; unclear excluded)
- `CalibrationReport` — overall + per-classification accuracy + reliability buckets across
  confidence, source_weight, analyst_weight
- `ProposalReport` / `SuggestedAdjustment` — descriptive proposals; humans apply changes

### cls_pdx1
- `Official` — elected official in the Portland bi-state metro (Multnomah / Washington / Clackamas / Clark WA)
- `Affiliation` — edge between an official and an entity (donation, board seat, contract, lobbying, etc.)
- `Bill` — legislative bill from OR or WA
- `Signal` — PDX-1i signal (distinct from spec1_core Signal)
- `Anomaly` — sigma-tier anomaly (TIER_1: ≥3σ; TIER_2: ≥2σ)
- `Issue` — published Metro Citizens Brief issue
- `ConfidenceTier` — HARD_RECORD (1) / REPORTED (2) / INFERRED (3)
- `EdgeType` — DONATION / BOARD_SEAT / CONTRACT / LOBBYING / EMPLOYMENT / CO_MENTION / ENDORSEMENT / FAMILY_TIE
- `AnomalyTier` — TIER_1 (≥3σ) / TIER_2 (≥2σ); TIER_1 is publish-eligible

### cls_leg_jud
- `LegJudBrief` — one-shot brief with sections: executive_summary, federal_members, federal_lobbying,
  judicial, state_leg, stated_purpose_vs_beneficiary, geopolitical_context, story_leads
- `LegJudSection` — (kind, title, body, record_ids)
- `SECTION_TITLES` — stable string map; do NOT rename (PDF + X publisher depend on exact strings)

### cls_research
- `TopicProfile` — analyst-defined research topic (keywords, entities, aliases, sub-questions)
- `ResearchArtifact` — versioned dossier for a topic (signals collected across runs)
- Status: `DRAFT` | `FINAL` (from `spec1_labels.RESEARCH_STATUS_*`)

### cls_analyst_loop
- `AnalystCase` — tracks one lead from dispatch to verdict (case_id, run_id, lead_id, feed_prompt, analyst_id)
- `AnalystOutput` — analyst's written response to the feed prompt
- `AnalystVerdict` — final verdict on the case (AnalystVerdictKind)
- `AuditResult` — LLM audit of an analyst output

## 4-Gate Scoring System

Every signal must pass ALL four gates to become an Opportunity:

| Gate | Criterion | Default Threshold |
|------|-----------|-------------------|
| credibility | Known source / analyst weight ≥ 0.5 | 0.5 |
| volume | Word count ≥ 50 | 50 words |
| velocity | Signal recency ≤ 48 hours | 48h |
| novelty | Not duplicate (hash-based dedup) | — |

Calibration drift across these gates is surfaced by `cls_calibration` — never auto-applied.

Research Mode (`cls_research`) does **not** run the 4-gate filter.

## Three-Tier LLM Fallback

`spec1_core.llm.fallback_client.FallbackLLMClient` provides exception-safe LLM calls:

| Tier | Backend | Config |
|------|---------|--------|
| 1 | Anthropic Claude (default: `claude-haiku-4-5-20251001`) | `ANTHROPIC_API_KEY` |
| 2 | Local Ollama (`llama3` / `mistral` by RAM) | `SPEC1_OLLAMA_URL`, `OLLAMA_MODEL` |
| 3 | Rule-based mock (`tier3_rules`) | Always available |

All LLM calls are logged to `SPEC1_LLM_LOG_PATH` (default: `logs/llm_fallback.jsonl`).
The cycle never crashes on LLM failure — every call eventually reaches Tier 3.

## MCP Tools Exposed (mcp_server.py)

Original tools:
`run_cycle`, `get_signals`, `get_intel`, `get_leads`, `get_brief`, `get_psyop`, `get_fara`,
`analyse_psyop`, `get_stats`, `file_verdict`, `get_verdicts`, `get_calibration`

Operator tools (added later):
`run_psyop`, `generate_brief`, `generate_leads`, `run_research`

## API Authentication

API key auth is **opt-in**. Set `SPEC1_API_KEY` to enable it.
When enabled, all endpoints except `/health`, `/metrics`, `/`, `/docs`, `/redoc`, `/openapi.json`
require one of:
- Header: `X-API-Key: <key>`
- Query param: `?api_key=<key>`

When `SPEC1_API_KEY` is unset, the API is fully open (self-hosted / local mode).

## Environment Variables

```
# Storage
SPEC1_STORE_PATH=spec1_intelligence.jsonl
SPEC1_DB_PATH=spec1.db
SPEC1_ENVIRONMENT=production
SPEC1_LOG_LEVEL=INFO

# LLM — Tier 1 (Anthropic)
ANTHROPIC_API_KEY=sk-ant-...
SPEC1_LLM_CLAUDE_MODEL=claude-haiku-4-5-20251001   # optional override

# LLM — Fallback
LLM_FALLBACK_ENABLED=true
LLM_FALLBACK_TIER_PRIORITY=claude,ollama,mock
SPEC1_LLM_LOG_PATH=logs/llm_fallback.jsonl
SPEC1_DEV_MODE=true                                # skip Tier 1, route to Ollama (saves tokens)

# LLM — Tier 2 (Ollama)
OLLAMA_MODEL=llama3
OLLAMA_HOST=localhost:11434
OLLAMA_AUTO_SPAWN=true
SPEC1_OLLAMA_URL=http://localhost:11434

# API Server
SPEC1_API_HOST=0.0.0.0
SPEC1_API_PORT=8000

# Authentication (leave unset for open access)
SPEC1_API_KEY=

# Webhooks (comma-separated HTTPS URLs; fires cycle.completed)
SPEC1_WEBHOOK_URLS=https://hooks.slack.com/...
SPEC1_WEBHOOK_SECRET=                              # optional HMAC-SHA256 signing secret
SPEC1_WEBHOOK_TIMEOUT=10

# CORS (production; defaults to open in dev)
SPEC1_CORS_ORIGINS=https://app.spec1.ai,https://spec1.ai

# Scheduler
SPEC1_CRON_HOUR=6
SPEC1_CRON_MINUTE=0
SPEC1_TIMEZONE=America/Los_Angeles

# Feed
SPEC1_FEED_TIMEOUT=15

# Research Mode
SPEC1_RESEARCH_TOPICS_PATH=research/topics
SPEC1_RESEARCH_DOSSIER_PATH=research/dossiers

# Portland Political Web (enables /portland-web UI + /api/v1/nodes + /api/v1/ingest)
# SPEC1_POLITICAL_WEB=true
```

## Running the System

```bash
# Full intelligence cycle (one-shot)
python -m spec1_core.app.cycle

# API server (canonical)
python -m spec1_api.main
# or
python -m spec1_core.main

# MCP server (for Claude integration)
python mcp_server.py

# Analyst loop CLI
python -m cls_analyst_loop new-case --lead-id <id> --analyst-id <id>
python -m cls_analyst_loop list-cases
python -m cls_analyst_loop show --case-id <case-id>

# Operator tools
PYTHONPATH=src python -m spec1_core.tools.generate_brief --run-id <run-id>
PYTHONPATH=src python -m spec1_core.tools.generate_leads --run-id <run-id>
PYTHONPATH=src python -m spec1_core.tools.run_psyop --store spec1_intelligence.jsonl
PYTHONPATH=src python -m spec1_core.tools.historical_briefs
PYTHONPATH=src python -m spec1_core.tools.calibration_propose \
    --intel spec1_intelligence.jsonl \
    --verdicts verdicts.jsonl \
    --out-dir generated/

# Workspace CLI (case management)
python -m spec1_core.workspace

# Terminal monitor (cosmetic curses UI, no pipeline connection)
python monitor.py
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v --tb=short

# Skip live integration tests (network calls to OLIS, ORESTAR)
pytest tests/ -v --tb=short --ignore=tests/test_olis_live.py --ignore=tests/test_orestar_resolver.py
```

All test functions must be fully implemented — no `pass` stubs, no `pytest.skip`.

## Implementation Rules

1. No stubs — every function body must be implemented.
2. Use `dataclasses` for internal models, `pydantic` for API schemas and `cls_pdx1` models.
3. All stores write append-only JSONL; `cls_db` additionally writes SQLite.
4. `cls_db.dual_write` wraps every store write so JSONL and SQLite stay in sync.
5. API routers read from JSONL stores (via repository) — not direct DB queries.
6. `mcp_server.py` exposes the tools listed in the MCP section above.
7. Tests use `tmp_path` fixtures and mock external network calls.
8. `pyproject.toml` lists all packages under `[tool.setuptools.packages.find]`.
9. Import canonical strings from `spec1_labels` — never hard-code label values.
10. The briefing module calls Claude via `FallbackLLMClient` but always falls back to rule-based
    brief on all-tier LLM failure — the cycle never crashes on LLM failure.
11. Calibration is **descriptive**: it surfaces drift, it does not change thresholds. Tuning is
    a human decision. This preserves the "deterministic, legible" design philosophy.
12. Verdicts are append-only; multiple verdicts per record are allowed and aggregators decide
    how to fold them.
13. PDF rendering runs as a subprocess (`spec1_core.tools.pdf_render`) so the API/engine
    processes never import weasyprint or its native deps.
14. `SECTION_TITLES` keys in `cls_leg_jud` are stable — the PDF generator (ReportLab) and
    any X publisher integration depend on these exact strings; do not rename.
15. `cls_pdx1.ConfidenceTier.INFERRED` (tier 3) signals are not publish-eligible alone.
    `AnomalyTier.TIER_1` (≥3σ) is required for publication gating.
16. New code should import from `spec1_core.*` not `spec1_engine.*`.
    `spec1_engine` is kept only for backward compatibility.

## Governance & Agent Constraints

### Frozen Core

`src/spec1_core/core/` (and its mirror `src/spec1_engine/core/`) is the frozen core.
It contains canonical schemas, ID generation, logging utilities, settings, and the prompt
files under `core/prompts/`.

**Rules:**
- Agents may **import** from `core/` but may **not modify** it
- Any change to `core/` requires explicit human approval and a semantic version bump
- `core/prompts/*.md` are the authoritative source for all prompt text —
  no inline prompt strings may be added elsewhere in the codebase

### Semantic Versioning

`pyproject.toml` version follows MAJOR.MINOR.PATCH (current: `0.6.0`):

| Bump | When |
|------|------|
| MAJOR | Breaking change to `/core` contracts or schemas |
| MINOR | New module, scorer, adapter, or prompt surface |
| PATCH | Bug fix, CI, infra, test, docs |

Every PR must declare its version bump type in the PR description.

### Agent Write Surfaces

Agents may freely modify:
- `src/spec1_engine/signal/`
- `src/spec1_engine/investigation/`
- `src/spec1_engine/intelligence/`
- `src/spec1_engine/briefing/` (except `templates.py` imports — edit `.md` files instead)
- `src/spec1_engine/tools/`
- `src/cls_osint/`, `src/cls_psyop/`, `src/cls_quant/`, `src/cls_leads/`
- `src/spec1_core/signal/`
- `src/spec1_core/investigation/`
- `src/spec1_core/intelligence/`
- `src/spec1_core/briefing/` (except `templates.py` imports — edit `.md` files instead)
- `src/spec1_core/tools/`
- `src/cls_osint/`, `src/cls_psyop/`, `src/cls_leads/`
- `src/cls_pdx1/`, `src/cls_research/`, `src/cls_analyst_loop/`, `src/cls_leg_jud/`
- `src/spec1_api/`
- `tests/`

Agents must **NOT** modify without human approval:
- `src/spec1_core/core/` (any file)
- `src/spec1_engine/core/` (any file)
- `src/spec1_core/core/prompts/` (any `.md` file)
- `pyproject.toml` version field
- `CLAUDE.md`
- `.github/pull_request_template.md`

### Branch Rules

| Branch | Purpose |
|--------|---------|
| `main` | Human-curated stable releases only |
| `dev` | Integration branch — merge agent branches here first |
| `claude/*` or `agent/*` | Agent work — never merge directly to `main` |

### PR Requirements

Every PR must include (use `.github/pull_request_template.md`):
1. Summary of changes
2. Version bump type and justification
3. Confirmation that `/core` was not modified (or justification if it was)
4. Test status (`pytest` + `ruff` clean)

## Session Safety Rules

### Shorthand glossary — confirm before acting on these
- "spec-1" / "the repo" → CLS-1000/spec-1V0.7, develop branch
- "pdx1-i" → PDX-1i / cls_pdx1 (Portland Metro Intelligence module)
- "gh research" → push/pull Research Mode work to GitHub
- "The Downlow" → [spell this one out once before acting on it — not yet defined]
- "Metro Citizens Brief" → cls_pdx1 publication output (not cls_world_brief)
- "Research Mode" → cls_research (topic-directed dossiers, no LLM, no 4-gate filter)
- "analyst loop" → cls_analyst_loop (chain-of-custody workflow for leads → verdicts)
- "Leg-Jud" / "legislative desk" → cls_leg_jud

If a message uses a term not in this glossary, or could mean more than
one thing, state your interpretation in one line and wait for
confirmation before running anything.

### Repo/scope anchoring — required at the start of every session
Before any write, commit, or push:
1. Run `pwd` and `git remote -v` and `git branch --show-current`.
2. Confirm aloud: working directory is inside spec-1V0.7, remote is
   CLS-1000/spec-1V0.7, branch is the designated agent branch.
3. If any of these don't match, STOP and ask — do not create a new
   branch, worktree, or remote to "fix" it yourself.

### Plan mode means read-only
While in plan mode: read and report only. Never write, edit, delete,
or run git commands. State the plan and stop. Wait for an explicit
"approved, proceed" message before executing anything.

### Destructive operations
Never delete a directory, force-push, rewrite history, or change
formatting/structural conventions (e.g. SECTION_TITLES in cls_leg_jud,
PAI-style output) without first stating the exact change and getting
explicit approval — even if you believe it's clearly implied by the request.
