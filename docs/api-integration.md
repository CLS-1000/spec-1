# SPEC-1 API Integration Guide

Complete reference for the SPEC-1 REST API (`spec1_api`).

All routes are under the `/api/v1/` prefix. The API is served by a FastAPI
application with auto-generated OpenAPI docs at `http://localhost:8000/docs`.

---

## Table of Contents

1. [Base URL and versioning](#base-url-and-versioning)
2. [Authentication](#authentication)
3. [Route reference](#route-reference)
   - [Health](#health)
   - [Signals](#signals)
   - [Intelligence](#intelligence)
   - [Leads](#leads)
   - [World Brief](#world-brief)
   - [PsyOp](#psyop)
   - [FARA](#fara)
   - [Verdicts](#verdicts)
   - [Calibration](#calibration)
   - [Cycle](#cycle)
   - [Publication](#publication)
   - [Workspace](#workspace)
   - [Legislative/Judicial](#legislativejudicial)
4. [Pagination](#pagination)
5. [Error responses](#error-responses)
6. [CORS configuration](#cors-configuration)
7. [OpenAPI / Swagger UI](#openapi--swagger-ui)
8. [MCP server (Claude integration)](#mcp-server-claude-integration)

---

## Base URL and versioning

```
http://localhost:8000/api/v1
```

All versioned API routes are under `/api/v1/`. Non-versioned paths serve static
HTML and are not part of the programmatic API surface:

| Path | Content |
|------|---------|
| `/` | SPEC-1 intelligence UI |
| `/verdicts/` | Verdict-filing web form |
| `/spec1_political_web.html` | Political intelligence viewer |
| `/docs` | Swagger UI (OpenAPI) |
| `/openapi.json` | OpenAPI schema |

---

## Authentication

The API has no built-in authentication in the current release. In production,
front it with a reverse proxy (nginx, Caddy, Cloudflare Tunnel) that enforces
authentication.

---

## Route reference

### Health

#### `GET /api/v1/health`

Returns service health status.

```bash
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "version": "0.6.0",
  "environment": "production"
}
```

---

### Signals

#### `GET /api/v1/signals`

Returns raw ingested signals.

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Max results (1–200) |
| `offset` | int | 0 | Pagination offset |
| `source_type` | string | — | Filter by source type (`rss`, `FARA`, etc.) |

#### `POST /api/v1/signals/ingest`

Ingest a new signal directly.

```json
{
  "source": "https://example.com",
  "text": "Signal text content here...",
  "source_type": "rss"
}
```

---

### Intelligence

#### `GET /api/v1/intel`

Returns analyzed intelligence records.

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Max results (1–200) |
| `offset` | int | 0 | Pagination offset |
| `classification` | string | — | Filter by outcome classification |
| `min_confidence` | float | 0.0 | Minimum confidence score |

Classifications: `CORROBORATED` · `ESCALATE` · `INVESTIGATE` · `MONITOR` · `CONFLICTED` · `ARCHIVE`

```bash
curl "http://localhost:8000/api/v1/intel?classification=ESCALATE&min_confidence=0.7"
```

---

### Leads

#### `GET /api/v1/leads`

Returns actionable intelligence leads.

Query parameters: `limit`, `offset`, `priority` (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`), `category`

#### `POST /api/v1/leads/generate`

Generate leads from current intelligence records on demand.

---

### World Brief

#### `GET /api/v1/brief`

Returns the most recently produced world brief.

```json
{
  "brief_id": "brief-...",
  "date": "2026-05-19",
  "headline": "...",
  "sections": [...],
  "confidence": 0.82
}
```

#### `GET /api/v1/brief/history`

Returns brief history. Query parameter: `limit` (1–50).

---

### PsyOp

#### `GET /api/v1/psyop`

Returns stored PsyOp scores.

Query parameters: `limit`, `offset`, `classification`

Classifications: `CLEAN` · `LOW_RISK` · `MEDIUM_RISK` · `HIGH_RISK`

#### `POST /api/v1/psyop/analyse`

Analyse a text snippet for PsyOp patterns on demand.

```json
{ "text": "The narrative claims that..." }
```

---

### FARA

#### `GET /api/v1/fara`

Returns FARA (Foreign Agents Registration Act) records.

Query parameters: `limit`, `offset`, `country`, `registrant`

---

### Verdicts

Human ground-truth for the calibration feedback loop.

#### `POST /api/v1/verdicts`

File a verdict on an intelligence record.

```json
{
  "record_id": "rec_abc123...",
  "verdict": "correct",
  "reviewer": "alice",
  "notes": "Corroborated by open-source reporting."
}
```

`verdict` must be one of: `correct` · `incorrect` · `partial` · `unclear`

Returns the stored verdict entry.

#### `GET /api/v1/verdicts`

List verdicts. Query parameters: `limit`, `offset`, `record_id`, `reviewer`, `verdict`

#### `GET /api/v1/verdicts/{record_id}`

List all verdicts for a specific record.

```json
{
  "record_id": "rec_abc123...",
  "total": 2,
  "items": [...]
}
```

**Web UI:** Visit `http://localhost:8000/verdicts/` for a browser-based form.

---

### Calibration

Read-only. Produces descriptive drift reports — never auto-applies adjustments.

#### `GET /api/v1/calibration/report`

Compute and return a `CalibrationReport` derived from current intelligence
records and verdicts.

```json
{
  "total_records": 120,
  "total_verdicts": 47,
  "matched_verdicts": 45,
  "overall": {
    "label": "overall",
    "accuracy": 0.72,
    "count": 45
  },
  "by_classification": { ... },
  "by_confidence_bucket": { ... }
}
```

#### `GET /api/v1/calibration/proposals`

Returns suggested threshold adjustments based on calibration drift.
**Descriptive only** — no adjustments are applied automatically.

Query parameters: `sample_floor` (min bucket size), `delta_floor` (min drift to flag)

---

### Cycle

#### `POST /api/v1/cycle/run`

Trigger a full intelligence cycle asynchronously.

```json
{
  "environment": "production",
  "max_signals": 100
}
```

Response:

```json
{
  "run_id": "run-abc123...",
  "started_at": "2026-05-19T06:00:00Z",
  "status": "running",
  "records_stored": 0
}
```

---

### Publication

#### `GET /api/v1/publication/latest`

Returns the most recent published PDF brief.

#### `GET /api/v1/publication/list`

Lists all available publication PDFs.

---

### Workspace

Persistent investigation case management.

#### `GET /api/v1/workspace/cases`

List open cases. Query parameters: `status` (`OPEN`/`CLOSED`/`WATCHING`), `limit`, `offset`

#### `POST /api/v1/workspace/cases`

Open a new case.

```json
{
  "title": "Investigation title",
  "question": "Core research question",
  "tags": ["defense", "treaty"]
}
```

#### `GET /api/v1/workspace/cases/{case_id}`

Get a specific case by ID.

#### `PATCH /api/v1/workspace/cases/{case_id}`

Update case status or add notes.

---

### Legislative/Judicial

#### `GET /api/v1/leg_jud/brief`

Returns the latest legislative/judicial brief.

#### `GET /api/v1/leg_jud/judicial`

Returns judicial signals. Query parameters: `limit`, `offset`, `judge`

#### `GET /api/v1/leg_jud/state_leg`

Returns state legislative signals. Query parameters: `limit`, `offset`, `state`

---

## Pagination

All list endpoints support `limit` and `offset`:

```bash
curl "http://localhost:8000/api/v1/intel?limit=10&offset=20"
```

Response shape:

```json
{
  "total": 150,
  "limit": 10,
  "offset": 20,
  "items": [...]
}
```

---

## Error responses

| Code | Meaning |
|------|---------|
| 200 | Success |
| 404 | Resource not found |
| 422 | Validation error (check request body) |
| 500 | Internal server error |

Error body:

```json
{ "detail": "Human-readable error message" }
```

---

## CORS configuration

In `development` / `dev` / `local` environments, the API allows all common
localhost origins and `file://` (the `null` origin). In `production`, set
`SPEC1_CORS_ORIGINS` to a comma-separated list of allowed origins:

```
SPEC1_CORS_ORIGINS=https://my-frontend.example.com,https://admin.example.com
```

---

## OpenAPI / Swagger UI

Interactive API explorer:

```
http://localhost:8000/docs
```

Raw OpenAPI schema (JSON):

```
http://localhost:8000/openapi.json
```

---

## MCP server (Claude integration)

SPEC-1 ships a companion MCP server at `mcp_server.py`. When connected to
Claude Desktop, it exposes all analysis capabilities as tools:

| Tool | Description |
|------|-------------|
| `run_cycle` | Trigger a full intelligence cycle |
| `get_signals` | Retrieve raw signals |
| `get_intel` | Retrieve intelligence records |
| `get_leads` | Retrieve actionable leads |
| `get_brief` | Retrieve the latest world brief |
| `get_psyop` | Retrieve PsyOp scores |
| `get_fara` | Retrieve FARA records |
| `analyse_psyop` | Analyse a text snippet for PsyOp patterns |
| `get_stats` | Get summary statistics |
| `file_verdict` | Submit a human verdict |
| `get_verdicts` | Retrieve filed verdicts |
| `get_calibration` | Get the current calibration report |

Start the MCP server:

```bash
make mcp
# or
PYTHONPATH=src python mcp_server.py
```
