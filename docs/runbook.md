# SPEC-1 Operational Runbook

Procedures for running, maintaining, and debugging SPEC-1 in production.

---

## Daily Operations

### Check last cycle output

```bash
# Latest brief (new canonical path)
cat generated/briefs/spec1_brief_latest.md
# Legacy path written by `make cycle` rich CLI:
# cat briefs/spec1_brief_latest.md

# Intelligence records from last run
tail -n 20 spec1_intelligence.jsonl | python -m json.tool

# API health
curl http://localhost:8000/api/v1/health
```

### Trigger a manual cycle

```bash
# Canonical lean cycle — produces intelligence records only.
# This is what the API scheduler runs, and what `POST /cycle/run` triggers.
PYTHONPATH=src python -m spec1_core.core.engine    # (via Engine class — embedded use)
curl -X POST http://localhost:8000/api/v1/cycle/run

# Rich CLI cycle — also runs psyop scoring + brief generation + workspace case
# updates inline. Convenient for one-shot local runs; not what the canonical
# scheduler executes.
make cycle                                            # → python -m spec1_core.app.cycle
```

The canonical FastAPI scheduler runs the lean cycle daily. To produce a brief,
leads, or psyop scores from the canonical cycle's records, run the operator
tools below.

### Check scheduler status

```bash
curl http://localhost:8000/api/v1/health
# Look for: "scheduler": "running"
```

### Pause scheduled cycles (kill-switch)

The canonical scheduler checks for a `.cls_kill` file at the repo root before every
scheduled run. To pause cycles without restarting:

```bash
touch .cls_kill          # next scheduled run skips with a logged warning
rm    .cls_kill          # restored — next scheduled run proceeds
```

### Run a cycle on API startup

```bash
SPEC1_RUN_ON_START=true make run
# Daemon thread fires one immediate cycle alongside the scheduled cron;
# also respects .cls_kill.
```

---

## Starting Services

### API server (canonical)

```bash
make run
# or
PYTHONPATH=src python -m spec1_api.main
```

### MCP server (Claude integration)

```bash
make mcp
# or
PYTHONPATH=src python mcp_server.py
```

---

## Development

### Install and run tests

```bash
make install    # pip install -e ".[dev]"
make test       # pytest tests/ -v --tb=short
make lint       # flake8 src/ tests/
```

### Environment setup

```bash
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY
make install
```

---

## Persistence

### JSONL files (source of truth)

| File | Contents |
|------|----------|
| `spec1_intelligence.jsonl` | Intelligence records |
| `verdicts.jsonl` | Human verdicts |
| `leads.jsonl` | Actionable leads |
| `world_briefs.jsonl` | Daily world briefs |
| `psyop_scores.jsonl` | PsyOp detection results |

All JSONL files are append-only. Never edit them manually.

### Rebuild SQLite from JSONL

```bash
PYTHONPATH=src python -m cls_db.migrate
# Then restart the API to repopulate
```

### Run schema migrations

```bash
PYTHONPATH=src python -m cls_db.migrate
```

---

## Operator Tools

Each tool reads from the intelligence JSONL store independently of the cycle. None
runs automatically inside the canonical cycle.

### Generate a brief from the latest run

```bash
make brief
# or:
PYTHONPATH=src python -m spec1_core.tools.generate_brief \
    --intel spec1_intelligence.jsonl \
    --run-id latest \
    --out-dir generated/briefs

# Force the rule-based producer (skip Claude entirely):
PYTHONPATH=src python -m spec1_core.tools.generate_brief --rule-based
```

Falls back to the rule-based `cls_world_brief.producer` if `ANTHROPIC_API_KEY`
is unset or the API call fails. Writes `spec1_brief_<date>.md`,
`spec1_brief_latest.md`, and an append-only `brief_index.jsonl` entry.

### Derive Lead objects from intelligence records

```bash
make leads
# or:
PYTHONPATH=src python -m spec1_core.tools.generate_leads \
    --intel spec1_intelligence.jsonl \
    --out generated/leads.jsonl \
    --min-confidence 0.3 --max-leads 50
```

### Score every intelligence record for psyop patterns

```bash
make psyop
# or:
PYTHONPATH=src python -m spec1_core.tools.run_psyop \
    --intel spec1_intelligence.jsonl \
    --out generated/psyop_scores.jsonl \
    --min-classification MEDIUM_RISK   # optional filter
```

### Backfill briefs for historical run_ids

```bash
make backfill
# or:
PYTHONPATH=src python -m spec1_core.tools.historical_briefs
```

### Generate a calibration proposal report

```bash
make calibration
# or:
PYTHONPATH=src python -m spec1_core.tools.calibration_propose \
    --intel spec1_intelligence.jsonl \
    --verdicts verdicts.jsonl \
    --out-dir generated/
```

---

## Filing Verdicts

Verdicts are append-only. Multiple verdicts per record are allowed.

```bash
# Via MCP (Claude session)
# → Use the file_verdict tool

# Via the web UI
# → Visit http://localhost:8000/verdicts/ in your browser

# Via API
curl -X POST http://localhost:8000/api/v1/verdicts \
  -H "Content-Type: application/json" \
  -d '{"record_id": "rec_...", "verdict": "correct", "reviewer": "handle", "notes": ""}'
```

Valid `kind` values: `correct`, `incorrect`, `partial`, `unclear`

---

## Workspace (Case Management)

```bash
make workspace
# or
PYTHONPATH=src python -m spec1_core.workspace
```

---

## Troubleshooting

### API won't start

1. Check `.env` exists and `ANTHROPIC_API_KEY` is set
2. Check port 8000 isn't in use: `lsof -i :8000`
3. Run `make install` to ensure dependencies are current

### Cycle produces no records

1. Check feed connectivity: `curl https://warontherocks.com/feed/`
2. Check API key: `python scripts/anthropic_smoke.py`
3. Lower velocity threshold temporarily (signals may be stale)

### Brief is rule-based (no Claude output)

The briefing module falls back silently on API errors. Check:
1. `ANTHROPIC_API_KEY` is valid and has quota
2. `python scripts/anthropic_smoke.py`

### SQLite and JSONL are out of sync

The JSONL is the source of truth. Rebuild SQLite:

```bash
rm spec1.db
PYTHONPATH=src python -m cls_db.migrate
```

---

## Generated Artifacts

The canonical lean cycle produces only intelligence records (`spec1_intelligence.jsonl`).
Briefs, leads, and psyop scores are produced by the operator tools above.

```
spec1_intelligence.jsonl   # Canonical cycle output — append-only source of truth
briefs/                    # Legacy: written by the rich `make cycle` CLI path and by historical_briefs
generated/                 # New default for operator tool outputs (gitignored)
├── briefs/                # generate_brief writes here
├── leads.jsonl            # generate_leads writes here
├── psyop_scores.jsonl     # run_psyop writes here
└── calibration_report.md  # calibration_propose writes here
```

Do not commit anything in `briefs/` or `generated/` to `main` — both are gitignored.
