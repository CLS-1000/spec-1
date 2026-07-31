# SPEC-1 Deployment Guide

Production and cloud deployment reference for SPEC-1.

---

## Table of Contents

1. [Docker](#docker)
2. [Systemd service (Linux)](#systemd-service-linux)
3. [Environment variable reference](#environment-variable-reference)
4. [Database setup and migrations](#database-setup-and-migrations)
5. [Scheduling configuration](#scheduling-configuration)
6. [Health check and monitoring](#health-check-and-monitoring)
7. [Cloud deployment](#cloud-deployment)

---

## Docker

### Build and run

```bash
docker build -t spec-1 .
docker run -d \
  --name spec1 \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e SPEC1_ENVIRONMENT=production \
  -v $(pwd)/data:/app/data \
  spec-1
```

### docker-compose (recommended)

Create `docker-compose.yml`:

```yaml
version: "3.9"
services:
  spec1:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - SPEC1_ENVIRONMENT=production
      - SPEC1_STORE_PATH=/app/data/spec1_intelligence.jsonl
      - SPEC1_DB_PATH=/app/data/spec1.db
      - SPEC1_VERDICTS_PATH=/app/data/verdicts.jsonl
      - SPEC1_LEADS_PATH=/app/data/leads.jsonl
      - SPEC1_PSYOP_PATH=/app/data/psyop_scores.jsonl
      - SPEC1_BRIEFS_PATH=/app/data/world_briefs.jsonl
      - SPEC1_BRIEFS_DIR=/app/data/briefs
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      # Requires curl in the container image. For minimal images, replace with:
      # test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 60s
      timeout: 10s
      retries: 3
```

```bash
docker-compose up -d
docker-compose logs -f
```

---

## Systemd service (Linux)

Create `/etc/systemd/system/spec1.service`:

```ini
[Unit]
Description=SPEC-1 Intelligence Engine API
After=network.target

[Service]
Type=simple
User=spec1
WorkingDirectory=/opt/spec-1
ExecStart=/opt/spec-1/.venv/bin/python -m spec1_api.main
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/spec-1/.env
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable spec1
sudo systemctl start spec1
sudo journalctl -u spec1 -f
```

---

## Environment variable reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | _(unset)_ | Anthropic API key for Claude Sonnet briefing |
| `SPEC1_ENVIRONMENT` | `production` | Runtime environment (`production`, `development`) |
| `SPEC1_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `SPEC1_STORE_PATH` | `spec1_intelligence.jsonl` | Intelligence records JSONL |
| `SPEC1_DB_PATH` | `spec1.db` | SQLite database path |
| `SPEC1_VERDICTS_PATH` | `verdicts.jsonl` | Human verdict JSONL |
| `SPEC1_LEADS_PATH` | `leads.jsonl` | Actionable leads JSONL |
| `SPEC1_PSYOP_PATH` | `psyop_scores.jsonl` | PsyOp scores JSONL |
| `SPEC1_BRIEFS_PATH` | `world_briefs.jsonl` | Brief index JSONL |
| `SPEC1_BRIEFS_DIR` | `briefs` | Brief Markdown directory |
| `SPEC1_API_HOST` | `127.0.0.1` | API bind host (`0.0.0.0` for Docker) |
| `SPEC1_API_PORT` | `8000` | API bind port |
| `SPEC1_CRON_HOUR` | `6` | Hour for scheduled daily cycle |
| `SPEC1_CRON_MINUTE` | `0` | Minute for scheduled daily cycle |
| `SPEC1_TIMEZONE` | `America/Los_Angeles` | Timezone for cron schedule |
| `SPEC1_FEED_TIMEOUT` | `15` | RSS feed request timeout (seconds) |
| `SPEC1_RUN_ON_START` | `false` | Run one cycle immediately on API startup |
| `SPEC1_CORS_ORIGINS` | _(empty)_ | Comma-separated allowed origins (production) |

---

## Database setup and migrations

SPEC-1 uses SQLite for structured queries alongside append-only JSONL files.

```bash
# Initialize / migrate schema
PYTHONPATH=src python -m cls_db.migrate

# Rebuild from JSONL if SQLite is out of sync
rm spec1.db
PYTHONPATH=src python -m cls_db.migrate
# Restart the API — stores will re-populate on the next write cycle
```

All store writes are dual-write (JSONL + SQLite) when a database is configured.
JSONL is always the source of truth. SQLite failures are logged and non-fatal.

---

## Scheduling configuration

The API server includes an APScheduler cron that triggers the intelligence cycle
daily. Configure via env vars:

```bash
SPEC1_CRON_HOUR=6          # 06:00
SPEC1_CRON_MINUTE=0
SPEC1_TIMEZONE=America/Los_Angeles
```

**Kill-switch (pause without restart):**

```bash
touch .cls_kill   # next run skips
rm .cls_kill      # re-enable
```

**Run once on startup:**

```bash
SPEC1_RUN_ON_START=true make run
```

---

## Health check and monitoring

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","version":"...","environment":"production","timestamp":"..."}
```

Prometheus / Uptime Robot / UptimeKuma: monitor `GET /api/v1/health` for HTTP 200.

Log output goes to stdout/stderr. In systemd environments, use `journalctl -u spec1`.

---

## Cloud deployment

### Render / Railway

1. Connect your fork of `mjlak1000/spec-1`
2. Set start command: `python -m spec1_api.main`
3. Set `SPEC1_API_HOST=0.0.0.0` and all required env vars
4. Attach a persistent volume for JSONL/SQLite files (mount at `/app/data`)

### AWS Lambda (thin API only)

Lambda cannot run APScheduler. Use Lambda for API queries only and trigger
`POST /api/v1/cycle/run` from EventBridge (cron) or an external scheduler.

### Any container host

```bash
docker build -t spec-1 .
docker run -d -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$KEY \
  -e SPEC1_API_HOST=0.0.0.0 \
  -v /persistent/path:/app/data \
  spec-1
```
