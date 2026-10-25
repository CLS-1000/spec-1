# SPEC-1 — Full Merge Conflict Report

**Generated:** 2026-07-26
**Repository:** `CLS-1000/spec-1`
**Reference commit named in request:** `e1edac3` — *"fix: resolve CI failures — leads schema canonical rebuild, reset_schema, nosec SQL fix, migration 009"* (Mon Jun 8 2026). This commit is **already an ancestor of `Main`**; `Main` is 185 commits ahead of it. It is not a source of any live conflict.
**Baseline for all merge tests:** `origin/Main` @ `183cf30`

---

## 1. Method

Every remote branch was test-merged against `origin/Main` using `git merge-tree --write-tree`
(true three-way merge, no working-tree mutation). Every branch tip was additionally scanned
for **committed** conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) left behind by an
unfinished resolution.

There are **no open pull requests** on the repository, so no PR is currently blocked. All
conflicts below are latent — they will surface the moment a branch is merged or a PR is opened.

**Working tree of `claude/conflict-errors-report-g4wzp2` is clean. `Main`'s tip contains zero conflict markers.**

> **Note on quoted markers.** Where this report quotes real conflict markers, the marker lines
> are indented by two spaces. The `install-gate` CI job rejects any file containing a marker at
> column 0 (`.github/workflows/install-gate.yml`), and that gate is doing its job — this report
> should not be the reason it is weakened. Read every indented `<<<<<<<` / `=======` / `>>>>>>>`
> below as flush-left in the real file.

---

## 2. Summary

| Branch | Ahead | Behind | Merge into `Main` | Conflicted files | Committed markers |
|---|---|---|---|---|---|
| `audit` | 62 | 157 | ❌ **CONFLICT** | **257** | 0 |
| `claude/adoring-heisenberg-ooptqj` | 2 | 45 | ❌ **CONFLICT** | 3 | **1 file** |
| `claude/repo-error-fixes-a7fkin` | 4 | 17 | ❌ **CONFLICT** | 2 | 0 |
| `claude/spec-1-workflow-failures-7vhywq` | 3 | 12 | ✅ clean | 0 | 0 |
| `temp/notitia-main` | 1 | 18 | ✅ clean | 0 | 0 |
| `dev` | 0 | 0 | ✅ identical to `Main` | 0 | 0 |
| `develop` (protected) | 0 | 11 | ✅ fast-forward | 0 | 0 |
| `copilot/explore-codebase-implementation-plan` | 0 | 20 | ✅ already merged | 0 | 0 |
| `copilot/fix-issue-with-data-import` | 0 | 37 | ✅ already merged | 0 | **3 files** |
| `copilot/potential-standalone-tools` | 0 | 25 | ✅ already merged | 0 | 0 |
| `copilot/python-versions-explanation` | 0 | 24 | ✅ already merged | 0 | 0 |

**Totals: 262 conflicted files across 3 branches, plus 4 files carrying committed conflict markers on 2 branches.**

---

## 3. Conflict Class A — `audit` (257 files)

`git merge-tree origin/Main origin/audit` → exit 1

| Conflict type | Count |
|---|---|
| content | 187 |
| modify/delete | 68 |
| rename/delete | 2 |
| **total** | **257** |

### 3.1 Root cause — this is a line-ending problem, not a code problem

The 187 content conflicts are **almost entirely artificial**. The `audit` branch converted
the repository to **CRLF line endings**; `Main` is LF. Every line of every converted file
therefore differs, so git produces one whole-file conflict hunk per file.

Evidence:

```
$ git diff --numstat --ignore-cr-at-eol <merge-base> origin/audit
371   0   MERGE_SAFETY_PLAN.md
373   0   spec1_ui.html
 23   1   src/spec1_api/main.py
```

**255 files changed on `audit`; with CR-at-EOL ignored, only 3 files have any real content
change at all.** 248 of the 324 text files on `audit` contain CR bytes; the merge-base
versions contain none.

Per-file hunk counts confirm this: 182 of the 187 content conflicts are a **single hunk
spanning the entire file** (e.g. `src/cls_db/dual_write.py` — 307 lines, markers at lines
1 / 162 / 307). Only 5 files have multi-hunk conflicts:

| File | Hunks |
|---|---|
| `src/spec1_api/static/index.html` | 3 |
| `pyproject.toml` | 3 |
| `docs/portfolio.md` | 2 |
| `README.md` | 2 |
| `.gitignore` | 2 |
| *(remaining 182 files)* | 1 each (whole-file) |

**Total conflict hunks: 194.**

### 3.2 Structural conflicts (the real ones)

Beyond line endings, `audit` diverged structurally from `Main` by relocating packages.

**(a) 68 modify/delete conflicts — 27 where `Main` deleted, 41 where `audit` deleted.**
The dominant cause is a package relocation:
`audit` moved `cls_leads`, `cls_psyop`, and `cls_world_brief` under
`src/spec1_analytics/`; `Main` kept them at `src/`. Git sees this as a delete on one
side and a modify on the other, in both directions:

*Deleted on `Main`, modified on `audit` (audit's version left in tree):*

```
AUDIT_REPORT.md
FALLBACK_SETUP.md
LAUNCH_PLAN.md
LAUNCH_READINESS.md
REPAIR_PLAN_PR64_66_WORKFLOWS.md
TEST_STATUS.md
briefs/spec1_brief_2026-04-12.md
briefs/spec1_brief_2026-04-14.md
docs/scalability_tracker.md
spec1_ui.html
src/spec1_analytics/cls_leads/__init__.py
src/spec1_analytics/cls_leads/formatter.py
src/spec1_analytics/cls_leads/generator.py
src/spec1_analytics/cls_leads/schemas.py
src/spec1_analytics/cls_leads/store.py
src/spec1_analytics/cls_psyop/__init__.py
src/spec1_analytics/cls_psyop/evidence.py
src/spec1_analytics/cls_psyop/patterns.py
src/spec1_analytics/cls_psyop/pipeline.py
src/spec1_analytics/cls_psyop/schemas.py
src/spec1_analytics/cls_psyop/scorer.py
src/spec1_analytics/cls_psyop/store.py
src/spec1_analytics/cls_world_brief/__init__.py
src/spec1_analytics/cls_world_brief/formatter.py
src/spec1_analytics/cls_world_brief/producer.py
src/spec1_analytics/cls_world_brief/schemas.py
src/spec1_analytics/cls_world_brief/store.py
```

*Deleted on `audit`, modified on `Main` (Main's version left in tree):*

```
src/cls_leads/formatter.py
src/cls_leads/generator.py
src/cls_leads/schemas.py
src/cls_leads/store.py
src/cls_psyop/evidence.py
src/cls_psyop/patterns.py
src/cls_psyop/pipeline.py
src/cls_psyop/schemas.py
src/cls_psyop/scorer.py
src/cls_psyop/store.py
src/cls_world_brief/formatter.py
src/cls_world_brief/producer.py
src/cls_world_brief/schemas.py
src/cls_world_brief/store.py
src/spec1_engine/analysts/__init__.py
src/spec1_engine/analysts/credibility.py
src/spec1_engine/analysts/discovery.py
src/spec1_engine/analysts/registry.py
src/spec1_engine/api/routes.py
src/spec1_engine/api/scheduler.py
src/spec1_engine/app/cycle.py
src/spec1_engine/briefing/generator.py
src/spec1_engine/briefing/templates.py
src/spec1_engine/briefing/writer.py
src/spec1_engine/congressional/cycle.py
src/spec1_engine/core/engine.py
src/spec1_engine/core/prompts/editorial_voice.md
src/spec1_engine/core/prompts/investigation_prompts.md
src/spec1_engine/core/prompts/psyop_scorer.md
src/spec1_engine/core/prompts/system_prompt.md
src/spec1_engine/core/prompts/user_prompt_template.md
src/spec1_engine/intelligence/analyzer.py
src/spec1_engine/intelligence/store.py
src/spec1_engine/investigation/verifier.py
src/spec1_engine/psyop/scorer.py
src/spec1_engine/signal/harvester.py
src/spec1_engine/signal/parser.py
src/spec1_engine/tools/__init__.py
src/spec1_engine/tools/calibration_propose.py
src/spec1_engine/tools/historical_briefs.py
src/spec1_engine/tools/pdf_render.py
```

> ⚠️ **Frozen-core impact.** This set includes `src/spec1_engine/core/engine.py` and all five
> `src/spec1_engine/core/prompts/*.md` files. Per `CLAUDE.md` these are frozen core — `audit`
> deletes them. Merging `audit` as-is would destroy the frozen core of the legacy package and
> requires explicit human approval plus a MAJOR version bump.

**(b) rename/delete — 2 files.**
`Main` renamed `src/spec1_engine/cls_psyop/` → `src/spec1_engine/psyop/`; `audit` deleted
the source path:

```
src/spec1_engine/cls_psyop/__init__.py  → renamed to src/spec1_engine/psyop/__init__.py on Main, deleted on audit
src/spec1_engine/cls_psyop/scorer.py    → renamed to src/spec1_engine/psyop/scorer.py    on Main, deleted on audit
```

**(c) `@domain:` banner headers.** `Main` added metadata banners
(`# @domain: / # @module: / # @loc: / # @status: / # @depends:`) to source files that
`audit` does not have. On a clean LF branch this would auto-merge; layered on top of the
CRLF flip it is folded into the whole-file conflict.

### 3.3 Full list — 187 content conflicts on `audit`

<details>
<summary>Expand</summary>

```
.env.example
.github/scripts/check_hardcoded_labels.py
.github/scripts/install_sgmllib_stub.py
.github/workflows/python-package.yml
.gitignore
Makefile
README.md
docs/architecture.md
docs/customization.md
docs/portfolio.md
mcp_server.py
memory/context.md
memory/decisions.md
pyproject.toml
requirements.txt
spec1_political_web.html
src/cls_calibration/formatter.py
src/cls_calibration/producer.py
src/cls_calibration/proposer.py
src/cls_db/cursor_reader.py
src/cls_db/dual_write.py
src/cls_db/indexed_queries.py
src/cls_db/migrate.py
src/cls_db/migrate_jsonl_to_db.py
src/cls_db/models.py
src/cls_db/publish_log.py
src/cls_db/repository.py
src/cls_leg_jud/formatter.py
src/cls_leg_jud/producer.py
src/cls_leg_jud/schemas.py
src/cls_leg_jud/store.py
src/cls_osint/adapters/congressional.py
src/cls_osint/adapters/fara.py
src/cls_osint/adapters/judicial.py
src/cls_osint/adapters/narrative.py
src/cls_osint/adapters/registry.py
src/cls_osint/adapters/state_legislative.py
src/cls_osint/adapters/verifier.py
src/cls_osint/feed.py
src/cls_osint/pipeline.py
src/cls_osint/schemas.py
src/cls_osint/store.py
src/cls_pdx1/explain/summarize.py
src/cls_pdx1/gates.py
src/cls_pdx1/legislation/bills.py
src/cls_pdx1/models.py
src/cls_pdx1/neutrality/attribution.py
src/cls_pdx1/neutrality/section.py
src/cls_pdx1/neutrality/tone.py
src/cls_pdx1/publication/builder.py
src/cls_pdx1/publication/diagram.py
src/cls_pdx1/publication/newsletter.py
src/cls_pdx1/sources/base.py
src/cls_pdx1/sources/sei.py
src/cls_pdx1/sources/wa_pdc.py
src/cls_pdx1/triggers.py
src/cls_pdx1/watch/nw_natural.py
src/cls_pdx1/watch/ohsu.py
src/cls_pdx1/watch/pge.py
src/cls_pdx1/watch/ppb.py
src/cls_pdx1/watch/schnitzer.py
src/cls_pdx1/watch/trimet.py
src/cls_pdx1/watch/water_bureau.py
src/spec1_api/auth.py
src/spec1_api/dependencies.py
src/spec1_api/main.py
src/spec1_api/metrics.py
src/spec1_api/routers/adapters.py
src/spec1_api/routers/brief.py
src/spec1_api/routers/cycle.py
src/spec1_api/routers/ingest.py
src/spec1_api/routers/leads.py
src/spec1_api/routers/leg_jud.py
src/spec1_api/routers/metrics.py
src/spec1_api/routers/nodes.py
src/spec1_api/routers/psyop.py
src/spec1_api/routers/publication.py
src/spec1_api/routers/signals.py
src/spec1_api/routers/workspace.py
src/spec1_api/scheduler.py
src/spec1_api/schemas/__init__.py
src/spec1_api/schemas/node_signal.py
src/spec1_api/static/index.html
src/spec1_api/webhooks.py
src/spec1_core/analysts/credibility.py
src/spec1_core/analysts/discovery.py
src/spec1_core/analysts/registry.py
src/spec1_core/api/app.py
src/spec1_core/api/routes.py
src/spec1_core/api/scheduler.py
src/spec1_core/app/cycle.py
src/spec1_core/app/publishers/x.py
src/spec1_core/briefing/generator.py
src/spec1_core/briefing/templates.py
src/spec1_core/briefing/writer.py
src/spec1_core/congressional/analyzer.py
src/spec1_core/congressional/collector.py
src/spec1_core/congressional/cycle.py
src/spec1_core/congressional/parser.py
src/spec1_core/congressional/scorer.py
src/spec1_core/core/engine.py
src/spec1_core/core/ids.py
src/spec1_core/core/logging_utils.py
src/spec1_core/intelligence/analyzer.py
src/spec1_core/intelligence/store.py
src/spec1_core/investigation/generator.py
src/spec1_core/investigation/verifier.py
src/spec1_core/llm/fallback_client.py
src/spec1_core/llm/ollama_manager.py
src/spec1_core/llm/tier3_rules.py
src/spec1_core/main.py
src/spec1_core/psyop/scorer.py
src/spec1_core/schemas/brief.py
src/spec1_core/schemas/models.py
src/spec1_core/signal/complexity.py
src/spec1_core/signal/gates.py
src/spec1_core/signal/harvester.py
src/spec1_core/signal/parser.py
src/spec1_core/signal/scorer.py
src/spec1_core/tools/backfill_jsonl_to_db.py
src/spec1_core/tools/calibration_propose.py
src/spec1_core/tools/generate_brief.py
src/spec1_core/tools/generate_leads.py
src/spec1_core/tools/historical_briefs.py
src/spec1_core/tools/pdf_render.py
src/spec1_core/tools/publication_generator.py
src/spec1_core/tools/run_psyop.py
src/spec1_core/workspace/case.py
src/spec1_core/workspace/cli.py
src/spec1_core/workspace/researcher.py
src/spec1_core/workspace/tracker.py
src/spec1_dual_write_config.py
src/spec1_labels.py
tests/test_adapter_registry.py
tests/test_analysts.py
tests/test_api.py
tests/test_auth.py
tests/test_brief_schemas.py
tests/test_briefing.py
tests/test_calibration.py
tests/test_calibration_proposer.py
tests/test_congressional.py
tests/test_cursor_reader.py
tests/test_cycle.py
tests/test_engine.py
tests/test_fallback_client.py
tests/test_fara.py
tests/test_feed.py
tests/test_harvester.py
tests/test_indexed_queries.py
tests/test_labels_compliance.py
tests/test_leads.py
tests/test_leg_jud.py
tests/test_logging_utils.py
tests/test_mcp_server.py
tests/test_metrics.py
tests/test_narrative.py
tests/test_pdf_render.py
tests/test_pdx1_anomaly.py
tests/test_pdx1_gates.py
tests/test_pdx1_legislation.py
tests/test_pdx1_models.py
tests/test_pdx1_neutrality.py
tests/test_pdx1_pipeline.py
tests/test_pdx1_publication.py
tests/test_pdx1_sources.py
tests/test_pdx1_triggers.py
tests/test_pdx1_watch.py
tests/test_persistence.py
tests/test_pipeline.py
tests/test_psyop.py
tests/test_psyop_evidence.py
tests/test_publication_generator.py
tests/test_scorer.py
tests/test_spec1_api_scheduler.py
tests/test_store.py
tests/test_tools_generate_brief.py
tests/test_tools_generate_leads.py
tests/test_tools_run_psyop.py
tests/test_ui_route.py
tests/test_verdicts.py
tests/test_verifier.py
tests/test_webhooks.py
tests/test_workspace.py
tests/test_world_brief.py
tests/test_x_publisher.py
tools/manual_publisher.py
```

</details>

### 3.4 Recommended remediation for `audit`

`audit` is 157 commits behind and its only unique content is 3 files. Do **not** attempt a
257-file manual resolution.

1. **Cherry-pick, don't merge.** The entire unique payload is:
   - `MERGE_SAFETY_PLAN.md` (371 lines, new)
   - `spec1_ui.html` (373 lines — note `Main` deliberately deleted this file)
   - `src/spec1_api/main.py` (+23 / −1)

   Extract those three with `git checkout origin/audit -- <path>`, normalise to LF, and
   commit onto a fresh branch off `Main`.

2. **Reject the `spec1_analytics/` relocation** unless it is an intentional architecture
   decision. It contradicts the layout in `CLAUDE.md` and deletes the frozen core of
   `spec1_engine`.

3. **Retire the branch** once the three files are salvaged.

---

## 4. Conflict Class B — `claude/adoring-heisenberg-ooptqj` (3 files)

Commits ahead of `Main`:
```
8bab3a5 docs: add NOTITIA CIVICA to product naming registry
54225df fix: resolve remaining conflict markers in requirements.txt, DESIGN_INTENT.md, README.md
```

All three conflicts are **documentation prose**, no code. No CRLF involvement.

### 4.1 `requirements.txt` — 1 hunk

```
  <<<<<<< origin/Main
# Canonical dependencies live in pyproject.toml.
# This file exists for CI/developer convenience.
  =======
# Install the package with dev extras.
# This file is kept as a convenience for CI and developers; the canonical
# dependency list lives in pyproject.toml.
  >>>>>>> origin/claude/adoring-heisenberg-ooptqj
```
Comment wording only. **Resolution: take `Main`.**

### 4.2 `README.md` — 1 hunk

`Main` replaced the bulleted "Daily Intelligence Artifacts" block with the prose
"Daily Research Brief" section. The branch still carries the old bullet list.
**Resolution: take `Main`** (the branch side is the superseded version).

### 4.3 `DESIGN_INTENT.md` — 2 hunks

- Hunk 1: blank-line-only difference.
- Hunk 2: column alignment of the product naming registry — `Main` uses 16-char padding,
  branch uses 19-char padding, for the same three entries (`SWITCHBOARD`, `NOTITIA CIVICA`).

Both sides already contain the `NOTITIA CIVICA` entry, so the branch's stated purpose is
**already satisfied on `Main`**. **Resolution: take `Main`; the branch adds nothing.**

### 4.4 ⚠️ Committed conflict markers — `Makefile`

This branch has **unresolved conflict markers committed to its tip**, despite commit
`54225df` claiming resolution:

```
Makefile:1: <<<<<<< HEAD
Makefile:3: =======
Makefile:5: >>>>>>> origin/develop
```

The conflicting content:
```make
  <<<<<<< HEAD
.PHONY: install test test-fast test-cov lint run mcp cycle backfill calibration workspace clean help brief leads psyop
  =======
.PHONY: install test test-fast test-cov lint run mcp cycle backfill calibration workspace clean help brief leads psyop research
  >>>>>>> origin/develop
```

**This Makefile does not parse.** Any `make` target on this branch fails. The correct
value — the `origin/develop` side, with `research` — is already what `Main` ships.

**Recommendation: delete this branch.** Every change it carries is already on `Main`, and its
only unique state is a broken Makefile.

---

## 5. Conflict Class C — `claude/repo-error-fixes-a7fkin` (2 files)

Commits ahead of `Main`:
```
a296ad5 Merge branch 'dev' into claude/repo-error-fixes-a7fkin
4a86e26 fix: remove stale TODO referencing spec1_engine migration
beadcf5 fix: move all module-level imports to top of file
39a597a fix: rename ambiguous variable 'l' to 'line' or 'lead'
```

Both conflicts are **delete/keep of a duplicated line** — `Main` removed a redundant
assignment, the branch retained it. Each is 1 hunk.

### 5.1 `src/cls_founder_brain/pipeline.py`

```python
def _make_situation_id(description: str) -> str:
    """Generate a unique (time-based) situation ID from description."""
  <<<<<<< origin/Main
  =======
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
  >>>>>>> origin/claude/repo-error-fixes-a7fkin
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    raw = f"{description[:50]}_{ts}"
    return f"sit_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
```

The branch's `ts` is immediately overwritten by the next line — dead code.
**Resolution: take `Main` (delete the line).**

### 5.2 `src/cls_founder_brain/synthesizer.py`

```python
  <<<<<<< origin/Main
  =======
        top_pattern = pattern_matches[0]
  >>>>>>> origin/claude/repo-error-fixes-a7fkin
```

Same pattern — a redundant assignment `Main` already removed.
**Resolution: take `Main` (delete the line).**

Both are two-second resolutions. This branch is otherwise mergeable and its three fix commits
are worth keeping.

---

## 6. Committed conflict markers — full inventory

Four files across two branches carry conflict markers **in committed content**. `Main`, `dev`,
`develop`, and all other branch tips are clean.

| Branch | File | Marker lines | Sides | Impact |
|---|---|---|---|---|
| `claude/adoring-heisenberg-ooptqj` | `Makefile` | 1 / 3 / 5 | `HEAD` vs `origin/develop` | **Makefile unparseable** — all `make` targets fail |
| `copilot/fix-issue-with-data-import` | `Makefile` | 1 / 3 / 5 | `HEAD` vs `origin/develop` | Makefile unparseable |
| `copilot/fix-issue-with-data-import` | `requirements.txt` | 1 / 6 / 20 | `HEAD` vs `origin/copilot/spec-1-define-empty-stubs` | **`pip install -r requirements.txt` fails** |
| `copilot/fix-issue-with-data-import` | `DESIGN_INTENT.md` | 279 / 281 / 282 | `HEAD` vs `origin/develop` | Cosmetic (docs) |

The `copilot/fix-issue-with-data-import` branch is a **fully-merged ancestor of `Main`**
(0 ahead / 37 behind) — the markers were introduced in history and resolved downstream, so
`Main` is unaffected. The branch pointer is stale and safe to delete.

Broken `requirements.txt` on that branch:
```
  <<<<<<< HEAD
# Install the package with dev extras.
# This file is kept as a convenience for CI and developers; the canonical
# dependency list lives in pyproject.toml.
-e .[dev]
  =======
feedparser>=6.0
requests>=2.31
...
pytest-asyncio>=0.23
  >>>>>>> origin/copilot/spec-1-define-empty-stubs
```

---

## 7. Systemic root cause — no `.gitattributes`

The repository has **no `.gitattributes` file on any branch**. Line endings are therefore
whatever each contributor's platform produced, and `Main` itself is already mixed:
**41 text files on `Main` contain CRLF**, including files inside the frozen core.

<details>
<summary>CRLF files currently on <code>Main</code> (41)</summary>

```
CHANGELOG.md
CONTRIBUTING.md
ROADMAP.md
docs/api-integration.md
docs/architecture.md
docs/customization.md
docs/deployment.md
docs/quickstart.md
docs/runbook.md
memory/context.md
memory/decisions.md
pyproject.toml
scripts/run_cycle.sh
scripts/setup_dev.sh
spec1_political_web.html
src/cls_pdx1/__init__.py
src/cls_pdx1/explain/__init__.py
src/cls_pdx1/legislation/__init__.py
src/cls_pdx1/neutrality/__init__.py
src/cls_pdx1/publication/__init__.py
src/cls_pdx1/sources/__init__.py
src/cls_pdx1/watch/__init__.py
src/spec1_api/static/index.html
src/spec1_api/static/spec1_political_web.html
src/spec1_api/static/verdicts.html
src/spec1_core/core/prompts/editorial_voice.md
src/spec1_core/core/prompts/geopolitics_system_prompt.md
src/spec1_core/core/prompts/geopolitics_user_prompt_template.md
src/spec1_core/core/prompts/investigation_prompts.md
src/spec1_core/core/prompts/legislative_system_prompt.md
src/spec1_core/core/prompts/legislative_user_prompt_template.md
src/spec1_core/core/prompts/psyop_scorer.md
src/spec1_core/core/prompts/system_prompt.md
src/spec1_core/core/prompts/user_prompt_template.md
src/spec1_engine/core/prompts/editorial_voice.md
src/spec1_engine/core/prompts/geopolitics_system_prompt.md
src/spec1_engine/core/prompts/geopolitics_user_prompt_template.md
src/spec1_engine/core/prompts/investigation_prompts.md
src/spec1_engine/core/prompts/legislative_system_prompt.md
src/spec1_engine/core/prompts/legislative_user_prompt_template.md
src/spec1_engine/core/prompts/psyop_scorer.md
```

</details>

`scripts/run_cycle.sh` and `scripts/setup_dev.sh` are shell scripts with CRLF — these fail
at runtime on Linux with `bad interpreter: /bin/bash^M` if the shebang line is affected.

**Fix (recommended, but requires human approval since it touches the frozen `core/prompts/`
files):** add a `.gitattributes` at the repo root —

```gitattributes
* text=auto eol=lf
*.png binary
*.pdf binary
*.jpg binary
*.ico binary
*.sh text eol=lf
```

then run `git add --renormalize .` on a dedicated branch. This is a PATCH-level change in
content terms but touches nearly every file, so it should land on its own, immediately after
the branch cleanup below — never alongside feature work.

---

## 8. Prioritised remediation plan

| # | Action | Branch | Risk |
|---|---|---|---|
| 1 | Resolve 2 delete-the-dead-line conflicts, merge | `claude/repo-error-fixes-a7fkin` | Low — real fixes worth keeping |
| 2 | Merge as-is (no conflicts) | `claude/spec-1-workflow-failures-7vhywq` | Low — CI hardening |
| 3 | Merge or drop (1 docs commit, no conflicts) | `temp/notitia-main` | None |
| 4 | **Delete** — all content already on `Main`, only unique state is a broken Makefile | `claude/adoring-heisenberg-ooptqj` | None |
| 5 | **Delete** 4 stale copilot pointers (all 0-ahead ancestors of `Main`; one carries broken markers) | `copilot/*` | None |
| 6 | Cherry-pick 3 files, then retire | `audit` | Medium — verify `spec1_ui.html` deletion on `Main` was intentional before restoring it |
| 7 | Add `.gitattributes` + `git add --renormalize .` on a dedicated branch | new | Medium — touches frozen `core/prompts/`, needs human sign-off |
| 8 | Fast-forward `develop` (11 behind) to `Main` | `develop` | None — protected branch, needs human action |

Executing steps 4–6 removes **260 of the 262 conflicted files** without a single manual
three-way resolution. The remaining 2 (step 1) are one-line deletions.

---

## 9. Verification commands

```bash
# Reproduce any branch's conflict set
git merge-tree --write-tree --name-only --messages origin/Main origin/<branch>

# Prove the audit branch is CRLF-only churn
git diff --numstat --ignore-cr-at-eol $(git merge-base origin/Main origin/audit) origin/audit

# Find committed conflict markers on a branch tip
git grep -n -E '^(<<<<<<< |=======$|>>>>>>> )' origin/<branch>

# List CRLF files on a ref
for f in $(git ls-tree -r --name-only origin/Main); do \
  git show "origin/Main:$f" 2>/dev/null | grep -q $'\r' && echo "$f"; done
```
