.PHONY: install test test-fast test-cov lint run mcp cycle triage backfill calibration workspace clean help brief leads psyop research organize

PYTHONPATH := src
PYTHON     := PYTHONPATH=$(PYTHONPATH) python
PYTEST     := PYTHONPATH=$(PYTHONPATH) pytest

help:
	@echo "SPEC-1 Intelligence Engine"
	@echo ""
	@echo "  make install      Install package + dev deps"
	@echo "  make test         Run full test suite"
	@echo "  make lint         Run ruff (same check as CI)"
	@echo "  make run          Start API server (port 8000)"
	@echo "  make mcp          Start MCP server"
	@echo "  make cycle        Run one-shot intelligence cycle (rich path)"
	@echo "  make triage       Harvest + 4 gates + rules only, no model (what Actions runs)"
	@echo "  make backfill     Backfill briefs for historical run_ids"
	@echo "  make calibration  Generate calibration proposal report"
	@echo "  make brief        Generate a daily brief for the latest run_id (operator tool)"
	@echo "  make leads        Derive Lead objects from intelligence records (operator tool)"
	@echo "  make psyop        Score every intelligence record for psyop patterns (operator tool)"
	@echo "  make research     Run analyst-defined topic research dossier expansion"
	@echo "  make workspace    Open workspace CLI"
	@echo "  make clean        Remove __pycache__ and .pytest_cache"
	@echo ""
	@echo "  Pass tool arguments with ARGS, e.g. make brief ARGS='--run-id run-abc'"

install:
	pip install -e ".[dev]"

test:
	$(PYTEST) tests/ -v --tb=short

test-fast:
	$(PYTEST) tests/ -x --tb=short -q

test-cov:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing

lint:
	ruff check src/ tests/

run:
	$(PYTHON) -m spec1_api.main

mcp:
	$(PYTHON) mcp_server.py

cycle:
	$(PYTHON) -m spec1_core.app.cycle $(ARGS)

triage:
	$(PYTHON) -m spec1_core.app.cycle --triage-only $(ARGS)

backfill:
	$(PYTHON) -m spec1_core.tools.historical_briefs $(ARGS)

calibration:
	$(PYTHON) -m spec1_core.tools.calibration_propose \
		--intel data/spec1_intelligence.jsonl \
		--verdicts data/verdicts.jsonl \
		--out-dir generated/ $(ARGS)

brief:
	$(PYTHON) -m spec1_core.tools.generate_brief $(ARGS)

leads:
	$(PYTHON) -m spec1_core.tools.generate_leads $(ARGS)

psyop:
	$(PYTHON) -m spec1_core.tools.run_psyop $(ARGS)

research:
	$(PYTHON) -m spec1_core.tools.run_research $(ARGS)

workspace:
	$(PYTHON) -m spec1_core.workspace.cli $(ARGS)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	echo "Cleaned."

organize:
	@echo "Starting repository organization..."
	@mkdir -p docs/investor_outreach docs/launch_prep data
	@-[ -f INVESTOR_PITCH.md ] && git mv INVESTOR_PITCH.md docs/investor_outreach/
	@-[ -f OUTREACH_TEMPLATES.md ] && git mv OUTREACH_TEMPLATES.md docs/investor_outreach/
	@-[ -f LAUNCH_PLAN.md ] && git mv LAUNCH_PLAN.md docs/launch_prep/
	@-[ -f LAUNCH_READINESS.md ] && git mv LAUNCH_READINESS.md docs/launch_prep/
	@-[ -f spec1_intelligence.jsonl ] && git mv spec1_intelligence.jsonl data/
	@-[ -f verdicts.jsonl ] && git mv verdicts.jsonl data/
	@echo "Organization complete! Run 'git status' to review changes."
