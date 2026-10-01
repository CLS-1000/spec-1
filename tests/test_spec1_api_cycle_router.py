"""Tests for spec1_api.routers.cycle."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _build_client():
    with patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"), \
         patch("spec1_api.scheduler.maybe_run_on_start"):
        from spec1_api.main import create_app
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)


def test_cycle_run_rejects_non_positive_max_signals():
    with _build_client() as client:
        r = client.post("/api/v1/cycle/run", json={"max_signals": 0})
    assert r.status_code == 422


def test_cycle_run_returns_500_on_engine_exception():
    with patch("spec1_api.routers.cycle._execute_cycle", side_effect=RuntimeError("boom")):
        with _build_client() as client:
            r = client.post("/api/v1/cycle/run", json={})
    assert r.status_code == 500
    assert "Cycle execution failed" in r.json()["detail"]


def test_cycle_run_records_metrics_and_fires_webhook():
    stats = {
        "run_id": "run-abc",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:01:00+00:00",
        "signals_harvested": 3,
        "signals_parsed": 3,
        "opportunities_found": 2,
        "investigations_generated": 2,
        "outcomes_verified": 2,
        "records_stored": 1,
        "errors": [],
    }
    with patch("spec1_api.routers.cycle._execute_cycle", return_value=stats), \
         patch("spec1_api.routers.cycle._metrics.record_cycle") as record_cycle, \
         patch("spec1_api.routers.cycle._webhooks.fire_cycle_completed") as fire_webhook:
        with _build_client() as client:
            r = client.post("/api/v1/cycle/run", json={})
    assert r.status_code == 200
    record_cycle.assert_called_once_with(stats)
    fire_webhook.assert_called_once_with(stats)
