# Changelog

All notable changes to SPEC-1 are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.8.0] — 2026-10-25

### Added
- **Legislative & Judicial Desk v2.1 (#196):** `python -m spec1_core.app.cycle --desk legislative [--since-days 90]`. `cls_leg_jud.bridge` turns OLIS measures, OLIS interim committee meetings (with agenda items) and OpenStates/LegiScan bills into standard Signals tagged `domain="state_leg.<st>.<kind>"`. Each item is verified on the local model and stored to `spec1_legislative.jsonl` + SQLite `intelligence_records`. The desk writes `briefs/spec1_legislative_<date>.md` via `generate_brief(mode="legislative")` with a provenance sidecar, plus the rule-based `cls_leg_jud` view. The 4 gates are evaluated and stored but not enforced; a 90-day window and a cap of 25 replace them. Synthetic state-legislature samples are dropped.
- **OLIS:** `Bill.last_action_at` / `introduced_at` from OData `ModifiedDate` / `CreatedDate`; `latest_interim_session_key()` and `fetch_interim_meetings()`.
- **`LocalTier3Client.chat()` (#195):** free-form markdown chat against local Ollama (`qwen2.5:3b` default, `OLLAMA_MODEL` override, `SPEC1_LOCAL_CHAT_TIMEOUT`, default 600s).
- `briefing.writer.write_brief(prefix=…)` / `write_brief_meta(latest_name=…)`: a desk gets its own dated, latest, prompts and index files and never touches `spec1_brief_*` or the published `brief_index.jsonl`.
- `signal.scorer.composite_score()`.

### Changed
- **Local-first brief (#195):** `generate_brief()` tries local Qwen, then Claude, then the rule-based brief, and records `cycle_stats["brief_backend"]`.
- Low-RAM Ollama default (`MODEL_LOW_RAM`) is now `qwen2.5:3b` (was `mistral`).

### Fixed
- **Routed `FallbackLLMClient` restored (#195).** The `FallbackLLMClient = LocalTier3Client` alias from 3f80d77 made the verifier raise TypeError, which was swallowed, so every record silently became `rule_based`. The analyst-loop audit crashed.
- Verifier `_extract_json` recovers `classification` / `verified` / `confidence` / `reasoning` by regex when a small model leaves quotes unescaped inside `reasoning`, instead of demoting the record to `rule_based`.
- Tests no longer reach the real Claude API or Ollama (`.env` keys leaked in through `load_dotenv`).
- Unused `Optional` import in `schemas/models.py` that failed CI lint on `develop`.

---

## [0.7.0] — 2026-10-24

### Added
- **`analysis_tier` on every record:** `llm_verified` only when a real model answered, else `rule_based`. Migration 011 adds `analysis_tier` (plus `signal_excerpt`, `llm_reasoning`) to `intel_records`; pre-011 rows stay `NULL` and fail the publish guard closed.
- **Publish guard:** each brief gets a `<brief>.meta.json` provenance sidecar. `notitia_civica_publish.yml`, `scripts/inject_brief_to_template.py` and `python -m spec1_core.briefing.writer --check` refuse anything not `llm_verified` or without a sidecar. `--mark-hand-written` keeps the Kali hand-written-brief flow over Qwen-verified records.
- **Triage-only cloud cycle:** `--triage-only` / `SPEC1_TRIAGE_ONLY=true` / `make triage` runs harvest, the 4 gates and Tier 3 rules with no model, brief, handoff, PDF or case research. Both Actions workflows use it.

### Changed
- **License reverted to proprietary** (EVASTARARCANA LLC, all rights reserved); the Apache 2.0 `LICENSE` from `831ad7a` is withdrawn.
- `Repository` writes only existing columns and updates existing rows in place instead of `INSERT OR REPLACE`; `filter()` accepts only real column names.
- `spec1_engine` archived.

### Fixed
- `FallbackLLMClient.complete()` reports the tier that actually answered.
- `run-cycle.yml` restores past issue PDFs so the issue counter no longer restarts at 001.
- Six broken Makefile targets; `make lint` runs ruff; `cryptography` declared.
- Harvester: CSIS Korea routed to Beyond Parallel, bozo feeds handled, Yonhap wire edition slugs canonicalized; batch insert supports heterogeneous record schemas.

---

## [0.6.0] — 2026-05-19

### Added
- **API versioning (Task 1.3):** All `spec1_api` routes are now under `/api/v1/` prefix (e.g., `GET /api/v1/health`, `POST /api/v1/verdicts`). Resolves naming ambiguity with legacy `spec1_core.api` which was already versioned.
- **Verdict-filing web UI (Task 1.5):** `GET /verdicts/` serves a single-page HTML form for filing human verdicts. Loads recent intel records, lets reviewer pick a verdict kind, and submits to `POST /api/v1/verdicts`.
- **Dual-write for leads, briefs, psyop (Task 1.6):** `LeadStore`, `BriefStore`, and `PsyopStore` now accept an optional `db` parameter. When provided, every write goes to both JSONL and SQLite via `DualWriter`. `spec1_api.dependencies` wires the database automatically. JSONL remains the source of truth.
- **New documentation (Task 1.7):** `docs/quickstart.md`, `docs/deployment.md`, `docs/customization.md`, `docs/api-integration.md`.

### Changed
- `docs/runbook.md`: Updated API paths to `/api/v1/...`, removed quant section, added verdict web UI reference.
- `docs/architecture.md`: Removed re-export shim rows and `cls_quant` row.
- `Makefile`: Removed `install-quant` target.
- `.env.example`: Removed `SPEC1_QUANT_ENABLED`.
- `README.md`: Removed `SPEC1_QUANT_ENABLED` row from env var table.

### Removed
- `cls_quant` — quantitative market intelligence module removed (out of scope for core triage mission; market demand not validated). numpy/yfinance optional deps, `SPEC1_QUANT_ENABLED` env var, and `install-quant` Makefile target all cleaned up.
- `cls_quant` references across docs, Makefile, and env templates (code was never shipped).

---

## [0.4.0] — 2026-05-06

### Added
- `cls_verdicts` — append-only human ground-truth store (`Verdict`, `VerdictKind`)
- `cls_calibration` — descriptive drift surfacing (aggregator, proposer, formatter); never auto-tunes
- `cls_db` — structured persistence layer: SQLite connection pool, ORM models, dual-write, migration runner
- `spec1_api` — canonical FastAPI application with APScheduler daily cron
  - Routers: `/health`, `/signals`, `/intel`, `/leads`, `/brief`, `/psyop`, `/fara`, `/verdicts`, `/calibration`, `/cycle/run`
- `mcp_server.py` — MCP server exposing 12 tools to Claude (`run_cycle`, `get_signals`, `get_intel`, `get_leads`, `get_brief`, `get_psyop`, `get_fara`, `analyse_psyop`, `get_stats`, `file_verdict`, `get_verdicts`, `get_calibration`)
- `spec1_core.workspace` — persistent investigation case files (case, tracker, researcher, CLI)
- `spec1_core.tools` — operational CLIs: `historical_briefs`, `calibration_propose`, `pdf_render`
- DPRK/Korea intelligence layer — 38 North, NK News, CSIS Korea, Yonhap feeds + dedicated fuel-supply signal loop
- Portland Political Web signal loop — 4-gate ingest + node tooltip API
- `cls_db.publish_log` — publication audit trail
- `spec1_api.static` — portfolio and UI HTML served at `/`
- X publisher integration (`test_x_publisher.py`)
- `WorldStateBrief` value objects and brief schemas (`test_brief_schemas.py`)
- PDF render subprocess (`spec1_core.tools.pdf_render`) — weasyprint isolated out-of-process

### Changed
- Briefing template replaced with WORLD STATE BRIEF design
- `spec1_core.briefing` now always falls back to rule-based brief on API error
- `DEFAULT_FEEDS` expanded from 6 to 10 sources

### Fixed
- Missing-file guard on `GET /` UI route
- Test assertion for `DEFAULT_FEEDS` count updated for DPRK sources

---

## [0.3.0] — 2026-04-28

### Added
- `cls_psyop` — psychological-operation detection (patterns, scorer, evidence, pipeline, store)
- `cls_quant` — quantitative market intelligence (4-sector watchlist: defense, cyber, energy, macro via yfinance)
- `cls_leads` — actionable intelligence lead generation and formatting
- `cls_world_brief` — daily world intelligence brief (producer, formatter, store)
- `cls_osint.adapters` — FARA, congressional, and narrative adapters
- `spec1_core.congressional` — congressional records (collector, parser, scorer, analyzer, cycle)
- `spec1_core.quant` — market signal cycle (collector, parser, scorer, analyzer)
- `spec1_core.analysts` — analyst registry, credibility weighting, discovery
- Re-export shims: `spec1_analytics.cls_leads`, `spec1_analytics.cls_psyop`, `spec1_analytics.cls_world_brief`
- `spec1_labels.py` — canonical label/enum strings (single source of truth)
- Sacred-geometry PDF brief template (later replaced in v0.4.0)

### Changed
- Briefing generator upgraded to Claude Sonnet from rule-based only

---

## [0.2.0] — 2026-04-18

### Added
- `spec1_core.investigation` — hypothesis generator and Claude Haiku verifier
  - Outcome classifications: Corroborated, Escalate, Investigate, Monitor, Conflicted, Archive
- `spec1_core.intelligence` — analyzer (blends confidence signals) and JSONL store
- `spec1_core.briefing` — daily brief generator with rule-based fallback
- `cls_osint` — extended OSINT adapters (feed fetcher, OSINT record schemas, pipeline, store)
- `spec1_core.core.prompts/` — authoritative prompt `.md` files (frozen)
- Frozen core governance: `src/spec1_core/core/` declared off-limits for ad-hoc edits
- `spec1_core.api` — legacy in-engine FastAPI mount (superseded by `spec1_api` in v0.4.0)

### Changed
- Scorer now produces `Opportunity` objects (not raw signals) for downstream stages
- Pipeline wired end-to-end: harvest → parse → score → investigate → verify → analyze → store

---

## [0.1.0] — 2026-04-11

### Added
- `spec1_core.signal` — harvester (RSS/Atom), parser (HTML clean + NLP), scorer (4-gate framework)
  - Gate 1: Credibility (source weight ≥ 0.5)
  - Gate 2: Volume (word count ≥ 50)
  - Gate 3: Velocity (recency ≤ 48h)
  - Gate 4: Novelty (keyword domain + hash-based dedup)
- `spec1_core.core` — schemas (`Signal`, `ParsedSignal`, `Opportunity`), ID generation, logging utils
- Initial RSS feed list: War on the Rocks, Cipher Brief, Just Security, RAND, Atlantic Council, Defense One
- `pyproject.toml` with `src/` layout, dev extras, and quant extras
- Initial test suite (pytest, tmp_path fixtures, mocked network calls)
