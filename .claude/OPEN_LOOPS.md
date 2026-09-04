# Open loops — spec-1

Source of truth for unresolved threads in this repo. One line per loop.
Injected into every Claude Code session by `.claude/hooks/session-brief.sh`.

Rules: write the *question*, not the topic. Never delete a loop — move it to
Closed. Keep Open under 40 lines.

## Open

- [2026-08-06] pdx-1i: does `graph.py` already build nodes from another source? If so `load_graph()` must be wired in as its input, not run as a second parallel registry. UNVERIFIED.
- [2026-08-06] pdx-1i: Option B (person nodes carrying aliases + provenance, un-freezing `Node`) is deferred, not closed. It is an editorial decision about what Notitia Civica publishes about named individuals, not a schema decision.
- [2026-08-26] gates: `DOMAIN_WEIGHTS` and `ALPHA_OVERRIDE` in `threat_index_config.py` are uncalibrated placeholders. They need a backfill replay before the threat index means anything.
- [2026-08-26] pipeline: `scored_signals`, `score_rejects`, and `parsed_signals` are empty for every run_id — the intermediate stages are memory-only and only the terminal store dual-writes. "Why was this signal dropped" is unanswerable after the process exits. Decide: write them, or drop the tables and stop implying they hold data.
- [2026-08-26] analyst loop: a verdict was filed `confirmed` with `published=True` on top of two audits that returned 0 claims confirmed and confidence 0.00. Nothing in the chain blocks publication on a failed audit. Is that a gate that should exist?
- [2026-08-26] analyst loop: `cls_analyst_loop` writes to its own JSONL at `./analyst_loop/`, not to `spec1.db`. `analyst_cases` in SQLite is empty. Two stores or one?
- [2026-08-26] deploy: no `make migrate` target exists and the schema-init mechanism is still unconfirmed. Find it or write it before any GCP bring-up.
- [2026-08-26] deploy: WSL2 means no systemd and no always-on uptime. The GCP runbook assumes a systemd timer for `make cycle`. Reconcile before following it.
- [2026-07-26] hygiene: `backfill_jsonl_to_db.py` line 6 has a TODO referencing the stale `spec1_engine` namespace.
- [2026-08-04] labeldrift: `ominous-22/labeldrift` is confirmed empty. The package exists locally with 18 tests and PyPI Trusted Publishing configured but was never actually pushed.

## Closed

- [2026-08-26] feedparser 6.0.10 broke on Python 3.13 (`cgi` removed from stdlib). Closed: pin changed to `>=6.0.11`, 6.0.14 installed, first live `make cycle` succeeded.
- [2026-08-06] pdx-1i seed migration structure-vs-persons. Closed: Option A chosen — structure only, names deliberately discarded, 57 seats preserved via `Jurisdiction.seats` tuple.
