"""Test configuration — mock network LLM calls to prevent hangs in CI."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

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
    # Every default store/cache/log path resolves against spec1_home() at call time,
    # so this one variable keeps defaults out of the real checkout. Tests that need a
    # specific home set SPEC1_HOME themselves, after this fixture.
    # mcp_server.main() chdirs into SPEC1_HOME, so the dir must exist.
    (out / "home").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SPEC1_HOME", str(out / "home"))
    monkeypatch.setenv("SPEC1_DB_PATH", str(out / "spec1.db"))
    monkeypatch.setenv("SPEC1_LLM_LOG_PATH", str(out / "logs" / "llm_fallback.jsonl"))

    for pkg in ("spec1_core",):
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


@pytest.fixture(autouse=True, scope="function")
def block_real_llm_backends(request, monkeypatch):
    """Keep tests off the real Claude API and a real Ollama.

    generator.py runs load_dotenv(), so a dev box's .env key leaks into every
    test, and an unmocked verifier would call Claude and then wait on
    ollama_manager.spawn(). generate_brief() also tries LocalTier3Client.chat()
    first. Drop the key and make both local paths fail fast, so the cycle falls
    to Tier 3. Tests that want a backend set the key or patch it themselves
    (their patch is applied after this one). The client's own test files are
    left alone.
    """
    if request.fspath.basename in ("test_fallback_client.py", "test_llm_task_routing.py"):
        yield
        return
    from spec1_core.llm import ollama_manager
    from spec1_core.llm.fallback_client import LocalTier3Client

    def _offline(self, *args, **kwargs):
        raise ConnectionError("Ollama offline (test)")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_AUTO_SPAWN", "false")
    monkeypatch.setattr(ollama_manager, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(LocalTier3Client, "chat", _offline)
    yield


# ── Session guard: the suite must not write into the checkout ─────────────────
#
# Watches the places a stray relative default lands (repo root files and the
# runtime data/output dirs). Any file created or modified there during the run
# fails the session, naming the file. Source dirs are not watched: pytest writes
# __pycache__ there legitimately.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_WATCHED_DIRS = ("data", "briefs", "generated", "logs", "cache", "research", "analyst_loop", "memory")
_IGNORED_NAMES = {".coverage", ".pytest_cache", "__pycache__", ".ruff_cache", ".mypy_cache"}
# Test-tool output the runner itself writes at the root, by design: CI runs
# `pytest --cov --cov-report=xml`, and coverage's parallel mode writes `.coverage.<host>.<pid>`.
_TOOL_OUTPUT = {"coverage.xml", "coverage.json", "junit.xml"}


def _is_tool_output(name: str) -> bool:
    return name in _TOOL_OUTPUT or name.startswith(".coverage")


def _checkout_state() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for entry in _REPO_ROOT.iterdir():
        if entry.is_file() and entry.name not in _IGNORED_NAMES and not _is_tool_output(entry.name):
            st = entry.stat()
            state[entry.name] = (st.st_mtime_ns, st.st_size)
    for name in _WATCHED_DIRS:
        base = _REPO_ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not (_IGNORED_NAMES & set(path.parts)):
                st = path.stat()
                state[str(path.relative_to(_REPO_ROOT))] = (st.st_mtime_ns, st.st_size)
    return state


def pytest_sessionstart(session):
    session.config._spec1_checkout_state = _checkout_state()


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "_spec1_checkout_state", None)
    if before is None:
        return
    after = _checkout_state()
    touched = sorted(k for k, v in after.items() if before.get(k) != v)
    if touched:
        listing = "\n  ".join(touched[:20])
        session.config.get_terminal_writer().line(
            f"\nTests wrote into the checkout ({len(touched)} files):\n  {listing}", red=True
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
