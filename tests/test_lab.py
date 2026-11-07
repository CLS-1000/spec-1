# @domain:   spec-1
# @module:   test_lab
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for the chatbot lab (/lab, POST /api/v1/lab/ask) and the /switchboard pages."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    resp.raise_for_status.return_value = None
    return resp


def _client(env: dict):
    with patch.dict("os.environ", env, clear=False), \
         patch("spec1_api.scheduler.start_scheduler"), \
         patch("spec1_api.scheduler.stop_scheduler"):
        import spec1_api.main as main_mod
        importlib.reload(main_mod)
        with TestClient(main_mod.app) as c:
            yield c


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("SPEC1_LLM_ROUTE_ASK_MODEL", raising=False)
    monkeypatch.setenv("SPEC1_LOCAL_BACKEND", "openai")
    monkeypatch.setenv("SPEC1_LOCAL_MODEL", "qwen3:8b")
    monkeypatch.setenv("SPEC1_LLM_LOG_PATH", str(tmp_path / "llm.jsonl"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-be-used")
    yield from _client({"SPEC1_API_KEY": ""})


@pytest.fixture()
def keyed_client():
    yield from _client({"SPEC1_API_KEY": "s3cret"})


def test_lab_page_served(client):
    r = client.get("/lab")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/api/v1/lab/ask" in r.text


def test_ask_returns_local_model_reply(client):
    with patch("requests.post", return_value=_openai_response("gatepost rejects bad rows")) as post, \
         patch("anthropic.Anthropic") as claude:
        r = client.post("/api/v1/lab/ask", json={"prompt": "What is gatepost?", "system": "Be brief."})

    claude.assert_not_called()
    assert r.status_code == 200
    assert r.json() == {
        "text": "gatepost rejects bad rows",
        "tier": "local",
        "model": "qwen3:8b",
        "route": ["local", "mock"],
    }
    assert post.call_args.kwargs["json"]["messages"][0] == {"role": "system", "content": "Be brief."}


def test_ask_503_when_local_model_down(client):
    with patch("requests.post", side_effect=ConnectionError("down")), \
         patch("anthropic.Anthropic") as claude:
        r = client.post("/api/v1/lab/ask", json={"prompt": "What is gatepost?"})
    claude.assert_not_called()
    assert r.status_code == 503
    assert r.json()["detail"] == "local model unavailable"


def test_ask_rejects_empty_prompt(client):
    assert client.post("/api/v1/lab/ask", json={"prompt": ""}).status_code == 422


def test_switchboard_pages_served(client):
    redirect = client.get("/switchboard", follow_redirects=False)
    assert redirect.status_code in (301, 302, 307, 308)
    assert redirect.headers["location"] == "/switchboard/"

    index = client.get("/switchboard/")
    assert index.status_code == 200
    assert "<title>SWITCHBOARD" in index.text

    gallery = client.get("/switchboard/gallery.html")
    assert gallery.status_code == 200
    logo = client.get("/switchboard/brand/switchboard.html")
    assert logo.status_code == 200
    assert "sb-mark" in logo.text
    assert client.get("/switchboard/brand/brand.css").status_code == 200


def test_key_guards_ask_but_not_pages(keyed_client):
    assert keyed_client.get("/lab").status_code == 200
    assert keyed_client.get("/switchboard/").status_code == 200
    assert keyed_client.get("/switchboard/brand/accent.js").status_code == 200
    assert keyed_client.post("/api/v1/lab/ask", json={"prompt": "hi"}).status_code == 403
