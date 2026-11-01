# [ SPEC-1 ] — Case Study

**Portfolio references:** [Landing page](https://mjlak1000.github.io/spec-1/) · [Portfolio summary](portfolio.md) · [README](../README.md)

---

## Who I am

I'm a career switcher. My work history is unusual for a software role: about seventeen years in restaurants and roughly two years at Apple retail during the original iPhone launch. I'm not pretending those add up to a CS degree. They add up to something different — a long stretch of operating under pressure, training people on systems they've never seen before, and triaging information faster than it arrives.

SPEC-1 is the artifact I built to show I can think and ship like an engineer. Everything below is about what I decided and why — because in a portfolio project the *decisions* are the credential, not the line count.

---

## What SPEC-1 is

SPEC-1 is a real-time OSINT platform. It harvests signals from RSS feeds, FARA filings, congressional records, and narrative sources; scores each signal through a four-gate deterministic framework; uses Claude to investigate and verify the survivors; analyzes outcomes; and produces a daily written intelligence brief. Everything is persisted twice — append-only JSONL for audit, SQLite for queries — and exposed as a FastAPI HTTP service and an MCP server so Claude can use the system as a tool.

The point was never the brief. The point was building a pipeline whose decisions I can defend.

---

## Engineering decisions worth talking about

### 1. A deterministic 4-gate filter, not an ML classifier

The obvious move with this much text was to embed everything and rank by similarity. I didn't. Every signal has to clear four explicit gates — `[CREDIBILITY]`, `[VOLUME]`, `[VELOCITY]`, `[NOVELTY]` — each a rule I can read, change, and unit-test. When the system surfaces something wrong, I can point to the gate that failed and the threshold that was off. That's not possible with a model.

The tradeoff is that calibration is manual. The benefit is that calibration is *legible* — every threshold is a decision someone can argue with, and the test suite encodes which boundary cases were considered. For a system whose output is intended to inform human judgment, I'd rather be wrong in a way I can explain than right in a way I can't.

### 2. A frozen core with explicit governance

`src/spec1_core/core/` holds the canonical schemas, ID generation, logging utilities, and the prompt files. It is treated as off-limits to ad-hoc edits — agents (or future me) may import from it, not modify it without an explicit version bump and review. Every prompt in the system lives there as a `.md` file; no inline prompt strings allowed elsewhere.

This isn't paranoia. It's the lesson of seventeen years of operations: the parts of a system everyone touches are the parts that drift. Pulling the contracts and prompts out of the working surface and putting a fence around them is how you keep the system coherent as it grows.

### 3. Dual-write persistence — JSONL and SQLite

JSONL is the system of record: append-only, immutable, audit-friendly. SQLite is the query layer: indexed, fast, easy to inspect, but secondary to the log. `[ cls_db.dual_write ]` writes JSONL first, then attempts SQLite as a non-fatal cache update — so the two can diverge if the SQLite step fails. The API reads through repository abstractions rather than depending on SQLite as source of truth; the database can be rebuilt from the log if needed.

The durability story is obvious: source of truth is plain text on disk. If anything ever looked off, I could `cat` a file and read it. That inspectability is what I trust under pressure, and it's what lets the system survive me being wrong about something else later.

### 4. Test discipline as a calibration anchor

The repo has 1,359 collected pytest tests across 37+ files — covering the engine, OSINT adapters, psyop detection, briefing, persistence, API, MCP server, operator tools, and recent additions (`[ titan ]`, LLM fallback, workspace case management). Test coverage isn't the story — what's in the tests is. Most of them encode a specific decision: this is the threshold we chose, this is the boundary case it has to handle, this is the failure mode we don't want to regress.

When calibration changes, the tests check that nothing else moved silently. That's the property I needed — I can adjust thresholds without lying awake wondering what I broke.

---

## What the non-tech background actually buys you

- **Triage under load.** The whole point of SPEC-1 is sorting too much information into the small subset that matters. That is, structurally, what every shift in a busy kitchen and every hour at an Apple Genius Bar is. The pattern recognition transfers; only the domain changes.
- **Teaching brand-new tech.** Two years explaining the original iPhone to people who had never seen a capacitive touchscreen is two years of doing what good documentation does: meet someone where they are and walk them forward. That shows up here as the README, the architecture diagrams, and the prompts in `core/prompts/`.
- **Operations literacy.** Knowing what fails when, and what you do when it does, is not learned from textbooks. The engineering decisions above — frozen contracts, dual-write durability, deterministic filtering — are operational decisions before they're technical ones.

---

## Recent operational improvements

### Three-tier LLM fallback (`spec1_engine.llm`)

After a few production cycles, every analysis point calling Claude exposed the system to a single-point-of-failure: API downtime, quota exhaustion, or cost spikes. The fix: a fallback chain — Claude Sonnet (primary) → Ollama (local, offline-capable) → rule-based templating (always available, zero latency). The infrastructure must be resilient without being smart. Fallback outputs are deliberately worse, and the analyst knows to weight them accordingly.

### Regional intelligence (`[ titan ]`)

I added a Portland metro module to test whether the same 4-gate framework applies to local political data. It does, but the data sources are different: OLIS (Oregon Legislature OData feed), ORESTAR (campaign finance), SEI (entity registry). Live data, not RSS.

The module revealed something operational: my credibility weights are too coarse for local data. A state legislator and a local city councilor carry different epistemic weight, but the four-gate framework treats them the same. This is fixable via calibration — add jurisdiction weight as a fifth dimension — but it's a data-driven discovery I wouldn't have made without a real use case.

### Workspace case management

The original design pushed all operator decisions onto external tools. Over time that became operationally painful. I built a CLI workspace (`spec1_engine.workspace`) so analysts can open cases, attach notes, file verdicts, and track investigation state without context-switching to a different tool. It's how systems that actually work get built: by operators — even an operator of one — telling engineers what they need.

---

## What I'd do differently

- **The four-gate weights are calibrated against a single observer — me.** Even though the feedback loop is wired end to end (`[ cls_verdicts ]` → `[ cls_calibration ]` → drift proposals), every verdict in the dataset so far is mine. A real framework needs multiple reviewers to detect bias I can't see in my own judgment. The infrastructure exists; the social step doesn't yet.
- **The PDF export pipeline originally embedded `weasyprint` in-process** — native deps in the main process, real deployment friction. Now isolated: `spec1_core.tools.pdf_render` runs weasyprint as a subprocess so the main process never imports it. That's how it should have started.
- **The frontend is a single static HTML file.** The right call for v0.4 — minimal blast radius, no build step, ships with the repo. A real version needs a proper SPA and a versioned API. Deferred deliberately; I know what they are.
- **The core governance violation.** In May 2026, I (via an agent) added four new prompt files directly to `src/spec1_core/core/prompts/` without the human approval I documented as required. The prompts are working, but the violation is real. The rule exists for a reason.

---

## What I'm looking for

A team willing to read the code, look at the decisions, and judge them on their merits. I'm not the candidate with five years at FAANG. I'm the candidate who built a real system end-to-end, who can defend every decision in it, and who has spent two decades learning how to operate things that have to actually work.

I can ship code that gets decisions right, that survives contact with reality, and that remains legible six months later when you need to change it. I care about what breaks, why it breaks, and making sure it doesn't break the same way twice.

If that's a profile you can use, I'd like to talk.

— Matt Lakamp
