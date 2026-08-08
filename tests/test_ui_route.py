# @domain:   spec-1
# @module:   test_ui_route
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the SPEC-1 UI root route + Portland Political Web env-gating."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _build_client(political_web_enabled: bool):
    """Build a TestClient with scheduler stubbed and political-web env set."""
    env = (
        {"SPEC1_POLITICAL_WEB": "true", "SPEC1_POLITICAL_WEB_ENABLED": ""}
        if political_web_enabled
        else {"SPEC1_POLITICAL_WEB": "", "SPEC1_POLITICAL_WEB_ENABLED": ""}
    )
    with patch.dict("os.environ", env, clear=False), \
         patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"):
        import spec1_api.main as main_mod
        importlib.reload(main_mod)  # rebuild app with current env
        with TestClient(main_mod.app) as c:
            yield c


@pytest.fixture(scope="module")
def client():
    """Default client — political web DISABLED (the canonical config)."""
    yield from _build_client(political_web_enabled=False)


@pytest.fixture(scope="module")
def client_with_political_web():
    """Client with SPEC1_POLITICAL_WEB_ENABLED=true."""
    yield from _build_client(political_web_enabled=True)


def test_root_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_root_contains_spec1_title(client):
    r = client.get("/")
    assert "SPEC-1 Intelligence Engine" in r.text


def test_root_contains_layout_div(client):
    r = client.get("/")
    assert 'class="layout"' in r.text


# ─── Default: political web DISABLED ──────────────────────────────────────────

def test_portland_web_404_when_disabled(client):
    r = client.get("/portland-web")
    assert r.status_code == 404


def test_nodes_router_404_when_disabled(client):
    # nodes.router is mounted at /nodes — should not exist by default
    r = client.get("/nodes/some-id")
    assert r.status_code == 404


# ─── With SPEC1_POLITICAL_WEB_ENABLED=true ────────────────────────────────────

def test_portland_web_returns_html_when_enabled(client_with_political_web):
    r = client_with_political_web.get("/portland-web")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_portland_web_contains_title_when_enabled(client_with_political_web):
    r = client_with_political_web.get("/portland-web")
    assert "Portland Political Web" in r.text


def test_portland_web_contains_d3_script_when_enabled(client_with_political_web):
    r = client_with_political_web.get("/portland-web")
    assert "d3" in r.text


def test_portland_web_enabled_via_legacy_env_alias():
    with patch.dict("os.environ", {"SPEC1_POLITICAL_WEB_ENABLED": "true", "SPEC1_POLITICAL_WEB": ""}, clear=False), \
         patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"):
        import spec1_api.main as main_mod
        importlib.reload(main_mod)
        with TestClient(main_mod.app) as c:
            r = c.get("/portland-web")
    assert r.status_code == 200


# ─── Political intel viewer (always available) ────────────────────────────────

def test_political_intel_viewer_returns_html(client):
    r = client.get("/spec1_political_web.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_political_intel_viewer_contains_title(client):
    r = client.get("/spec1_political_web.html")
    assert "SPEC-1 Political Intelligence" in r.text


def test_political_intel_data_returns_json(client, tmp_path, monkeypatch):
    export = tmp_path / "spec1_intelligence_export.json"
    export.write_text('[]')
    monkeypatch.setenv("SPEC1_STORE_PATH", str(tmp_path / "spec1_intelligence.jsonl"))
    # Re-import so the route picks up the patched env var
    import importlib
    import spec1_api.main as main_mod
    importlib.reload(main_mod)
    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        r = c.get("/spec1_intelligence_export.json")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]


# ── Verdict filing UI ─────────────────────────────────────────────────────────

def test_verdicts_ui_returns_html(client):
    r = client.get("/verdicts/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_verdicts_ui_contains_form(client):
    r = client.get("/verdicts/")
    assert "verdict-form" in r.text


def test_verdicts_ui_references_api_v1(client):
    r = client.get("/verdicts/")
    assert "/api/v1/verdicts" in r.text
