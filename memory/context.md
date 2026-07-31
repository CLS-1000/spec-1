# SPEC-1 — System Context

Live reference for agents and contributors. Update this file when the system's
state or active work changes significantly.

---

## Current Version

**v0.4.0** — Full stack: pipeline, API, MCP, verdicts, calibration, workspace

---

## Active Modules

| Module | Status | Notes |
|--------|--------|-------|
| `spec1_core` | Active | Core pipeline — frozen core off-limits |
| `cls_osint` | Active | 10 RSS feeds including 4 DPRK/Korea sources |
| `cls_psyop` | Active | Pattern detection + evidence chains |
| `cls_quant` | Active | Run separately: `python -m spec1_core.quant.cycle` (requires `.[quant]` extras) |
| `cls_leads` | Active | |
| `cls_world_brief` | Active | |
| `cls_verdicts` | Active | Append-only; currently single reviewer |
| `cls_calibration` | Active | Descriptive only — never auto-tunes |
| `cls_research` | Active | Analyst-defined topic dossiers with automated expansion |
| `cls_db` | Active | Dual-write; SQLite non-fatal |
| `spec1_api` | Active | FastAPI + APScheduler on port 8000 |
| `mcp_server.py` | Active | 13 tools exposed to Claude |
| `spec1_core.workspace` | Active | Case file management |

---

## Known Limitations

1. **Single reviewer** — All verdicts in `verdicts.jsonl` are from one person. Calibration
   reports reflect a single observer's bias. Multiple reviewers needed before calibration
   can be trusted for threshold changes.

2. **SQLite coverage is partial** — `cls_db.dual_write` is optional; not all stores use it.
   Some stores are still JSONL-only. The API reads from JSONL via repository abstractions.

3. **Frontend is a single HTML file** — `spec1_ui.html` served at `GET /`. No build step,
   no SPA framework. Sufficient for v0.4; a proper frontend is a known future step.

4. **PDF export requires weasyprint native deps** — Works as a subprocess; not installed by
   default. PDFs not generated unless weasyprint is available.

5. **Quant pipeline requires numpy/pandas/yfinance** — Install with `pip install -e ".[quant]"`.
   Falls back to synthetic data if yfinance is unavailable.

---

## Feed Sources (as of v0.4.0)

| ID | Source |
|----|--------|
| `war_on_the_rocks` | War on the Rocks |
| `cipher_brief` | The Cipher Brief |
| `just_security` | Just Security |
| `rand` | RAND Corporation |
| `atlantic_council` | Atlantic Council |
| `defense_one` | Defense One |
| `38_north` | 38 North (DPRK) |
| `nk_news` | NK News (DPRK) |
| `csis_korea` | CSIS Korea Chair (DPRK) |
| `yonhap` | Yonhap News Agency (Korea) |

---

## Analyst Registry (as of v0.4.0)

11 analysts/organizations in the registry. Domain-aware — signals about Russian
military operations surface different leads than cyber or energy infrastructure signals.
Individual credibility scores are not published (see `PORTFOLIO_SUMMARY.md`).

---

## Test Suite (as of v0.4.0)

- **30 test files**, **917 test functions**
- External network calls are mocked in all tests
- `test_quant.py` requires numpy — skip with `--ignore tests/test_quant.py` without it
- Run: `pytest tests/ -v --tb=short`

---

## Agent Write Surfaces

Agents may freely modify:
- `src/spec1_core/signal/`
- `src/spec1_core/investigation/`
- `src/spec1_core/intelligence/`
- `src/spec1_core/briefing/` (except `templates.py` imports — edit `.md` files)
- `src/spec1_core/tools/`
- `src/cls_osint/`, `src/cls_psyop/`, `src/cls_quant/`, `src/cls_leads/`
- `src/spec1_api/`
- `tests/`
- `docs/`, `memory/`, `scripts/`

Agents must NOT modify without human approval:
- `src/spec1_core/core/` (any file)
- `src/spec1_core/core/prompts/` (any `.md` file)
- `pyproject.toml` version field
- `CLAUDE.md`
- `.github/pull_request_template.md`
