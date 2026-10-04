# @domain:   machine
# @module:   test_spec1_api_scheduler
# @loc:      gh_main
# @status:   testing
# @depends:  spec1_core, cls_db

"""Tests for spec1_api.scheduler — kill-switch and run-on-start behaviour."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from spec1_api import scheduler as sched


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Ensure the module-level _scheduler is None before/after each test."""
    sched._scheduler = None
    yield
    if sched._scheduler is not None:
        try:
            sched._scheduler.shutdown(wait=False)
        except Exception:
            pass
        sched._scheduler = None


@pytest.fixture
def kill_file_in_tmp(tmp_path, monkeypatch):
    """Point KILL_FILE at a tmp path so tests don't touch repo root."""
    kf = tmp_path / ".cls_kill"
    monkeypatch.setattr(sched, "KILL_FILE", kf)
    return kf


def test_run_cycle_job_skips_when_kill_file_present(kill_file_in_tmp, caplog):
    kill_file_in_tmp.write_text("")
    with patch("spec1_core.app.cycle.run_cycle") as mock_run:
        sched._run_cycle_job()
        mock_run.assert_not_called()
    assert "Kill file present" in caplog.text


def test_run_cycle_job_runs_engine_when_no_kill_file(kill_file_in_tmp):
    assert not kill_file_in_tmp.exists()
    with patch("spec1_api.scheduler.new_run_id", return_value="run-scheduled-test"), \
         patch("spec1_core.app.cycle.run_cycle") as mock_run:
        mock_run.return_value = {"records_stored": 3, "errors": []}
        sched._run_cycle_job()
        mock_run.assert_called_once_with(
            store_path=sched.Path("spec1_intelligence.jsonl"),
            run_id="run-scheduled-test",
            environment="production",
            verbose=False,
        )


def test_run_cycle_job_logs_correlation_and_traceback_on_failure(kill_file_in_tmp, caplog):
    with patch("spec1_api.scheduler.new_run_id", return_value="run-scheduled-error"), \
         patch("spec1_core.app.cycle.run_cycle", side_effect=RuntimeError("cycle failed")):
        sched._run_cycle_job()

    assert "run_id=run-scheduled-error" in caplog.text
    assert "stage=cycle" in caplog.text
    assert "duration_seconds=" in caplog.text
    assert any(record.exc_info for record in caplog.records)


def test_stop_scheduler_logs_shutdown_failures(caplog):
    mock_scheduler = MagicMock()
    mock_scheduler.shutdown.side_effect = RuntimeError("shutdown failed")
    sched._scheduler = mock_scheduler

    sched.stop_scheduler()

    assert sched._scheduler is None
    assert "Scheduler shutdown failed" in caplog.text
    assert "duration_seconds=" in caplog.text
    assert any(record.exc_info for record in caplog.records)


def test_run_cycle_job_swallows_engine_errors(kill_file_in_tmp, caplog):
    with patch("spec1_core.app.cycle.run_cycle") as mock_run:
        mock_run.side_effect = RuntimeError("boom")
        sched._run_cycle_job()  # must not raise
    assert "Scheduled cycle failed" in caplog.text


def test_maybe_run_on_start_disabled_by_default(kill_file_in_tmp, monkeypatch):
    monkeypatch.delenv("SPEC1_RUN_ON_START", raising=False)
    with patch("spec1_api.scheduler.threading.Thread") as mock_thread:
        sched.maybe_run_on_start()
        mock_thread.assert_not_called()


def test_maybe_run_on_start_fires_thread_when_enabled(kill_file_in_tmp, monkeypatch):
    monkeypatch.setenv("SPEC1_RUN_ON_START", "true")
    with patch("spec1_api.scheduler.threading.Thread") as mock_thread:
        sched.maybe_run_on_start()
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args.kwargs
        assert kwargs["target"] is sched._run_cycle_job
        assert kwargs["daemon"] is True
        mock_thread.return_value.start.assert_called_once()


def test_maybe_run_on_start_respects_kill_file(kill_file_in_tmp, monkeypatch, caplog):
    monkeypatch.setenv("SPEC1_RUN_ON_START", "true")
    kill_file_in_tmp.write_text("")
    with patch("spec1_api.scheduler.threading.Thread") as mock_thread:
        sched.maybe_run_on_start()
        mock_thread.assert_not_called()
    assert "Kill file present" in caplog.text


def test_maybe_run_on_start_case_insensitive_truthy(kill_file_in_tmp, monkeypatch):
    for val in ("TRUE", "True", "true"):
        monkeypatch.setenv("SPEC1_RUN_ON_START", val)
        with patch("spec1_api.scheduler.threading.Thread") as mock_thread:
            sched.maybe_run_on_start()
            mock_thread.assert_called_once()


def test_maybe_run_on_start_falsy_strings_disabled(kill_file_in_tmp, monkeypatch):
    for val in ("false", "0", "no", ""):
        monkeypatch.setenv("SPEC1_RUN_ON_START", val)
        with patch("spec1_api.scheduler.threading.Thread") as mock_thread:
            sched.maybe_run_on_start()
            mock_thread.assert_not_called()


def test_get_scheduler_returns_none_when_unstarted():
    assert sched.get_scheduler() is None


def test_start_scheduler_idempotent(monkeypatch):
    """Calling start_scheduler twice does not create a second scheduler."""
    mock_cls = MagicMock()

    mock_bg_module = MagicMock()
    mock_bg_module.BackgroundScheduler = mock_cls

    # Inject mock so the lazy `from apscheduler.schedulers.background import ...`
    # inside start_scheduler() succeeds without requiring tzlocal to be installed.
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", mock_bg_module)

    sched.start_scheduler()
    # _scheduler is now set; a second call must return early without instantiating again
    scheduler_after_first_call = sched._scheduler
    assert scheduler_after_first_call is not None
    sched.start_scheduler()
    assert sched._scheduler is scheduler_after_first_call, "start_scheduler must be idempotent"
    assert mock_cls.call_count == 1, "BackgroundScheduler should be instantiated exactly once"
