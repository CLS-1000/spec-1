# SPEC-1 STRATEGIC ACTION PLAN
## 26-Week Roadmap: From Portfolio Project to Sustainable Product
**Status:** DRAFT  
**Last Updated:** May 2026  
**Owner:** Matt Lakamp (EVASTARARCANA LLC)  
**Contact:** spec1_ops@proton.me
---
## EXECUTIVE OVERVIEW
**Current State:** v0.5.0, mature codebase (736 tests), incomplete market positioning  
**Target State:** Sustainable product business with $10-20K MRR, 10-20 paying customers, 100+ active users  
**Timeline:** 26 weeks (6 months)  
**Resource Estimate:** 1 FTE engineering + 0.5 FTE sales/marketing (Phase 2+)
---
## REPOSITORY STRATEGY

```
Phase 1-2 (NOW):
mjlak1000/spec-1                    ← everything here (code, API, tests, docs)
  └── src/
      ├── spec1_core/               ← organizationally separated (same repo)
      ├── spec1_analytics/          ← organizationally separated (same repo)
      └── spec1_api/

Phase 2 Week 9 (new repo, marketing only):
mjlak1000/spec-1                    ← code, unchanged
mjlak1000/spec-1-marketing          ← NEW: portfolio site (Next.js + Vercel)

Phase 3+ (optional — only if licensing or team boundaries justify it):
spec-1-core                         ← AGPL open-source engine (extracted)
spec-1-analytics                    ← Proprietary analytics layer (extracted)
spec-1-saas                         ← Proprietary SaaS layer (extracted)
```

**Default assumption:** monorepo (`mjlak1000/spec-1`) is fine through Phase 3.
A repo split is a deliberate decision gate, not an automatic outcome.

---
## PHASE 1: CONSOLIDATION & CLARITY (Weeks 1-8)
### Goal: Fix architectural loose ends and prepare for external users
### Week 1-2: Foundation Fixes
#### TASK 1.1: Resolve Quant Module Decision
- **Status:** ✅ DONE — Decision: **REMOVE** (option A)
- **Decision:** Remove entirely — orthogonal to core triage mission; market demand not validated
- **Deliverables:**
  - [x] Decision documented in CHANGELOG
  - [x] Code removed (cls_quant never shipped; references cleaned from docs, Makefile, .env.example, README)
  - [x] All tests passing
  - [x] pyproject.toml has no quant extras
- **Commits:**
  - `chore: remove quant module references (out of scope)`
---
#### TASK 1.2: Consolidate Module Naming (Remove Re-export Shims)
- **Status:** 🔴 CRITICAL
- **Current Problem:**
  - `spec1_analytics.cls_leads` is alias to `cls_leads`
  - `spec1_analytics.cls_psyop` is alias to `cls_psyop`
  - `spec1_analytics.cls_world_brief` is alias to `cls_world_brief`
  - These suggest a future refactor that never happened
- **Solution:** Remove all re-export shims; always import from top-level modules
- **Time Estimate:** 2-3 days
- **Deliverables:**
  - [ ] `spec1_analytics/cls_leads.py` → DELETED
  - [ ] `spec1_analytics/cls_psyop.py` → DELETED
  - [ ] `spec1_analytics/cls_world_brief.py` → DELETED
  - [ ] All imports updated throughout codebase
  - [ ] All tests passing
  - [ ] No re-exports remain
- **Files to Update:**
  - `src/spec1_core/__init__.py` (remove re-exports)
  - `src/spec1_api/routers/*.py` (update imports)
  - `src/mcp_server.py` (update imports)
  - `tests/*.py` (update imports)
- **Testing:** 
  - `grep -r "from spec1_core import cls_" src/ tests/` → should return nothing
  - `pytest tests/ -v --tb=short` → all passing
- **Commits:**
  - `refactor: remove re-export shims (cls_leads, cls_psyop, cls_world_brief)`
---
#### TASK 1.3: Add API Versioning (/api/v1/ prefix)
- **Status:** 🔴 CRITICAL (blocks future API stability)
- **Scope:** Prefix all HTTP routes with `/api/v1/`
- **Time Estimate:** 1-2 days
- **Files to Update:**
  - `src/spec1_api/routers/health.py` → `/api/v1/health`
  - `src/spec1_api/routers/signals.py` → `/api/v1/signals`
  - `src/spec1_api/routers/intel.py` → `/api/v1/intel`
  - `src/spec1_api/routers/leads.py` → `/api/v1/leads`
  - `src/spec1_api/routers/brief.py` → `/api/v1/brief`
  - `src/spec1_api/routers/psyop.py` → `/api/v1/psyop`
  - `src/spec1_api/routers/fara.py` → `/api/v1/fara`
  - `src/spec1_api/routers/verdicts.py` → `/api/v1/verdicts`
  - `src/spec1_api/routers/calibration.py` → `/api/v1/calibration`
  - `src/spec1_api/routers/cycle.py` → `/api/v1/cycle/run`
  - `docs/api.md` (update all examples)
  - `tests/test_api.py` (update all test paths)
- **Deliverables:**
  - [ ] All routes prefixed with `/api/v1/`
  - [ ] Documentation updated
  - [ ] Tests updated and passing
  - [ ] Migration guide added to CHANGELOG (breaking change)
- **Testing:** `pytest tests/test_api.py -v`
- **Commits:**
  - `breaking: add /api/v1/ prefix to all routes`
  - `docs: update API examples for /api/v1/`
---
### Week 2-3: Operator Tool Audit
#### TASK 1.4: Audit & Document Operator Tools
- **Status:** 🟡 MEDIUM (tools exist but entry points are unclear)
- **Problem:** Makefile targets reference tools that may not be callable as modules
- **Solution:** Ensure every operator tool is:
  - Callable as `python -m spec1_core.tools.<tool>`
  - Documented in docs/runbook.md
  - Tested in test suite
  - Listed in pyproject.toml `[project.scripts]`
- **Time Estimate:** 2-3 days
- **Operator Tools to Audit:**
  1. `generate_brief` → `python -m spec1_core.tools.generate_brief`
  2. `generate_leads` → `python -m spec1_core.tools.generate_leads`
  3. `run_psyop` → `python -m spec1_core.tools.run_psyop`
  4. `calibration_propose` → `python -m spec1_core.tools.calibration_propose`
  5. `historical_briefs` → `python -m spec1_core.tools.historical_briefs`
  6. `pdf_render` → `python -m spec1_core.tools.pdf_render`
- **Deliverables:**
  - [ ] Each tool has a `__main__.py` entry point
  - [ ] `pyproject.toml` lists all tools under `[project.scripts]`
  - [ ] Makefile targets verified working
  - [ ] docs/runbook.md documents each tool (usage, parameters, output)
  - [ ] Each tool has tests in test suite
  - [ ] `python -m spec1_core.tools.<tool> --help` works
- **Testing:**
  - `python -m spec1_core.tools.generate_brief --help`
  - `python -m spec1_core.tools.run_psyop --help`
  - `make brief` → works
  - `make psyop` → works
  - `make calibration` → works
  - `pytest tests/test_tools.py -v`
- **Commits:**
  - `feat: add entry points for all operator tools`
  - `docs: document operator tool usage in runbook.md`
---
### Week 3-4: Verdict Filing UI
#### TASK 1.5: Build Verdict-Filing Web UI
- **Status:** 🔴 CRITICAL (makes feedback loop real for non-technical users)
- **Scope:** Single-page HTML form to file verdicts on intelligence records
- **Time Estimate:** 5-7 days
- **Deliverables:**
  - [ ] HTML form at `/verdicts/` (served by spec1_api)
  - [ ] Form captures: `record_id`, `verdict_kind`, `notes`, `reviewer_name`
  - [ ] Form submits to `POST /api/v1/verdicts/` (existing endpoint)
  - [ ] Form shows recent records from `GET /api/v1/intel` for easy browsing
  - [ ] Form stores verdicts to `verdicts.jsonl`
  - [ ] Integration tests for form submission
- **Files to Create:**
  - `src/spec1_api/static/verdicts.html` (form UI)
  - `src/spec1_api/routers/static.py` (route for `/verdicts/`)
- **Form Design (Sacred Geometry):**
  - Black/white only
  - Monospace font (IBM Plex Mono)
  - Geometric grid layout
  - No color accents
- **Features:**
  - Record search/filter by record_id or domain
  - Recent records carousel (last 10 analyzed)
  - Verdict kind selector (correct / incorrect / partial / unclear)
  - Notes textarea (optional)
  - Reviewer name field (pre-fill from env var if available)
  - Submit button → stores to verdicts.jsonl
  - Success message with count
- **Testing:**
  - `pytest tests/test_verdicts.py -v`
  - Manual: Visit http://localhost:8000/verdicts/ → submit form → check verdicts.jsonl
- **Commits:**
  - `feat: build verdict-filing web UI at /verdicts/`
  - `test: add integration tests for verdict submission`
---
### Week 4-6: Persistence Layer Systematization
#### TASK 1.6: Systematize Persistence (Dual-Write + Repositories + API)
- **Status:** 🔴 CRITICAL (enables scaling, querying, and enterprise features)
- **Current State:** Only verdicts have full dual-write; other stores are JSONL-only
- **Goal:** Every store (signals, intel, leads, briefs, psyop, calibration) has:
  - JSONL append-only write path
  - SQLite dual-write via `cls_db.dual_write`
  - Repository abstraction (read interface)
  - API read endpoint
- **Time Estimate:** 10-14 days
- **Stores to Systematize:**

| Store | JSONL | SQLite | Repository | API Endpoint | Status |
|-------|-------|--------|------------|--------------|--------|
| Signals | ✓ | ✓ | ✓ | GET /api/v1/signals | ✓ Complete |
| Intelligence Records | ✓ | ✓ | ✓ | GET /api/v1/intel | ✓ Complete |
| Leads | ✓ | ⚠️ Partial | ⚠️ Partial | ✓ Complete | ⚠️ WIP |
| Briefs | ✓ | ⚠️ Partial | ⚠️ Partial | ✓ Complete | ⚠️ WIP |
| PsyOp Scores | ✓ | ⚠️ Partial | ⚠️ Partial | ✓ Complete | ⚠️ WIP |
| Calibration Reports | ✓ | ⚠️ Partial | ⚠️ Partial | GET /api/v1/calibration | ⚠️ WIP |
| Verdicts | ✓ | ✓ | ✓ | GET /api/v1/verdicts | ✓ Complete |

- **Tasks:**
  - [ ] Add SQLite models for leads, briefs, psyop, calibration (if not present)
  - [ ] Add repository abstractions for each store
  - [ ] Wire dual_write into each store's write path
  - [ ] Add read endpoints for each store (API routers)
  - [ ] Update docs/architecture.md with persistence status
  - [ ] All tests passing
- **Files to Modify:**
  - `src/cls_db/models.py` (add SQLite schemas)
  - `src/cls_db/repository.py` (add CRUD methods)
  - `src/cls_world_brief/store.py` (add dual_write)
  - `src/cls_leads/store.py` (add dual_write)
  - `src/cls_psyop/store.py` (add dual_write)
  - `src/cls_calibration/store.py` (add dual_write)
  - `src/spec1_api/routers/*.py` (use repositories)
  - `tests/test_persistence.py` (add new tests)
- **Testing:**
  - `pytest tests/test_persistence.py -v`
  - Manual: Run cycle → check both JSONL and SQLite contain records
  - API: `curl http://localhost:8000/api/v1/intel | jq` → should return records
- **Commits:**
  - `feat: add SQLite models for all stores`
  - `feat: add repository abstractions for all stores`
  - `feat: enable dual-write for leads, briefs, psyop, calibration`
  - `test: add comprehensive persistence tests`
---
### Week 6-8: Documentation Expansion
#### TASK 1.7: Expand Documentation (Getting Started, Deployment, Customization)
- **Status:** 🟡 MEDIUM (critical for onboarding external users)
- **Goal:** A new user can clone, setup, run, and customize SPEC-1 in < 30 minutes
- **Time Estimate:** 5-7 days
- **Documentation to Create/Expand:**

1. **Getting Started Quickstart** (`docs/quickstart.md`)
   - [ ] System requirements (Python 3.9+, pip, git)
   - [ ] 5-minute setup walkthrough
   - [ ] `bash scripts/setup_dev.sh` → run cycle → view results
   - [ ] Common first-run issues + solutions
   - [ ] One-minute run of MCP server with Claude

2. **Deployment Guide** (`docs/deployment.md`)
   - [ ] Docker setup (Dockerfile + docker-compose.yml to create)
   - [ ] Systemd service file for Linux
   - [ ] Environment variable reference with examples
   - [ ] Cloud deployment (AWS Lambda, Render, Railway, etc.)
   - [ ] Database setup and migrations
   - [ ] Scheduling configuration (cron hour, timezone)
   - [ ] Health check and monitoring setup

3. **Customization Guide** (`docs/customization.md`)
   - [ ] How to add a new RSS source
   - [ ] How to add a new signal adapter (FARA-like)
   - [ ] How to modify scoring thresholds
   - [ ] How to change analyst weights
   - [ ] How to customize brief templates
   - [ ] How to integrate with external APIs (Slack, email, webhook)
   - [ ] Code examples for each customization

4. **Troubleshooting Guide** (expand `docs/runbook.md`)
   - [ ] "Cycle is slow" → diagnosis and fixes
   - [ ] "Claude API returns errors" → fallback behavior explained
   - [ ] "No intelligence records generated" → threshold debugging
   - [ ] "Database is out of sync with JSONL" → recovery procedure
   - [ ] "Tests fail on my machine" → common causes

5. **API Integration Guide** (`docs/api-integration.md`)
   - [ ] Slack webhook integration
   - [ ] Email digest delivery
   - [ ] S3 export of briefs
   - [ ] GitHub Actions trigger
   - [ ] Zapier/IFTTT integration pattern

- **Deliverables:**
  - [ ] 5 new documentation files (500-1000 words each)
  - [ ] All docs linked from main README
  - [ ] All code examples tested and working
  - [ ] Screenshots or diagrams where helpful (sacred geometry aesthetic)
  - [ ] Table of contents in each doc for easy navigation
- **Testing:**
  - Follow quickstart guide from scratch → should work
  - Deploy to Docker locally → should work
  - Customize example → should work
- **Commits:**
  - `docs: add getting started quickstart`
  - `docs: add deployment guide with Docker and systemd`
  - `docs: add customization guide with examples`
  - `docs: expand troubleshooting section`
---
### Week 8: Testing & Cleanup
#### TASK 1.8: Quality Gate & Release
- **Status:** 🟢 CLEANUP
- **Time Estimate:** 2-3 days
- **Deliverables:**
  - [ ] All tests passing: `pytest tests/ -v --tb=short`
  - [ ] Code quality check: `flake8 src/ tests/ --max-line-length=120`
  - [ ] No imports from removed modules (grep verify)
  - [ ] CHANGELOG.md updated with all changes from Phase 1
  - [ ] Version bumped to 0.6.0 (MINOR version: consolidation + new features)
  - [ ] README.md links updated to new docs
  - [ ] All Makefile targets working
- **Commits:**
  - `chore: bump version to 0.6.0`
  - `docs: update README with Phase 1 changes`
---
## PHASE 1 DELIVERABLES SUMMARY

| Task | Status | Time | Completion Criteria |
|------|--------|------|-------------------|
| 1.1 Resolve Quant Module | ✓ | 1-2d | Decision made; code updated; tests pass |
| 1.2 Consolidate Naming | ✓ | 2-3d | No re-exports; all imports from top-level |
| 1.3 API Versioning | ✓ | 1-2d | All routes prefixed `/api/v1/` |
| 1.4 Operator Tools | ✓ | 2-3d | All tools callable as modules; documented |
| 1.5 Verdict UI | ✓ | 5-7d | Form at `/verdicts/` functional; tests pass |
| 1.6 Persistence Layer | ✓ | 10-14d | All stores have dual-write + API |
| 1.7 Documentation | ✓ | 5-7d | 5 new docs; user can setup in <30 min |
| 1.8 Quality Gate | ✓ | 2-3d | All tests pass; v0.6.0 released |

**Phase 1 Total Time: ~35-40 engineering days (~8 weeks, 1 FTE)**

**Phase 1 Exit Criteria:**
- ✓ Codebase is clean and consolidated
- ✓ All operator tools are documented and working
- ✓ Verdict feedback loop is real (UI exists)
- ✓ Persistence is systematic (no JSONL-only stores)
- ✓ New user can setup and customize in <30 minutes
- ✓ All tests passing; no technical debt blockers
---
## PHASE 2: POSITIONING & COMMERCIAL PATHS (Weeks 9-16)
### Goal: Build distinct positioning for core engine vs. analytics; enable multiple monetization paths
### Week 9: Repo Organization & Planning
#### TASK 2.1: Reorganize `src/` for Future Modularity (in-repo only)
- **Status:** 🟡 MEDIUM (folder rename within `mjlak1000/spec-1` — no repo split yet)
- **Goal:** Reorganize `src/` so `spec1_core` and `spec1_analytics` are visually distinct,
  making a future optional repo split straightforward without requiring one now.
- **Scope:** Folder renames inside `mjlak1000/spec-1` only. No new repositories.
- **Time Estimate:** 2-3 days
- **Repo layout after this task:**
  ```
  mjlak1000/spec-1          ← everything stays here (Phase 1 & 2)
  └── src/
      ├── spec1_core/           ← harvest → verify → store (canonical cycle)
      │   ├── signal/
      │   ├── investigation/
      │   ├── intelligence/
      │   └── core/
      ├── spec1_analytics/      ← briefs, leads, psyop
      │   ├── cls_world_brief/
      │   ├── cls_leads/
      │   └── cls_psyop/
      ├── spec1_api/            ← HTTP + MCP surfaces
      ├── cls_osint/            ← adapters
      ├── cls_verdicts/         ← feedback
      ├── cls_calibration/      ← feedback
      └── cls_db/               ← persistence
  ```
- **Future repo split (Phase 3+, optional — only if justified):**
  ```
  spec-1-core        ← AGPL open-source engine (extracted from spec1_core/)
  spec-1-analytics   ← Proprietary analytics layer (extracted from spec1_analytics/)
  spec-1-saas        ← Proprietary SaaS/hosting layer
  ```
  Monorepo is equally valid; split only if licensing or team boundaries demand it.
- **Deliverables:**
  - [ ] `src/spec1_core/` (done — renamed from spec1_engine + all imports updated)
  - [ ] `src/cls_world_brief/`, `src/cls_leads/`, `src/cls_psyop/` → `src/spec1_analytics/`
  - [ ] All other top-level packages (`cls_osint`, `cls_verdicts`, etc.) remain at `src/`
  - [ ] All imports updated throughout codebase
  - [ ] All tests passing
  - [ ] docs/architecture.md updated to show new structure
  - [ ] No functional changes
- **Commits:**
  - `refactor: reorganize src/ into spec1_core/ and spec1_analytics/ (in-repo)`
---
#### TASK 2.2: Plan Independent Portfolio Site
- **Status:** 🟡 MEDIUM (planning + design, no code yet)
- **Goal:** Design separate marketing site (not GitHub Pages) with positioning.
  Lives in a **new repo `mjlak1000/spec-1-marketing`** — completely separate from the
  code repo so marketing changes never touch the engine.
- **Time Estimate:** 3-5 days (planning + design)
- **Deliverables:**
  - [ ] Domain name selected (e.g., spec1.ai, spec1intelligence.io)
  - [ ] `mjlak1000/spec-1-marketing` repo created (Next.js skeleton, README, deploy config)
  - [ ] Site architecture documented (landing, features, pricing, blog, docs, case studies)
  - [ ] Positioning content drafted (open-source core vs. commercial analytics)
  - [ ] Pricing tiers documented (free, pro, enterprise)
  - [ ] Hosting provider selected (Vercel recommended — native Next.js support)
#### TASK 2.1: Reorganize for Future Modularity
- **Status:** 🟡 MEDIUM (organizational change, no functional changes)
- **Goal:** Signal future separation of core engine + analytics without splitting yet
- **Time Estimate:** 2-3 days
- **Changes (Folder Structure Only):**
  ```
  Current:
  src/
  ├── spec1_core/
  └── cls_*/
  
  Reorganize to:
  src/
  ├── spec1_core/           ← harvest → verify → store (canonical cycle)
  │   ├── signal/
  │   ├── investigation/
  │   ├── intelligence/
  │   └── core/
  ├── spec1_analytics/      ← briefs, leads, psyop, quant
  │   ├── cls_world_brief/
  │   ├── cls_leads/
  │   ├── cls_psyop/
  │   └── cls_quant/
  ├── spec1_api/            ← HTTP + MCP surfaces
  ├── cls_osint/            ← adapters (keep top-level)
  ├── cls_verdicts/         ← feedback (keep top-level)
  ├── cls_calibration/      ← feedback (keep top-level)
  └── cls_db/               ← persistence (keep top-level)
  ```
- **Rationale:** Prepares for future `spec-1-core` (open-source engine) vs. `spec-1-analytics` (commercial)
- **Deliverables:**
  - [ ] Folders reorganized as above
  - [ ] All imports updated
  - [ ] All tests passing
  - [ ] docs/architecture.md updated to show structure
  - [ ] No functional changes
- **Commits:**
  - `refactor: reorganize src/ to signal future core/analytics separation`
---
#### TASK 2.2: Plan Independent Portfolio Site
- **Status:** 🟡 MEDIUM (planning + design, no code yet)
- **Goal:** Design separate marketing site (not GitHub Pages) with positioning
- **Time Estimate:** 3-5 days (planning + design)
- **Deliverables:**
  - [ ] Domain name selected (e.g., spec1.ai, spec1intelligence.io)
  - [ ] Site architecture documented (landing, features, pricing, blog, docs, case studies)
  - [ ] Positioning content drafted (open-source core vs. commercial analytics)
  - [ ] Pricing tiers documented (free, pro, enterprise)
  - [ ] Hosting provider selected (Vercel, Netlify, AWS, etc.)
  - [ ] Design mockups (sacred geometry aesthetic consistent with brand)
  - [ ] Blog content plan (3-5 posts on signal detection, triage automation, etc.)
- **Content Outline:**
  - Landing page: Hero, problem statement, solution overview, positioning
  - Features page: Core engine, analytics layers, integrations
  - Pricing page: Free tier (always), Pro tier ($200/mo), Enterprise (custom)
  - Blog: Thought leadership on OSINT, signal detection, triage
  - Case studies: 2-3 public case studies (journalist, nonprofit, threat intel)
  - Docs link: Pointing to `mjlak1000/spec-1` GitHub repo for technical docs
- **Commits (in `spec-1-marketing`):**
  - `chore: init spec-1-marketing repo (Next.js + Vercel)`
  - `docs: add portfolio site planning document`
---
### Week 9-12: Portfolio Site Build
#### TASK 2.3: Build Independent Portfolio Site (`mjlak1000/spec-1-marketing`)
- **Status:** 🟡 MEDIUM (2-3 weeks of design + development)
- **Repo:** `mjlak1000/spec-1-marketing` (separate from code repo — created in Task 2.2)
- **Time Estimate:** 8-10 days
- **Tech Stack:** Next.js + Vercel (fast, low-friction, native Next.js support)
  - Docs link: Pointing to GitHub repo for technical docs
- **Commits:**
  - `docs: add portfolio site planning document`
---
### Week 9-12: Portfolio Site Build
#### TASK 2.3: Build Independent Portfolio Site
- **Status:** 🟡 MEDIUM (2-3 weeks of design + development)
- **Time Estimate:** 8-10 days
- **Tech Stack Recommendation:** Next.js + Vercel (fast, low-friction, good for SaaS sites)
- **Deliverables:**
  - [ ] Domain registered and DNS configured
  - [ ] Site deployed and live at spec1.ai (or chosen domain)
  - [ ] Landing page with positioning (core engine + commercial analytics)
  - [ ] Features page (comprehensive feature list, differentiators)
  - [ ] Pricing page (free, pro, enterprise tiers with descriptions)
  - [ ] Blog (initial 3 posts on signal detection, OSINT, triage)
  - [ ] Case studies (2-3 public customer stories)
  - [ ] Press kit / media resources
  - [ ] Email signup for launch announcement
  - [ ] Analytics setup (Google Analytics 4 or Plausible)
- **Key Positioning Messaging:**
  - **Headline:** "SPEC-1: Intelligence Triage Automation for Journalists, Analysts, and Researchers"
  - **Subheading:** "Separate signal from noise. Investigate automatically. Brief decisively."
  - **Value Props:**
    1. Open-source deterministic core (transparent, auditable, no black boxes)
    2. Commercial analytics (briefs, leads, psyop detection, custom sources)
    3. Fast, accurate triage (4-gate filter + Claude verification)
    4. Pricing that scales (free for individuals, pay for features)
- **SEO Strategy:**
  - Target keywords: OSINT automation, signal detection, intelligence briefing, threat intel triage
  - Blog posts for organic traffic
  - Link building to GitHub repo
- **Commits:**
  - `feat: build independent portfolio site at spec1.ai`
  - `docs: add case studies to portfolio site`
---
### Week 12-14: SaaS Architecture & Commercial Strategy
#### TASK 2.4: Document SaaS Architecture (Not Built Yet, Just Planned)
- **Status:** 🟡 MEDIUM (planning + documentation)
- **Goal:** Lay out what a hosted version would look like
- **Time Estimate:** 3-5 days
- **Deliverables:**
  - [ ] SaaS architecture document (50-100 page design doc or shorter summary)
  - [ ] User signup and onboarding flow
  - [ ] Multi-tenant architecture (or single-tenant SaaS)
  - [ ] Pricing model calculation (cost to serve vs. revenue per tier)
  - [ ] Integration strategy (Slack, email, webhook, S3 export)
  - [ ] Metrics and analytics dashboard
  - [ ] Deployment architecture (serverless vs. containerized)
  - [ ] Security and compliance checklist (SOC 2, data residency, etc.)
  - [ ] Roadmap for SaaS MVP (timeline, features, cost estimate)
- **Document Structure:**
  - Executive summary (1 page)
  - User flows (onboarding, cycle setup, brief generation, verdict filing)
  - Architecture diagram (auth, API, workers, database, storage)
  - Cost model (infrastructure cost, SaaS cost, margin calculation)
  - Competitive analysis (Recorded Future, Maltego, SpiderFoot, custom)
  - Pricing tiers with unit economics
  - Launch roadmap (Phase 3)
- **Commits:**
  - `docs: add SaaS architecture and business model documentation`
---
#### TASK 2.5: Document Licensing & Commercial Strategy
- **Status:** 🔴 CRITICAL (unblocks all future monetization)
- **Goal:** Decide on licensing and commercial model
- **Time Estimate:** 3-5 days
- **Decisions Needed:**

1. **Open-Source License for Core:**
   - Options: Apache 2.0, MIT, AGPL, Elastic License, Business Source License
   - **Recommendation:** **AGPL** (copyleft, forces commercial users to open-source or buy license)
   - **Rationale:** Protects open-source nature while incentivizing commercial licensing

2. **Commercial License:**
   - **Dual-licensing strategy:** AGPL for open-source users, proprietary commercial license for companies
   - **Price per tier:**
     - Free tier: AGPL, self-hosted, unlimited use
     - Pro tier: $200/mo, SaaS hosted, unlimited users, email support
     - Enterprise: Custom pricing, dedicated support, custom integrations, on-premise option

3. **Commercial Features vs. Open-Source:**
   - **Open-source core (AGPL):**
     - Harvest → verify → store (canonical cycle)
     - RSS/FARA/Congressional adapters
     - Basic API
   - **Commercial analytics (proprietary):**
     - Daily world briefs (Claude Sonnet generation)
     - Actionable leads (with advanced ranking)
     - PsyOp detection
     - Custom signal sources (marketplace)
     - SaaS hosting and multi-user management
     - Integrations (Slack, email, webhook)
     - Priority support

- **Deliverables:**
  - [ ] Licensing document (LICENSE.txt + COMMERCIAL_LICENSE.txt)
  - [ ] Commercial strategy document (pricing, tiers, go-to-market)
  - [ ] License headers added to source files
  - [ ] GitHub repo README updated with licensing info
  - [ ] Pricing page on portfolio site
- **Commits:**
  - `chore: adopt AGPL licensing for spec1-core`
  - `docs: add commercial licensing and pricing strategy`
---
### Week 14-16: Community Building & Case Studies
#### TASK 2.6: Create Public Case Studies & Testimonials
- **Status:** 🟡 MEDIUM (requires early user interviews)
- **Goal:** Identify 2-3 early users; document their use cases; publish case studies
- **Time Estimate:** 5-7 days
- **Strategy:**
  - Identify early users from Phase 1 (people who have run SPEC-1 or expressed interest)
  - Interview them (30-60 min calls, 2-3 questions: what problem did SPEC-1 solve, what metrics improved, what would you recommend)
  - Write up case studies (500-1000 words each, with quotes, metrics, lessons)
  - Publish on portfolio site
  - Share on social media + communities
- **Case Study Template:**
  - **Organization name & description**
  - **Challenge (what problem did they face)**
  - **Solution (how SPEC-1 helped)**
  - **Results (metrics: time saved, signals detected, briefs generated, etc.)**
  - **Quote from user**
  - **Lessons learned**
- **Target Case Studies:**
  1. **Journalist:** "How SPEC-1 helped me break a story on X in Y days"
  2. **Civil rights org:** "How SPEC-1 automated policy monitoring and caught a threat before it passed"
  3. **Threat intel analyst:** "How SPEC-1 reduced signal noise by 80% and freed up 10 hours/week"
- **Deliverables:**
  - [ ] 2-3 user interviews completed
  - [ ] 2-3 case studies written (500-1000 words each)
  - [ ] Case studies published on portfolio site
  - [ ] Testimonials quoted on landing page
  - [ ] Permission received for public attribution
- **Commits:**
  - `docs: add case studies to portfolio site`
---
#### TASK 2.7: Launch Community & Social Presence
- **Status:** 🟡 MEDIUM (ongoing engagement)
- **Goal:** Build community foundations for Phase 3 growth
- **Time Estimate:** 3-5 days (initial setup + content)
- **Channels:**

1. **GitHub Discussions**
   - [ ] Enable Discussions on GitHub repo
   - [ ] Create categories: General, Feature Requests, Showcase, Q&A
   - [ ] Pin introduction post with roadmap + community guidelines
   - [ ] Welcome first 10 participants

2. **Social Media (Twitter/X)**
   - [ ] Create @SPEC1Intelligence account (or similar)
   - [ ] Bio: "Open-source intelligence triage. Signal detection + verification + briefs. For journalists, researchers, and analysts."
   - [ ] Initial posts (5-10): Why triage matters, feature announcements, case studies, thought leadership
   - [ ] Follow relevant accounts (journalists, OSINT researchers, think tanks)
   - [ ] Engage with community (retweet relevant research, answer questions)

3. **Email Newsletter**
   - [ ] Setup Substack or Beehiiv (free tier)
   - [ ] Monthly updates: new features, case studies, thought leadership
   - [ ] Signup form on portfolio site

- **Content Calendar (Phase 2 + early Phase 3):**
  - Week 1: Launch announcement + roadmap
  - Week 2: Case study 1 (journalist)
  - Week 3: Feature deep-dive (4-gate filter)
  - Week 4: Case study 2 (nonprofit)
  - Month 2: Blog post on OSINT trends
  - Month 2: Feature announcement (Phase 2 completion)
  - Month 3: Thought leadership on signal detection
  - Ongoing: Community Q&A, retweets, engagement

- **Deliverables:**
  - [ ] GitHub Discussions enabled and active
  - [ ] Twitter account created with 3-5 initial posts
  - [ ] Newsletter signup form integrated
  - [ ] Content calendar documented
  - [ ] Community guidelines written and pinned
- **Commits:**
  - `docs: add community guidelines to GitHub Discussions`
  - `docs: document social media + community strategy`
---
## PHASE 2 DELIVERABLES SUMMARY

| Task | Status | Time | Completion Criteria |
|------|--------|------|-------------------|
| 2.1 Repo Reorganization | ✓ | 2-3d | Folders restructured; imports updated; tests pass |
| 2.2 Portfolio Site Planning | ✓ | 3-5d | Domain selected; content planned; design mockups done |
| 2.3 Portfolio Site Build | ✓ | 8-10d | Site live at spec1.ai; 3 blog posts published |
| 2.4 SaaS Architecture Doc | ✓ | 3-5d | Architecture documented; cost model calculated |
| 2.5 Licensing & Commercial | ✓ | 3-5d | AGPL adopted; commercial license written; pricing decided |
| 2.6 Case Studies | ✓ | 5-7d | 2-3 case studies published with metrics |
| 2.7 Community Launch | ✓ | 3-5d | Discussions, Twitter, newsletter active |

**Phase 2 Total Time: ~30-40 days (~8 weeks, 0.5-1 FTE engineering + 0.5 FTE marketing)**

**Phase 2 Exit Criteria:**
- ✓ Positioning is clear (core engine vs. commercial analytics)
- ✓ Portfolio site is live with case studies and blog
- ✓ SaaS architecture is planned (ready for Phase 3 build)
- ✓ Licensing and pricing strategy is documented
- ✓ Community is active (Discussions, Twitter, newsletter)
- ✓ 5-10 early users engaged and providing feedback
---
## PHASE 3: GROWTH & MONETIZATION (Weeks 17-26)
### Goal: Grow user base, launch commercial offerings, and build sustainable operations
### Week 17-24: SaaS MVP Development
#### TASK 3.1: Build SaaS MVP (Hosted SPEC-1)
- **Status:** 🔴 CRITICAL (largest Phase 3 task)
- **Goal:** Launch hosted version of SPEC-1 with pre-configured templates and managed infrastructure
- **Time Estimate:** 16-20 days (requires 2 FTE or 1 FTE over longer period)
- **Scope:**
  - Multi-user authentication (OAuth or email/password)
  - Pre-configured signal templates (journalist, compliance, threat intel)
  - Web UI for verdicts, settings, integrations
  - Email digest delivery of daily briefs
  - Slack integration for brief notifications
  - Webhook support for custom integrations
  - Tiered pricing (Free, Pro $200/mo, Enterprise custom)
  - Payment processing (Stripe)
  - Billing dashboard (usage, invoices)
- **Tech Stack:**
  - Backend: spec1_api (existing)
  - Frontend: React SPA (new)
  - Database: PostgreSQL (scalable SQLite alternative)
  - Auth: Auth0 or Firebase Auth
  - Hosting: AWS Lambda + RDS, or Render/Railway
  - Payments: Stripe API
- **Deliverables:**
  - [ ] User authentication system working
  - [ ] Pre-configured signal templates available
  - [ ] Multi-user workspace (users → accounts → projects)
  - [ ] Web UI for verdicts and settings
  - [ ] Email digest delivery working
  - [ ] Slack integration working
  - [ ] Webhook integration working
  - [ ] Stripe payments integrated
  - [ ] Billing dashboard functional
  - [ ] SaaS deployed and live at spec1.ai
  - [ ] Tier 1 customers onboarded and paying
- **Commitment Path:**
  - Week 17-18: Infrastructure + auth setup
  - Week 18-20: Multi-tenant data model + UI
  - Week 20-21: Integrations (Slack, email, webhook)
  - Week 21-22: Stripe payments + billing
  - Week 22-23: Testing + hardening
  - Week 23-24: Initial customer onboarding
- **Commits:**
  - `feat: add OAuth authentication for SaaS`
  - `feat: add multi-tenant workspace system`
  - `feat: build SaaS UI (React) for verdicts and settings`
  - `feat: integrate Slack notifications`
  - `feat: integrate Stripe payments and billing`
  - `chore: deploy SaaS to production`
---
#### TASK 3.2: Custom Signal Adapter Marketplace
- **Status:** 🟡 MEDIUM (depends on 3.1 completion)
- **Goal:** Allow users to contribute custom signal adapters
- **Time Estimate:** 5-7 days
- **Scope:**
  - Upload/submit custom adapter code (Python module)
  - Review process (human + automated tests)
  - Publish approved adapters to marketplace
  - Install adapters via SaaS UI (one-click)
  - Revenue share or credit model (e.g., 30% of sales from adapter)
- **Deliverables:**
  - [ ] Marketplace webpage (showcase community adapters)
  - [ ] Adapter submission form
  - [ ] Automated testing of submitted adapters
  - [ ] Review workflow (approve/reject)
  - [ ] One-click install in SaaS
  - [ ] 5-10 initial adapters (custom sources, partner data)
  - [ ] Documentation for building adapters
- **Commits:**
  - `feat: build custom adapter marketplace`
---
### Week 24-26: Documentation, Sales, & Scaling
#### TASK 3.3: Expanded Documentation & Tutorials
- **Status:** 🟡 MEDIUM (content creation)
- **Goal:** Create video tutorials, integration guides, and API reference
- **Time Estimate:** 5-7 days
- **Deliverables:**
  - [ ] 5-10 video tutorials (5-10 min each):
    - Getting started with SPEC-1
    - Setting up your first signal sources
    - Customizing scoring thresholds
    - Filing verdicts and calibration
    - Slack integration setup
    - Building a custom adapter
  - [ ] Integration guides for popular tools (email, Slack, Zapier, IFTTT, GitHub Actions)
  - [ ] API reference (OpenAPI/Swagger)
  - [ ] Troubleshooting guide for SaaS issues
  - [ ] Video + blog post for each major feature
- **Distribution:**
  - YouTube channel (SPEC-1 Intelligence)
  - Embed videos on portfolio site
  - Link from docs
  - Share on social media
- **Commits:**
  - `docs: add video tutorials and integration guides`
---
#### TASK 3.4: Sales & Partnership Execution
- **Status:** 🟡 MEDIUM (business development, not engineering)
- **Goal:** Acquire 10-20 paying customers by end of Phase 3
- **Time Estimate:** Ongoing (5 days ops/month from engineering; 1 FTE sales person)
- **Strategy:**

1. **Direct Sales (B2B):**
   - Target threat intel shops (2-10 analysts)
   - Email outreach to contacts from case studies + community
   - Demo call → trial → conversion
   - Target: $500-2K/mo per customer

2. **Partnership Sales:**
   - Investigative journalism nonprofits (INN, Reveal, ProPublica)
   - Civil liberties orgs (EFF, CAIR, ACLU)
   - Policy research orgs (think tanks)
   - Partner terms: White-label or revenue share or early access to features

3. **Community Sales:**
   - Leverage GitHub Discussions, Twitter, newsletter
   - Testimonials + case studies → inbound interest
   - Free tier for community members → paid conversion

- **Metrics to Track:**
  - Signups (free tier)
  - Trial-to-paid conversion rate
  - Customer acquisition cost (CAC)
  - Monthly recurring revenue (MRR)
  - Churn rate
  - Customer lifetime value (LTV)
  - Target: 10-20 paying customers, $10-20K MRR by week 26
- **Commits:**
  - `docs: add sales process and customer onboarding docs`
---
#### TASK 3.5: Analytics, Monitoring & Observability
- **Status:** 🟡 MEDIUM (infrastructure + instrumentation)
- **Goal:** Add metrics and dashboards for operational visibility
- **Time Estimate:** 3-5 days
- **Deliverables:**
  - [ ] Instrumentation added to API (latency, throughput, errors)
  - [ ] Instrumentation added to cycle (duration, signals/sec, records/sec)
  - [ ] Metrics collection (Prometheus or similar)
  - [ ] Dashboard built (Grafana or in-house)
  - [ ] Alerts configured (cycle failure, API errors, SLA violations)
  - [ ] Customer metrics dashboard (usage, cost, verdicts filed, etc.)
  - [ ] Analytics (Google Analytics 4) on portfolio site + SaaS
- **Key Metrics to Track:**
  - **Infrastructure:**
    - API latency (p50, p99)
    - API throughput (req/s)
    - API error rate
    - Cycle duration (min)
    - Cycle success rate
    - Database query latency
  - **Product:**
    - Signals harvested (per cycle)
    - Opportunities generated (per cycle)
    - Intelligence records created (per cycle)
    - Briefs generated (per run)
    - Leads generated (per run)
    - Verdicts filed (per week)
  - **Business:**
    - User signups (free tier)
    - Trial conversions
    - MRR
    - Churn rate
    - NPS (Net Promoter Score)
- **Commits:**
  - `feat: add metrics and observability to API`
  - `feat: add operator dashboard with analytics`
---
#### TASK 3.6: Performance Improvements (Async/Await Refactor)
- **Status:** 🟡 MEDIUM (optimization, not critical but important for scale)
- **Goal:** Refactor signal fetching to use async/await; enable concurrent multi-source pipelines
- **Time Estimate:** 5-7 days
- **Current State:** Synchronous feed fetching (blocking I/O)
- **Improvement:** Async/await with httpx (concurrent HTTP requests)
- **Expected Impact:** 2-3x speedup for multi-source pipelines
- **Deliverables:**
  - [ ] Signal harvester refactored to async
  - [ ] Feed fetching uses httpx (async HTTP client)
  - [ ] Concurrent fetching of multiple feeds
  - [ ] All tests passing
  - [ ] Performance benchmarks documented (before/after)
  - [ ] Backward compatibility maintained
- **Commits:**
  - `perf: refactor signal fetching to async/await`
  - `test: add performance benchmarks for pipeline`
---
## PHASE 3 DELIVERABLES SUMMARY

| Task | Status | Time | Completion Criteria |
|------|--------|------|-------------------|
| 3.1 SaaS MVP | ✓ | 16-20d | SaaS live; auth working; tier 1 customers onboarded |
| 3.2 Adapter Marketplace | ✓ | 5-7d | 5-10 adapters in marketplace; users can install |
| 3.3 Tutorials & Docs | ✓ | 5-7d | 10 video tutorials published; integration guides done |
| 3.4 Sales & Partnerships | ✓ | Ongoing | 10-20 paying customers acquired; partnerships signed |
| 3.5 Analytics | ✓ | 3-5d | Metrics and dashboards live; alerts configured |
| 3.6 Performance Improvements | ✓ | 5-7d | Async pipeline deployed; 2-3x speedup measured |

**Phase 3 Total Time: ~50-60+ days over 10 weeks (1-2 FTE engineering + 1 FTE sales)**

**Phase 3 Exit Criteria:**
- ✓ SaaS MVP live and accepting payments
- ✓ 10-20 paying customers (threat intel, journalism, nonprofit, commercial)
- ✓ $10-20K MRR
- ✓ 100+ active users (mix of free + paid)
- ✓ Marketplace with 5-10 community adapters
- ✓ Strong community (active Discussions, Twitter, newsletter)
- ✓ Team expanded (1 sales person, possibly 1 additional engineer)
- ✓ Sustainable operations (profitability path visible)
---
## CONSOLIDATED TIMELINE

```
PHASE 1: CONSOLIDATION & CLARITY (Weeks 1-8)
├── W1-2: Foundation Fixes (Quant, Naming, Versioning)
├── W2-3: Operator Tools Audit
├── W3-4: Verdict Filing UI
├── W4-6: Persistence Layer Systematization
├── W6-8: Documentation Expansion
└── W8: Quality Gate & Release → v0.6.0

PHASE 2: POSITIONING & COMMERCIAL PATHS (Weeks 9-16)
├── W9: Repo Reorganization & SaaS Planning
├── W9-12: Portfolio Site Build
├── W12-14: SaaS Architecture & Commercial Strategy
└── W14-16: Community Building & Case Studies

PHASE 3: GROWTH & MONETIZATION (Weeks 17-26)
├── W17-24: SaaS MVP Development
├── W24-26: Tutorials, Sales, Analytics, Performance Improvements
└── W26: First revenue milestone ($10-20K MRR)
```
---
## RESOURCE & BUDGET ESTIMATES
### Engineering Time
- **Phase 1:** ~40 engineering days (1 FTE, 8 weeks)
- **Phase 2:** ~35 engineering days (0.5 FTE, 8 weeks) + marketing planning
- **Phase 3:** ~60+ engineering days (1-2 FTE, 10 weeks) + sales operations
- **Total:** ~135+ days (1 FTE over 26 weeks, with peaks in Phase 1 & 3)

### Estimated Costs

| Item | Phase 1 | Phase 2 | Phase 3 | Total |
|------|---------|---------|---------|-------|
| Developer time (internal) | — | — | — | ~$50-80K (assume $150/hr) |
| Domain (spec1.ai) | — | $150 | $150 | $300 |
| Hosting (basic) | — | $200/mo | $200/mo | ~$1600 |
| SaaS hosting (Render/Railway) | — | — | $500-2K/mo | ~$10-20K |
| Stripe fees | — | — | 2.9% + $0.30/txn | ~5% of revenue |
| Analytics/monitoring (Grafana, etc.) | — | — | $100-300/mo | ~$2K |
| Marketing (portfolio site, ads) | — | $2-5K | $5-10K | ~$15K |
| Sales contractor (Phase 3) | — | — | $3-5K/mo | ~$30-50K |
| **Total** | **~$0** | **~$5K** | **~$50K** | **~$95-155K** |

**Note:** Estimates assume using free/cheap tools where possible; scaling costs appear in Phase 3 once revenue is being generated.
---
## SUCCESS METRICS & KPIs
### Phase 1 Success
- [ ] All code tests passing (pytest)
- [ ] User can setup in <30 minutes
- [ ] All operator tools documented and callable
- [ ] Verdict UI functional
- [ ] Zero breaking changes from v0.5 to v0.6

### Phase 2 Success
- [ ] Portfolio site live and indexed by search engines
- [ ] SaaS architecture documented and validated with early users
- [ ] 2-3 public case studies published
- [ ] 50+ GitHub Discussions messages
- [ ] 1000+ Twitter followers
- [ ] 100+ email newsletter subscribers
- [ ] 5-10 active early users providing feedback

### Phase 3 Success
- [ ] SaaS MVP live at spec1.ai
- [ ] 10-20 paying customers
- [ ] $10-20K MRR
- [ ] <5% monthly churn (for SaaS)
- [ ] NPS > 50
- [ ] 100+ active users (mix of free + paid)
- [ ] 5-10 community adapters in marketplace
- [ ] CAC < LTV/3 (unit economics work)
---
## RISK MITIGATION

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Quant module decision delayed | Low | Low | Decide by end of week 1 |
| SaaS infrastructure costs too high | Medium | High | Use serverless; scale pricing |
| No paying customers by Phase 3 | Medium | High | Validate demand with users in Phase 2 |
| Community doesn't adopt core | Medium | Medium | Partner with journalism/civil rights orgs |
| Open-source vs. commercial licensing confusion | Low | Medium | Consult licensing experts; document clearly |
| Team burnout (too fast growth) | Medium | High | Hire contractors/sales person; pace work |
| Breaking changes alienate users | Low | Low | Deprecate slowly; communicate changes |
---
## DECISION POINTS & GATING

| Decision | Due Date | Options | Recommendation |
|----------|----------|---------|-----------------|
| Quant module | End of W1 | Keep / Remove | **Remove** (focused mission) |
| Domain name | End of W9 | .ai / .io / .com / other | **spec1.ai** (emerging AI positioning) |
| SaaS architecture | End of W12 | Single-tenant / Multi-tenant / Hybrid | **Multi-tenant** (more scalable) |
| Licensing | End of W14 | Apache / MIT / AGPL / Proprietary | **AGPL** (protects open-source) |
| Sales model | End of W16 | Direct / Marketplace / Partnership | **All three** (diversified) |
| First customer segment | End of W20 | Journalist / Nonprofit / Threat Intel | **Threat Intel** (fastest to revenue) |
---
## PHASE GATES (Go/No-Go Decisions)
### End of Phase 1 (Week 8)
**Gate:** Technical foundation is solid; ready for external users
- ✓ All tests passing
- ✓ No technical debt blockers
- ✓ Operator tools all documented
- ✓ Verdict UI functional
- ✓ New user can setup in <30 min
- **Decision:** Proceed to Phase 2 (Positioning)

### End of Phase 2 (Week 16)
**Gate:** Market positioning is clear; SaaS architecture validated
- ✓ Portfolio site live
- ✓ 5-10 early users engaged
- ✓ 2-3 case studies published
- ✓ SaaS architecture validated with customers
- ✓ Licensing strategy decided
- **Decision:** Proceed to Phase 3 (Build SaaS) or Pivot (go narrower)

### End of Phase 3 (Week 26)
**Gate:** Product-market fit signals visible; revenue generation started
- ✓ SaaS MVP live and taking payments
- ✓ 10-20 paying customers
- ✓ $10-20K MRR
- ✓ <5% monthly churn
- ✓ Unit economics positive or close to positive
- **Decision:** Scale (hire team, expand features) or Sustain (maintain current product)
---
## DEPENDENCIES & BLOCKERS
**Critical Path:**
1. Quant module decision (blocks everything else) → Day 1-2
2. API versioning (blocks external users) → Week 1-2
3. Verdict UI (makes feedback loop real) → Week 3-4
4. Persistence layer (enables scaling) → Week 4-6
5. Documentation (enables onboarding) → Week 6-8
6. Portfolio site (enables positioning) → Week 9-12
7. SaaS MVP (enables monetization) → Week 17-24

**External Dependencies:**
- Anthropic API stability (for Claude verification)
- RSS feed uptime (for signal harvesting)
- Early users willing to participate in case studies (Phase 2)
- Sales person availability (Phase 3)
---
## QUARTERLY CHECKPOINTS
### Q1 Checkpoint (Week 8 — End of Phase 1)
- [ ] Version 0.6.0 released
- [ ] Zero critical technical debt
- [ ] 10-20 active users (repo stars, GitHub Discussions activity)
- [ ] All Makefile targets working
- [ ] Documentation is comprehensive

### Q2 Checkpoint (Week 16 — End of Phase 2)
- [ ] Portfolio site live with 500+ monthly visitors
- [ ] 2-3 case studies published
- [ ] 50-100 GitHub Discussions messages
- [ ] SaaS architecture documented and validated
- [ ] Licensing and pricing strategy finalized

### Q3 Checkpoint (Week 26 — End of Phase 3)
- [ ] SaaS MVP live and accepting payments
- [ ] 10-20 paying customers acquired
- [ ] $10-20K MRR
- [ ] 100+ active users
- [ ] First revenue milestone achieved
---
## APPENDIX: TOOL TEMPLATES & CHECKLISTS
### Code Review Checklist (Every Phase)
- [ ] All tests passing (`pytest tests/`)
- [ ] No style violations (`flake8 src/ tests/`)
- [ ] No imports from frozen core without approval
- [ ] No `pass` stubs or `pytest.skip`
- [ ] No hardcoded label strings (import from `spec1_labels`)
- [ ] CHANGELOG.md updated with version bump
- [ ] docs/architecture.md reflects changes

### Deployment Checklist (Every Phase)
- [ ] Version bumped in pyproject.toml (MAJOR / MINOR / PATCH)
- [ ] CHANGELOG.md entry written
- [ ] All tests passing
- [ ] Code reviewed by team lead
- [ ] Deployed to GitHub Pages (documentation)
- [ ] Deployed to production API (if applicable)
- [ ] Health check passes
- [ ] Monitoring shows no spike in errors

### Community Engagement Checklist (Phase 2 & 3)
- [ ] GitHub Discussions response time < 24 hours
- [ ] Twitter posts 2-3x per week
- [ ] Newsletter published monthly
- [ ] Case studies published and shared
- [ ] Respond to user issues and PRs
---
## QUESTIONS FOR STAKEHOLDERS
**Before starting Phase 1:**
1. Is the decision to remove the quant module acceptable? (YES / NO)
2. Are you (the founder) available full-time for Phase 1? (YES / NO)
3. Do you want to hire a contractor for Phase 2 marketing? (YES / NO)
4. Do you have domain preferences (spec1.ai vs. spec1intelligence.io)? (PREFERENCE)
5. Is the Phase 3 target of $10-20K MRR realistic for your market? (YES / NO / UNCERTAIN)

**Before starting Phase 2:**
1. Do we have 5+ early users willing to participate in case studies? (YES / NO)
2. Is SaaS hosting on budget? (YES / NEEDS ADJUSTMENT)
3. Can we hire a part-time sales person for Phase 3? (YES / NO / UNDECIDED)
4. Do we have partnership interest from 2+ orgs (journalism, nonprofits, etc.)? (YES / NO)

**Before starting Phase 3:**
1. Is the SaaS architecture validated by paying customers? (YES / NO)
2. Do we have resources for 1-2 FTE engineering + 1 FTE sales? (YES / NO)
3. Are we comfortable with the AGPL licensing strategy? (YES / NO)
4. Do we have a sales process and pipeline? (YES / NO)
---
## CONCLUSION
This roadmap takes SPEC-1 from "impressive portfolio project" to "sustainable product business" over 26 weeks. The path is:

1. **Phase 1:** Fix technical foundation (consolidation)
2. **Phase 2:** Build market positioning (clarity)
3. **Phase 3:** Generate revenue (monetization)

Each phase has clear deliverables, success criteria, and gating decisions. The resource requirements scale from 1 FTE (Phase 1) to 2 FTE + sales (Phase 3), with total estimated cost of $95-155K (including team time).

The highest-leverage changes are:
1. Resolving the quant module (clarity)
2. Building the verdict UI (product)
3. Systematizing persistence (scalability)
4. Separating positioning (marketability)
5. Launching SaaS MVP (monetization)

**Execution discipline is more important than timeline perfection.** Follow the gating decisions; validate assumptions with real users; adjust roadmap based on market feedback. The goal is sustainable product business, not "go big or go home."

---
**Document Version:** 1.0  
**Last Updated:** May 19, 2026  
**Next Review:** Week 8 (end of Phase 1)  
**Contact:** spec1_ops@proton.me
