.PHONY: install test test-fast test-cov lint run mcp cycle backfill calibration workspace clean help brief leads psyop research

PYTHONPATH := src
PYTHON     := PYTHONPATH=$(PYTHONPATH) python
PYTEST     := PYTHONPATH=$(PYTHONPATH) pytest

help:
	@echo "SPEC-1 Intelligence Engine"
	@echo ""
	@echo "  make install      Install package + dev deps"
	@echo "  make test         Run full test suite"
	@echo "  make lint         Run flake8"
	@echo "  make run          Start API server (port 8000)"
	@echo "  make mcp          Start MCP server"
	@echo "  make cycle        Run one-shot intelligence cycle (rich path)"
	@echo "  make backfill     Backfill briefs for historical run_ids"
	@echo "  make calibration  Generate calibration proposal report"
	@echo "  make brief        Generate a daily brief for the latest run_id (operator tool)"
	@echo "  make leads        Derive Lead objects from intelligence records (operator tool)"
	@echo "  make psyop        Score every intelligence record for psyop patterns (operator tool)"
	@echo "  make research     Run analyst-defined topic research dossier expansion"
	@echo "  make workspace    Open workspace CLI"
	@echo "  make clean        Remove __pycache__ and .pytest_cache"

install:
	pip install -e ".[dev]"

test:
	$(PYTEST) tests/ -v --tb=short

test-fast:
	$(PYTEST) tests/ -x --tb=short -q

test-cov:
	$(PYTEST) tests/ --cov=src --cov-report=term-missing

lint:
	flake8 src/ tests/ --max-line-length=120

run:
	$(PYTHON) -m spec1_api.main

mcp:
	$(PYTHON) mcp_server.py

cycle:
	$(PYTHON) -m spec1_core.app.cycle

backfill:
	$(PYTHON) -m spec1_engine.tools.historical_briefs
calibration: $(PYTHON) -m spec1_engine.tools.calibration_propose \
	--intel data/spec1_intelligence.jsonl \
	--verdicts data/verdicts.jsonl \
	--out-dir generated/

brief: $(PYTHON) -m spec1_engine.tools.generate_brief
leads: $(PYTHON) -m spec1_engine.tools.generate_leads
psyop: $(PYTHON) -m spec1_engine.tools.run_psyop
research: $(PYTHON) -m spec1_core.tools.run_research
workspace: $(PYTHON) -m spec1_engine.workspace

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
