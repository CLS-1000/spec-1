"""Test configuration — mock network LLM calls to prevent hangs in CI."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True, scope="function")
def isolate_output_paths(tmp_path, monkeypatch):
    """Send every file the cycle writes into a per-test temp dir.

    Without this, tests that call run_cycle write into the real repo:
    briefs/ (dated brief, *_latest.md, brief_index.jsonl), generated/briefs/
    (a new spec1_issue_NNN PDF per run, advancing the real issue counter),
    data/psyop_signals.jsonl, logs/llm_fallback.jsonl and spec1.db. Those
    are gitignored, so they never show in `git status`; the June 17 batch of
    ~108 "# Test Brief" issue PDFs came from exactly this.

    Tests that set a path themselves still win: their monkeypatch or explicit
    argument is applied after this fixture.
    """
    out = tmp_path / "_spec1_outputs"
    monkeypatch.setenv("SPEC1_DB_PATH", str(out / "spec1.db"))
    monkeypatch.setenv("SPEC1_LLM_LOG_PATH", str(out / "logs" / "llm_fallback.jsonl"))

    for pkg in ("spec1_core", "spec1_engine"):
        # Some tests wipe os.environ, so also move the module default, not just the env var.
        try:
            llm = importlib.import_module(f"{pkg}.llm.fallback_client")
            monkeypatch.setattr(llm, "_DEFAULT_LOG_PATH", out / "logs" / "llm_fallback.jsonl")
        except (ImportError, AttributeError):
            pass
        try:
            writer = importlib.import_module(f"{pkg}.briefing.writer")
            monkeypatch.setattr(writer, "BRIEFS_DIR", out / "briefs")
        except ImportError:
            pass
        try:
            psyop = importlib.import_module(f"{pkg}.psyop.scorer")
            if hasattr(psyop, "_DEFAULT_STORE_PATH"):
                monkeypatch.setattr(psyop, "_DEFAULT_STORE_PATH", out / "data" / "psyop_signals.jsonl")
        except ImportError:
            pass
        try:
            pubgen = importlib.import_module(f"{pkg}.tools.publication_generator")
        except ImportError:
            continue
        original = pubgen.generate_publication

        def _isolated(*args, _orig=original, **kwargs):
            # output_dir is the 4th positional parameter; only fill it if the caller didn't.
            if len(args) < 4 and "output_dir" not in kwargs:
                kwargs["output_dir"] = str(out / "generated" / "briefs")
            return _orig(*args, **kwargs)

        monkeypatch.setattr(pubgen, "generate_publication", _isolated)
    yield


@pytest.fixture(autouse=True, scope="function")
def mock_network_llm_calls(request):
    """Mock network LLM calls only for cycle/briefing tests.

    Skips Tier 1 (Claude API) via SPEC1_DEV_MODE for tests that call
    run_cycle or briefing generator, since CI has no API credits.

    Fallback client tests are excluded so they can test Tier 1 behavior.
    """
    # Only apply mocking for specific test files
    test_module = request.fspath.basename
    if test_module in ("test_cycle.py", "test_cycle_dedup.py", "test_api.py", "test_briefing.py"):
        os.environ["SPEC1_DEV_MODE"] = "true"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="# Test Brief")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("spec1_core.llm.ollama_manager.chat", side_effect=Exception("Ollama offline")), \
             patch("anthropic.Anthropic", return_value=mock_client):
            yield
            os.environ.pop("SPEC1_DEV_MODE", None)
    else:
        yield
