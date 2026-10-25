# SPEC-1 — Cloud Readiness Audit (GCP / Cloud Run)

**Generated:** 2026-07-26
**Repository:** `CLS-1000/spec-1` @ `53b2554` (`Main`)
**Package version:** `0.6.2`
**Target:** Google Cloud Platform — Cloud Run (fully managed)
**Scope:** Read-only audit. No source, config, or infrastructure was modified.

---

## Verdict

**SPEC-1 will not deploy to Cloud Run in its current state.** The container image does not
build, and even with the build fixed, three architectural properties conflict with Cloud Run's
execution model: the app never reads `$PORT`, all persistence assumes a durable local
filesystem, and the daily cycle runs on an in-process scheduler.

| Severity | Count | Meaning |
|---|---|---|
| 🔴 Blocker | 4 | Deployment fails, or data is silently lost |
| 🟠 High | 5 | Deploys, but insecure, unobservable, or functionally wrong |
| 🟡 Medium | 9 | Operational friction, cost, or maintenance risk |
| 🟢 Strength | 6 | Already correct — preserve these |

The good news: **3 of the 4 blockers are small, mechanical fixes.** Only persistence (B-3)
requires a design decision.

---

## 🔴 Blockers

### B-1 — The Docker image does not build (Python version conflict)

`Dockerfile:5` and `Dockerfile:20` both pin `python:3.11-slim-bookworm`, but
`pyproject.toml:9` declares `requires-python = ">=3.12"`. The builder stage's
`pip wheel ... -e .` (`Dockerfile:17`) aborts.

Verified by running the identical resolution on Python 3.11.15:

```
$ python -m pip install --dry-run --no-deps -e .
ERROR: Package 'spec1-engine' requires a different Python: 3.11.15 not in '>=3.12'
```

This is not theoretical — every CI workflow (`install-gate.yml:16`,
`python-package.yml:22`, `run-cycle.yml:21`) already standardised on 3.12. The Dockerfile
is the only artifact left on 3.11, so CI stays green while the image is broken. **Nothing
in CI builds the image**, which is why this has gone unnoticed.

**Fix:** change both `FROM` lines to `python:3.12-slim-bookworm`. Add an image build to CI
so this cannot regress (see M-9).

---

### B-2 — The app never reads `$PORT`, which is Cloud Run's contract

Cloud Run injects `PORT` into the container and requires the process to listen on it.
SPEC-1 reads a different variable entirely:

- `src/spec1_api/main.py:218` — `port = int(os.environ.get("SPEC1_API_PORT", "8000"))`
- `Dockerfile:29` — `SPEC1_API_PORT=8000`

`PORT` is ignored, so the server binds 8000 while Cloud Run's default probe targets 8080.
The revision fails its startup probe and never serves traffic.

Worse, the second documented entrypoint hardcodes everything and cannot be configured at all:

```python
# src/spec1_core/main.py
uvicorn.run("spec1_core.api.app:app", host="0.0.0.0", port=8000, reload=False, ...)
```

`CLAUDE.md` presents `python -m spec1_core.main` as an equivalent way to start the API. On
Cloud Run it is not — no environment variable can move it off 8000.

**Fix:** read `PORT` first, fall back to `SPEC1_API_PORT`, then `8000`:

```python
port = int(os.environ.get("PORT") or os.environ.get("SPEC1_API_PORT", "8000"))
```

Apply to both entrypoints. (A deploy-time workaround exists — set the service's container
port to 8000 — but it leaves the platform contract unmet and breaks the moment anyone uses
the default.)

---

### B-3 — Persistence assumes a durable local disk; Cloud Run has none

This is the one finding that is a **design decision, not a patch.**

The core architecture is dual-write: every record goes to append-only JSONL *and* SQLite
(`src/cls_db/dual_write.py`). The image commits to this with `VOLUME ["/data"]`
(`Dockerfile:51`) and:

```
SPEC1_STORE_PATH=/data/spec1_intelligence.jsonl
SPEC1_DB_PATH=/data/spec1.db
```

On Cloud Run, the container filesystem is an **in-memory tmpfs**. Three consequences:

1. **Every write counts against the instance's memory limit.** An append-only JSONL store
   that grows across a long-running cycle will eventually OOM the instance.
2. **All data is destroyed** when the instance is recycled — which Cloud Run does routinely,
   including scaling to zero.
3. **Concurrent instances diverge.** Each replica gets its own private `/data`, so two
   instances produce two unrelated intelligence stores with colliding IDs.

SQLite makes this sharper. `src/cls_db/database.py:37` enables WAL:

```python
self._conn.execute("PRAGMA journal_mode=WAL")
```

WAL relies on shared-memory coordination that **does not work on network filesystems**.
Mounting a GCS bucket via Cloud Storage FUSE — the usual Cloud Run answer to "I need a
filesystem" — is therefore not a safe fix for the SQLite half; concurrent writers risk
corruption, not just contention.

**Options, in ascending order of effort:**

| Option | Fit | Trade-off |
|---|---|---|
| **Cloud Run + Cloud SQL (Postgres)** | Best long-term | Requires a real SQLAlchemy backend swap; `sqlalchemy>=2.0` is already a dependency, but `cls_db` is hand-written `sqlite3` throughout |
| **GCS FUSE for JSONL only + Cloud SQL for structured** | Preserves the dual-write concept | Two backends to keep in sync; JSONL append over FUSE is workable, SQLite over FUSE is not |
| **Switch target to a PaaS with real block volumes** (Fly.io / Render) | Zero code change | Not GCP |
| **GCE VM or GKE with a persistent disk** | Zero code change, stays on GCP | Loses Cloud Run's scale-to-zero and managed operations |

If the goal is specifically Cloud Run, plan for the `cls_db` → Cloud SQL migration. If the
goal is "on GCP, soon", a GCE VM with a persistent disk runs the current code unmodified.

---

### B-4 — The daily cycle will not run

`src/spec1_api/scheduler.py:58` starts an in-process APScheduler `BackgroundScheduler` from
the FastAPI lifespan, firing `_run_cycle_job` at `SPEC1_CRON_HOUR`/`SPEC1_CRON_MINUTE` in
`America/Los_Angeles`.

On Cloud Run this fails in both directions:

- **At `min-instances=0`** (the default), no instance exists at 06:00, so the job never
  fires. Cloud Run also throttles CPU to near-zero outside request handling, so even a warm
  instance may not execute the timer.
- **At `min-instances>1`**, *every* replica runs its own scheduler and fires its own full
  cycle — duplicate harvests, duplicate LLM spend, duplicate records.

The repo already knows this. `docs/deployment.md` says, in the Lambda section:

> Lambda cannot run APScheduler. Use Lambda for API queries only and trigger
> `POST /api/v1/cycle/run` from EventBridge (cron) or an external scheduler.

The identical constraint applies to Cloud Run and is not documented there.

**Fix:** disable the in-process scheduler in cloud deployments and drive
`POST /api/v1/cycle/run` from **Cloud Scheduler** with an OIDC-authenticated request. There
is currently no env flag to disable the scheduler — one should be added
(e.g. `SPEC1_SCHEDULER_ENABLED=false`), since `start_scheduler()` is called unconditionally.

Related: `maybe_run_on_start()` (`scheduler.py:91`) launches a **full intelligence cycle in a
daemon thread during application startup** when `SPEC1_RUN_ON_START=true`. On Cloud Run that
competes with the startup probe and runs under CPU throttling. Leave it off.

---

## 🟠 High

### H-1 — The API is fully open by default, including expensive endpoints

`src/spec1_api/auth.py` is a no-op unless `SPEC1_API_KEY` is set:

```python
required_key = _get_configured_key()
if required_key is None:
    return await call_next(request)   # auth disabled — pass through
```

This is a defensible default for localhost. On a public Cloud Run URL it means anonymous
callers can `POST /api/v1/cycle/run` — triggering feed harvests and **billable Anthropic
API calls** — with no credential.

**Fix:** require `SPEC1_API_KEY` whenever `SPEC1_ENVIRONMENT=production`, and deploy the
service with `--no-allow-unauthenticated` plus IAM invoker bindings.

### H-2 — API keys are accepted in the query string and land in logs

`auth.py` accepts the key two ways:

```python
supplied = request.headers.get("X-API-Key") or request.query_params.get("api_key")
```

Cloud Run and Cloud Load Balancing both record the full request path — **including the query
string** — in Cloud Logging. Every `?api_key=...` call writes a live credential into logs
that have a different (usually broader) access policy than the secret store.

**Fix:** drop the query-param path in production, or redact it before logging.

### H-3 — API key comparison is not constant-time

```python
if supplied == required_key:
```

A plain `==` on secrets short-circuits on first mismatch. Over a network this is a weak
oracle, but it is free to fix: use `hmac.compare_digest(supplied, required_key)`.

### H-4 — Application logs are invisible in Cloud Logging

`src/spec1_core/core/logging_utils.py:35` defines `configure_root()`, but **nothing in
`spec1_api` ever calls it** — verified: no `configure_logging`/`setup_logging` call exists
anywhere under `src/spec1_api/` or `src/spec1_core/app/`.

The API therefore runs with an unconfigured root logger. Uvicorn configures its own loggers,
but the module loggers that carry the operationally interesting messages do not propagate to
any handler at INFO. Concretely, these are silently dropped in production:

- `"Scheduled cycle complete: %d records stored, %d errors"` (`scheduler.py:37`)
- `"Scheduler started: daily cycle at ..."` (`scheduler.py:68`)
- Webhook delivery outcomes

Note `logger.error(...)` calls still surface via the `lastResort` handler at WARNING+, so
failures are visible while successes are not — the worst combination for diagnosing a
silent pipeline.

### H-5 — No structured logging for Cloud Logging

Where logging *is* configured, it is plain text:

```python
format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

Cloud Logging ingests this as unparsed `textPayload`. Every entry lands at default severity
— `ERROR` and `INFO` become indistinguishable, so severity-based alerting cannot be built —
and multi-line tracebacks are split into one log entry per line.

**Fix:** emit JSON to stdout with `severity` and `message` keys; Cloud Logging parses those
natively.

---

## 🟡 Medium

### M-1 — Ollama Tier 2 stalls every LLM fallback by ~2 seconds

`src/spec1_core/llm/fallback_client.py:196` defaults auto-spawn **on**:

```python
auto_spawn = os.environ.get("OLLAMA_AUTO_SPAWN", "true").lower() != "false"
```

The image contains no `ollama` binary. So on every Tier-1 failure the client calls
`ollama_manager.is_running()`, which does a blocking `urlopen` against
`http://localhost:11434` with `timeout=2` (`ollama_manager.py:47`), waits out the timeout,
then `shutil.which("ollama")` returns `None` and it logs *"ollama binary not found in PATH"*
before finally reaching Tier 3.

`.env.example` ships `OLLAMA_AUTO_SPAWN=true` and
`LLM_FALLBACK_TIER_PRIORITY=claude,ollama,mock`, so this is the default posture.

**Fix for cloud:** set `OLLAMA_AUTO_SPAWN=false` and
`LLM_FALLBACK_TIER_PRIORITY=claude,mock`.

### M-2 — `/health` is a static stub

`src/spec1_api/routers/health.py` returns a hardcoded `status="ok"` plus the version and
environment string. It never touches the database, the JSONL store, or any dependency.

It is a valid *liveness* probe and nothing more. A revision with an unwritable `/data` or a
corrupt SQLite file reports healthy and will be routed traffic.

**Fix:** add a readiness check that opens the DB and stats the store path. Point Cloud Run's
startup probe at it, keeping `/health` for liveness.

### M-3 — Dependencies are effectively unpinned

`pyproject.toml` pins exactly one of fifteen dependencies (`feedparser==6.0.10`); the rest
are `>=` floors — `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `pydantic>=2.0`,
`sqlalchemy>=2.0`, `anthropic>=0.20`, and so on.

Two images built from the same commit a week apart can contain different major versions.
This turns an upstream release into a production incident with no corresponding code change,
and makes rollback unreliable — redeploying an old commit does not restore the old
dependency set.

**Fix:** generate a lockfile (`pip-compile`, `uv lock`, or `pip freeze` into
`requirements.lock`) and have the Dockerfile install from it.

### M-4 — Production image uses an editable install

`Dockerfile:44` installs the application editable in the **runtime** stage:

```dockerfile
RUN pip install --no-cache-dir --no-index --find-links=/wheels -e .
```

An editable install links back to `/app/src` rather than installing into site-packages, so
the image must retain the source tree and the `.pth`/finder indirection stays on the import
path. Note what `/wheels` is actually doing here: it supplies the **dependency** wheels built
in the builder stage, while the application itself is rebuilt from source at runtime-stage
install time. The application is never installed from a wheel, so the two-stage build buys
less isolation than its shape suggests.

**Fix:** build a real wheel (`python -m build --wheel`) in the builder and
`pip install --no-index /wheels/*.whl` in the runtime stage. Drop `-e`.

### M-5 — Deployment docs contradict the image

`docs/deployment.md` and the `Dockerfile` disagree on both the data path and the health URL:

| | Dockerfile | docs/deployment.md |
|---|---|---|
| Data dir | `/data` (`VOLUME ["/data"]`) | `/app/data` (`-v $(pwd)/data:/app/data`) |
| Health URL | `/health` | `/api/v1/health` |

`/api/v1/health` **does not exist** — `health.router` is mounted with no prefix
(`main.py:169`). The compose healthcheck in the docs would fail permanently. Anyone
following the docs also mounts their volume at a path the image does not use, so `/data`
stays ephemeral and their data vanishes.

### M-6 — No GCP section in the deployment guide

`docs/deployment.md` covers Docker, systemd, Render/Railway, AWS Lambda, and generic
container hosts. There is no Cloud Run, GKE, or GCE guidance, and no mention of Secret
Manager, Cloud Scheduler, or Cloud SQL.

### M-7 — Dead duplicate app definition with permissive CORS

`src/spec1_api/main.py:14-27` constructs a `FastAPI()` instance at import time and attaches
CORS with hardcoded localhost origins and `allow_credentials=True` — before the module's own
docstring (line 30) and imports (33-65).

This object is discarded: line 211 rebinds `app = create_app()`. The block is dead today,
but it is a live trap. Anything that imports `spec1_api.main` and grabs `app` before line
211, or any future refactor that reorders the module, silently activates a permissive CORS
policy that bypasses `_build_cors_origins()`.

**Fix:** delete lines 14-27 and the duplicated imports.

### M-8 — `SPEC1_LOG_LEVEL` is documented but never read

`.env.example` and `CLAUDE.md` both list `SPEC1_LOG_LEVEL=INFO`. A search across `src/`
returns **zero** references. Operators setting it get no effect and no warning — compounding
H-4, since the natural response to "I see no logs" is to set exactly this variable.

### M-9 — Nothing in CI builds the container image

The four workflows run tests, lint, CodeQL, a fresh-clone install gate, and the cycle. None
runs `docker build`. That is precisely why B-1 — a broken image on the default branch —
passed every check.

**Fix:** add a `docker build` step, and push to Artifact Registry on merges to `Main`.

---

## 🟢 Strengths — preserve these

1. **Multi-stage build.** `Dockerfile` separates builder from runtime; `build-essential`
   never reaches the final image.
2. **Non-root runtime user.** `useradd --uid 10001 spec1` + `USER spec1`, with `/app` and
   `/data` chowned. Satisfies Cloud Run's security posture out of the box.
3. **`.dockerignore` is genuinely good.** Excludes `.env`, `.envrc`, `*.jsonl`, `*.db`,
   `*.log`, `.git`, and shell rc files — no credential or data leakage into the image.
4. **CORS fails closed in production.** `_build_cors_origins()` returns `[]` unless
   `SPEC1_CORS_ORIGINS` is set, and `allow_credentials` is tied to a non-empty allowlist.
5. **Webhooks are HMAC-signed.** `X-Spec1-Signature: sha256=<hex>` with a configurable
   timeout, delivered off the request path.
6. **LLM failure is already non-fatal.** The three-tier fallback terminates at rule-based
   Tier 3, so no cloud LLM outage can crash the cycle — a genuinely good property to carry
   into a managed environment.

---

## Recommended sequence

**Stage 1 — make the image deployable (small, mechanical)**
1. B-1: bump both `FROM` lines to `python:3.12-slim-bookworm`.
2. B-2: read `$PORT` in `spec1_api/main.py` and `spec1_core/main.py`.
3. M-9: add `docker build` to CI so B-1 cannot recur.
4. M-7: delete the dead app block.

**Stage 2 — decide persistence (the real work)**
5. B-3: choose a target from the options table. This gates everything else; until it is
   settled, any Cloud Run deployment loses data on every instance recycle.

**Stage 3 — make it safe and observable**
6. H-1/H-2/H-3: require `SPEC1_API_KEY` in production, drop the query-param path, use
   `hmac.compare_digest`. Deploy with `--no-allow-unauthenticated`. Put
   `ANTHROPIC_API_KEY` and `SPEC1_API_KEY` in **Secret Manager**, not plain env vars.
7. H-4/H-5: call `configure_root()` at startup and emit JSON with a `severity` field.
8. M-2: add a real readiness probe.

**Stage 4 — correctness and cost**
9. B-4: add `SPEC1_SCHEDULER_ENABLED`, disable in cloud, drive the cycle from **Cloud
   Scheduler** → `POST /api/v1/cycle/run` with OIDC.
10. M-1: `OLLAMA_AUTO_SPAWN=false`, `LLM_FALLBACK_TIER_PRIORITY=claude,mock`.
11. M-3: pin dependencies with a lockfile.
12. M-4: install a built wheel instead of `-e .`.
13. M-5/M-6/M-8: reconcile the docs with the image, add a Cloud Run section, and either
    implement or remove `SPEC1_LOG_LEVEL`.

---

## Verification commands

```bash
# B-1 — reproduce the build failure on 3.11
python3.11 -m pip install --dry-run --no-deps -e .

# B-2 — confirm $PORT is never read
grep -rn 'environ.*PORT' src/ | grep -v SPEC1_API_PORT

# B-4 / H-4 — scheduler start path and the missing logging config
grep -rn 'start_scheduler\|configure_root' src/spec1_api/ src/spec1_core/

# M-8 — confirm SPEC1_LOG_LEVEL is unreferenced
grep -rn 'SPEC1_LOG_LEVEL' src/

# M-5 — confirm /api/v1/health does not exist
grep -rn 'health.router' src/spec1_api/main.py
```
