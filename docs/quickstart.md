# SPEC-1 Quick Start Guide

Get SPEC-1 running locally in under 5 minutes.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Run your first cycle](#run-your-first-cycle)
5. [View results](#view-results)
6. [Start the API server](#start-the-api-server)
7. [Use the MCP server with Claude](#use-the-mcp-server-with-claude)
8. [Common first-run issues](#common-first-run-issues)

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.9+ | 3.11 recommended |
| pip | 23+ | Bundled with Python |
| git | any | For cloning |
| Anthropic API key | — | Optional — falls back to rule-based if absent |

---

## Installation

```bash
git clone https://github.com/mjlak1000/spec-1.git
cd spec-1
pip install -e ".[dev]"
```

Verify:

```bash
python -c "import spec1_core; print('ok')"
```

---

## Configuration

```bash
cp .env.example .env
```

At minimum, set:

```
ANTHROPIC_API_KEY=sk-ant-...   # optional but recommended
SPEC1_ENVIRONMENT=development
```

All other values default to sensible local paths. See `.env.example` for the full
reference.

---

## Run your first cycle

A single cycle harvests RSS signals, scores them through the 4-gate pipeline,
and writes intelligence records to JSONL + SQLite.

```bash
make cycle
# or
PYTHONPATH=src python -m spec1_core.app.cycle
```

Expected output (numbers will vary):

```
[run-abc123] Harvesting signals...
[run-abc123] Scored 42 signals → 11 opportunities
[run-abc123] Generated 11 investigations, verified 9
[run-abc123] Stored 9 intelligence records
```

Records are written to `spec1_intelligence.jsonl` and `spec1.db`.

---

## View results

```bash
# Intelligence records (JSONL)
tail -n 5 spec1_intelligence.jsonl | python -m json.tool

# Generate a world brief from the records
make brief
cat generated/briefs/spec1_brief_latest.md

# Generate actionable leads
make leads

# Run psyop pattern detection
make psyop
```

---

## Start the API server

```bash
make run
# or
PYTHONPATH=src python -m spec1_api.main
```

Visit `http://localhost:8000` for the UI, or call the API directly:

```bash
curl http://localhost:8000/api/v1/health | python -m json.tool
curl http://localhost:8000/api/v1/intel?limit=5 | python -m json.tool
```

File verdicts via the web form:

```
http://localhost:8000/verdicts/
```

---

## Use the MCP server with Claude

```bash
make mcp
# or
PYTHONPATH=src python mcp_server.py
```

Then in Claude Desktop, configure a local MCP server pointing to
`python mcp_server.py`. Available tools:

`run_cycle` · `get_signals` · `get_intel` · `get_leads` · `get_brief`  
`get_psyop` · `get_fara` · `analyse_psyop` · `get_stats` · `file_verdict`  
`get_verdicts` · `get_calibration`

---

## Common first-run issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -e ".[dev]"` from the repo root |
| No intelligence records produced | Feeds may be slow; run again or check connectivity |
| Brief is rule-based | Set `ANTHROPIC_API_KEY` in `.env` |
| Port 8000 already in use | Set `SPEC1_API_PORT=8001` in `.env` |
| `spec1.db` permission error | Check write permissions for the directory |

Still stuck? See the [Troubleshooting section](runbook.md#troubleshooting) in the runbook.
