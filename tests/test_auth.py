# @domain:   spec-1
# @module:   test_auth
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for spec1_api.auth — API key middleware."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_key():
    """Return a TestClient with SPEC1_API_KEY set."""
    with patch.dict(os.environ, {"SPEC1_API_KEY": "test-secret-key", "SPEC1_ENVIRONMENT": "production"}, clear=False):
        with patch("spec1_api.scheduler.start_scheduler"), \
             patch("spec1_api.scheduler.stop_scheduler"), \
             patch("spec1_api.scheduler.maybe_run_on_start"):
            from spec1_api.main import create_app
            _app = create_app()
            with TestClient(_app, raise_server_exceptions=False) as c:
                yield c


@pytest.fixture
def app_no_key():
    """Return a TestClient with no SPEC1_API_KEY (open access)."""
    with patch.dict(os.environ, {}, clear=False):
        env = dict(os.environ)
        env.pop("SPEC1_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("spec1_api.scheduler.start_scheduler"), \
                 patch("spec1_api.scheduler.stop_scheduler"), \
                 patch("spec1_api.scheduler.maybe_run_on_start"):
                from spec1_api.main import create_app
                _app = create_app()
                with TestClient(_app, raise_server_exceptions=False) as c:
                    yield c


# ── Public paths always accessible ────────────────────────────────────────────

class TestPublicPaths:
    def test_health_no_key_required(self, app_with_key):
        r = app_with_key.get("/health")
        assert r.status_code == 200

    def test_metrics_no_key_required(self, app_with_key):
        r = app_with_key.get("/metrics")
        assert r.status_code == 200

    def test_docs_no_key_required(self, app_with_key):
        r = app_with_key.get("/docs")
        assert r.status_code == 200

    def test_openapi_json_no_key_required(self, app_with_key):
        r = app_with_key.get("/openapi.json")
        assert r.status_code == 200


# ── Protected paths require key ────────────────────────────────────────────────

class TestProtectedPaths:
    def test_intel_without_key_returns_403(self, app_with_key):
        r = app_with_key.get("/api/v1/intel")
        assert r.status_code == 403

    def test_intel_with_wrong_key_returns_403(self, app_with_key):
        r = app_with_key.get("/api/v1/intel", headers={"X-API-Key": "wrong-key"})
        assert r.status_code == 403

    def test_intel_with_correct_header_key_passes(self, app_with_key):
        r = app_with_key.get("/api/v1/intel", headers={"X-API-Key": "test-secret-key"})
        assert r.status_code == 200

    def test_intel_with_correct_query_param_passes(self, app_with_key):
        r = app_with_key.get("/api/v1/intel?api_key=test-secret-key")
        assert r.status_code == 200

    def test_403_response_has_detail(self, app_with_key):
        r = app_with_key.get("/api/v1/intel")
        assert "detail" in r.json()

    def test_403_preserves_cors_headers(self):
        with patch.dict(
            os.environ,
            {
                "SPEC1_API_KEY": "test-secret-key",
                "SPEC1_ENVIRONMENT": "production",
                "SPEC1_CORS_ORIGINS": "https://example.test",
            },
            clear=False,
        ):
            with patch("spec1_api.scheduler.start_scheduler"), \
                 patch("spec1_api.scheduler.stop_scheduler"), \
                 patch("spec1_api.scheduler.maybe_run_on_start"):
                from spec1_api.main import create_app
                app = create_app()
                with TestClient(app, raise_server_exceptions=False) as client:
                    r = client.get(
                        "/api/v1/intel",
                        headers={"Origin": "https://example.test"},
                    )
        assert r.status_code == 403
        assert r.headers.get("access-control-allow-origin") == "https://example.test"


# ── No key configured → open access ───────────────────────────────────────────

class TestNoKeyConfigured:
    def test_intel_accessible_without_key(self, app_no_key):
        r = app_no_key.get("/api/v1/intel")
        assert r.status_code == 200

    def test_signals_accessible_without_key(self, app_no_key):
        r = app_no_key.get("/api/v1/signals")
        assert r.status_code == 200


# ── Unit tests for middleware logic ───────────────────────────────────────────

class TestApiKeyMiddlewareLogic:
    def test_get_configured_key_returns_none_when_unset(self):
        from spec1_api.auth import _get_configured_key
        with patch.dict(os.environ, {}, clear=True):
            assert _get_configured_key() is None

    def test_get_configured_key_returns_value_when_set(self):
        from spec1_api.auth import _get_configured_key
        with patch.dict(os.environ, {"SPEC1_API_KEY": "mykey"}, clear=False):
            assert _get_configured_key() == "mykey"

    def test_empty_string_key_returns_none(self):
        from spec1_api.auth import _get_configured_key
        with patch.dict(os.environ, {"SPEC1_API_KEY": "   "}, clear=False):
            assert _get_configured_key() is None
