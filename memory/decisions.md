# Architecture Decision Records (ADRs)

Significant design decisions are recorded here. Each entry explains what was decided,
why, and what tradeoffs were accepted. This is the institutional memory of the project.

---

## ADR-001 — Deterministic 4-Gate Filter, Not an ML Classifier

**Date:** 2026-04-11
**Status:** Active

**Decision:** Score signals through four explicit, rule-based gates (credibility, volume,
velocity, novelty) rather than training an embedding-based similarity ranker.

**Rationale:** When a gate fails, the specific threshold that failed is visible and
adjustable. That is not possible with a model. For a system whose output informs human
judgment, legible failure modes outweigh automated accuracy improvements. The test suite
encodes every boundary case — calibration changes can be validated without silent
regressions.

**Tradeoff accepted:** Calibration is manual. Thresholds must be adjusted by a human
reading the `cls_calibration` drift report. This is intentional — see ADR-005.

---

## ADR-002 — Frozen Core with Explicit Governance

**Date:** 2026-04-11
**Status:** Active

**Decision:** `src/spec1_core/core/` is off-limits to ad-hoc edits. Agents and
contributors may import from it but may not modify it without a semantic version bump
and explicit human approval. All prompts live in `core/prompts/*.md` — no inline
prompt strings anywhere else in the codebase.

**Rationale:** The parts of a system that everyone touches are the parts that drift.
Separating canonical contracts and prompts from the working surface keeps the system
coherent as it grows and as multiple agents contribute.

**Tradeoff accepted:** New prompt requirements require a PR that touches the frozen
surface, which slows iteration. This is the intended friction — prompt changes are
consequential.

---

## ADR-003 — Dual-Write Persistence: JSONL Primary, SQLite Secondary

**Date:** 2026-04-11
**Status:** Active (expanded in v0.5.1)

**Decision:** JSONL is the system of record — append-only, immutable, auditable.
SQLite is a queryable index that can be rebuilt from the JSONL log at any time.
`cls_db.dual_write` is the write path that writes JSONL first, then attempts SQLite
as a non-fatal operation. The API reads through repository abstractions, not direct
DB queries.

**Rationale:** The JSONL source of truth is plain text on disk — inspectable with
`cat`, reconstructible from scratch, and immune to database corruption. The SQLite
layer is a convenience that must never become a dependency.

**Current coverage (as of v0.5.1):**
- `cls_verdicts/store.py` — always dual-writes.
- `cls_leads/store.py` — opt-in dual-write via `db=` kwarg.
- `cls_psyop/store.py` — opt-in dual-write via `db=` kwarg.
- `intelligence/store.py`, `cls_world_brief/store.py` — still JSONL-only.

Scalable read helpers added:
- `cls_db.cursor_reader.JSONLCursorReader` — cursor-based forward pagination.
- `cls_db.indexed_queries.IndexedQueryLayer` — limit-enforced SQLite queries.
- `spec1_engine.tools.backfill_jsonl_to_db` — JSONL→SQLite migration CLI.

**Tradeoff accepted:** JSONL and SQLite can diverge if a SQLite write fails. This is
accepted because SQLite is the index, not the record. The backfill tool allows
re-syncing the two at any time.

---

## ADR-004 — Rule-Based Briefing Fallback on API Error

**Date:** 2026-04-18
**Status:** Active

**Decision:** The briefing generator calls Claude Sonnet but always falls back to a
rule-based brief if the API call fails for any reason. The cycle never crashes on an
LLM failure.

**Rationale:** The pipeline's value is in the scored intelligence records, not in
whether the brief is LLM-generated. Availability of the system must not depend on
API availability.

**Tradeoff accepted:** Fallback briefs are lower quality. The degradation is explicit
and logged — operators can see when it occurred.

---

## ADR-005 — Calibration Is Descriptive Only, Never Auto-Applied

**Date:** 2026-04-28
**Status:** Active

**Decision:** `cls_calibration` surfaces drift and proposes threshold adjustments as
human-readable reports. It never modifies gate thresholds, source weights, or any
pipeline parameter. Every suggested adjustment must be read, evaluated, and applied
(or rejected) by a human.

**Rationale:** The 4-gate thresholds represent accumulated judgment about what
constitutes a credible, actionable signal in this domain. Automated tuning against
historical verdicts would shift those thresholds toward whatever pattern past verdicts
encoded — including any bias in a single reviewer's judgment (currently all verdicts
are from one reviewer). Auto-tuning without multiple independent reviewers would
launder bias into the system invisibly.

**Tradeoff accepted:** Calibration requires human action. The system does not improve
itself. This is the intended design.

---

## ADR-006 — PDF Rendering as Subprocess

**Date:** 2026-05-03
**Status:** Active

**Decision:** PDF generation uses `weasyprint` via a subprocess
(`spec1_core.tools.pdf_render`) rather than importing it directly in the API or
engine process.

**Rationale:** `weasyprint` carries heavy native dependencies (Cairo, Pango, etc.)
that create deployment friction. Isolating it to a subprocess means the main process
never imports it — the API and engine work without it installed, and the subprocess
can fail without crashing the cycle.

**Tradeoff accepted:** PDF generation has subprocess overhead and requires weasyprint
installed in the environment. This is acceptable for the current use case.

---

## ADR-007 — MCP Server as Separate Entry Point

**Date:** 2026-05-01
**Status:** Active

**Decision:** `mcp_server.py` at the repo root is a standalone MCP server exposing
SPEC-1 tools to Claude. It is separate from the FastAPI application and does not share
a process with the API server.

**Rationale:** MCP and HTTP are distinct surfaces with different clients. Keeping them
separate allows either to be run independently and avoids coupling their lifecycles.

**Tradeoff accepted:** Running both requires two processes. Shared state (JSONL files,
SQLite) is the coordination layer.

---

## ADR-008 — Canonical Cycle Is Lean; Briefs / Leads / Psyop Are Operator Tools

**Date:** 2026-05-09
**Status:** Active

**Decision:** The canonical FastAPI cycle (`POST /cycle/run`, scheduled run, MCP
`run_cycle`) executes only the lean core pipeline: harvest → parse → score →
investigate → verify → analyze → write `IntelligenceRecord` to JSONL. Brief
generation, lead derivation, psyop scoring, calibration proposals, and workspace
case processing are operator-invoked through the richer app/API entrypoints
(`spec1_core.app.cycle`, `POST /brief/generate`, `POST /leads/generate`,
`POST /psyop/run`), each reading from the intelligence JSONL on demand.

**Rationale:** An audit found the docs claimed the canonical cycle automatically
produced briefs, leads, and psyop scores, but the actual `Engine.run()` produced
only intelligence records. The richer behaviour lived in `spec1_core.app.cycle`
and related API routes rather than in the canonical scheduler path. The
split-then-rejoin pattern preserves the trustworthy core, makes downstream artifacts
explicit operator decisions, and keeps the test surface focused. It also matches
the existing pattern of separate operator-invoked tooling for downstream artifacts.

**Tradeoff accepted:** Two execution models coexist for some time. The richer app/API
path remains available for backwards compatibility and operator workflows; the
canonical scheduler does not invoke it automatically. Operators who want a brief
after a scheduled run must call the brief-generation entrypoint explicitly (for
example via `POST /brief/generate` or the MCP `generate_brief` tool). The
simplification is presentational and operational, not algorithmic — no scoring or
persistence semantics changed.

---

## ADR-009 — Research Mode: Analyst-Defined Topic Dossiers

**Date:** 2026-06-20
**Status:** Active

**Decision:** Add Research Mode (`cls_research`) as an operator-invoked tool that allows
analysts to define investigation topics as JSON dossier templates, then run automated
signal collection, expansion, and analysis against those topics. Topics are stored in
`research/topics/topic_*.json`; dossiers (expanded results) are written to
`research/dossiers/` and tracked via `RESEARCH_STATUS_*` enums in `spec1_labels.py`.

**Rationale:** Analysts need a way to define sustained investigations around topics
of interest (e.g., "DPRK missile indigenization", "Portland metro housing policy").
Rather than running ad-hoc searches in the Workspace, Research Mode lets them version
topic definitions and re-run expansions on a schedule or on-demand, maintaining an
append-only audit trail of what signals were collected for each investigation.

**Tradeoff accepted:** Research Mode is decoupled from the canonical cycle. Analysts
invoke it explicitly via `make research`, the MCP `run_research` tool, or the API route.
It reads from the signal and intelligence stores but does not auto-execute. This keeps
the core cycle lean and makes research an intentional operator action.

---
