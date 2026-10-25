# spec1_engine — archived 2026-10-24

Moved here from `src/spec1_engine/` by the 2026-10-24 audit PR. Nothing live
imports it: the daily cycle, API, MCP server, Dockerfile and Makefile all run
`spec1_core`.

Why: it stopped changing on 2026-06-25. Of the 56 files it shared with
`spec1_core`, 46 had drifted, and it lacks the later fixes (per-task model
routing, `<think>` stripping, article text in the verifier, analysis_tier).
The Makefile and `scripts/run_cycle.sh` still called it, so those paths ran
four-month-old code.

What only existed here (unused anywhere live when archived):
- `persistence/postgres.py` (+ its test, `test_persistence.py`, moved here)
- `tools/radar_dashboard.py`, `tools/snapshot_manager.py`, `tools/workspace_sanitizer.py`
- `core/llm.py`, `core/settings.py`, `core/prompts/{brief_*,feed_prompt_gate_*,lead_packet_*}.md`
- `data/` snapshots (Portland zoning/transit)

Not on the import path (`src/` only) and not collected by pytest. To bring a
file back, `git mv` it into `src/spec1_core/` and repoint its imports.

## Tests moved here with it

- `test_persistence.py` — tests `persistence/postgres.py`, which only exists here.
- `test_credibility.py` — tests `analysts/credibility.py` *in this package*,
  whose `match_record()` does token-based author matching ("J. Barnes",
  "By Julian Barnes", multi-author bylines) and rejects "Jonathan Barnes".
  `spec1_core.analysts.credibility` never got it: its partial match accepts
  any author containing the last name plus the first initial anywhere, so
  "Jonathan Barnes" scores as Julian E. Barnes (0.90). Nothing live imports
  `CredibilityAnalyst` today, so no output is affected — port this matcher
  before anything starts using it.
