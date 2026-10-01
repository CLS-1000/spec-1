# @domain:   spec-1
# @module:   test_webhooks
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for spec1_api.webhooks — cycle-event delivery."""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch



def _make_stats(run_id="run-001", signals=10, records=5, errors=None):
    return {
        "run_id": run_id,
        "started_at": "2024-01-15T06:00:00+00:00",
        "finished_at": "2024-01-15T06:02:30+00:00",
        "signals_harvested": signals,
        "records_stored": records,
        "errors": errors or [],
    }


# ── fire_cycle_completed — no URLs configured ─────────────────────────────────

class TestFireCycleNoUrls:
    def test_no_urls_does_not_call_httpx(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": ""}, clear=False):
            with patch("spec1_api.webhooks._deliver_one") as mock_deliver:
                webhooks.fire_cycle_completed(_make_stats())
                time.sleep(0.05)
                mock_deliver.assert_not_called()


# ── fire_cycle_completed — URLs configured ────────────────────────────────────

def _wait_all_threads(timeout: float = 2.0) -> None:
    """Wait for all non-main daemon threads to complete (up to timeout)."""
    deadline = time.time() + timeout
    for t in threading.enumerate():
        if t is threading.main_thread() or not t.daemon:
            continue
        remaining = deadline - time.time()
        if remaining > 0:
            t.join(timeout=remaining)


class TestFireCycleWithUrls:
    def test_spawns_thread_per_url(self):
        from spec1_api import webhooks

        done = threading.Event()
        delivered: list[str] = []

        def fake_deliver(url, payload, secret, timeout):
            delivered.append(url)
            if len(delivered) == 2:
                done.set()

        urls = "https://hook1.example.com,https://hook2.example.com"
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": urls, "SPEC1_WEBHOOK_SECRET": ""}, clear=False):
            with patch("spec1_api.webhooks._deliver_one", side_effect=fake_deliver):
                webhooks.fire_cycle_completed(_make_stats())
                done.wait(timeout=2.0)

        assert set(delivered) == {"https://hook1.example.com", "https://hook2.example.com"}

    def test_payload_contains_expected_keys(self):
        from spec1_api import webhooks

        done = threading.Event()
        payloads: list[dict] = []

        def capture_deliver(url, payload, secret, timeout):
            payloads.append(payload)
            done.set()

        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "https://hook.example.com", "SPEC1_WEBHOOK_SECRET": ""}, clear=False):
            with patch("spec1_api.webhooks._deliver_one", side_effect=capture_deliver):
                webhooks.fire_cycle_completed(_make_stats(run_id="run-xyz"))
                done.wait(timeout=2.0)

        assert len(payloads) == 1
        p = payloads[0]
        assert p["event"] == "cycle.completed"
        assert p["run_id"] == "run-xyz"
        assert "signals_harvested" in p
        assert "records_stored" in p
        assert "success" in p
        assert "sent_at" in p

    def test_success_true_when_no_errors(self):
        from spec1_api import webhooks

        done = threading.Event()
        payloads: list[dict] = []

        def capture(url, payload, secret, timeout):
            payloads.append(payload)
            done.set()

        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "https://h.example.com", "SPEC1_WEBHOOK_SECRET": ""}, clear=False):
            with patch("spec1_api.webhooks._deliver_one", side_effect=capture):
                webhooks.fire_cycle_completed(_make_stats(errors=[]))
                done.wait(timeout=2.0)

        assert payloads[0]["success"] is True

    def test_success_false_when_errors(self):
        from spec1_api import webhooks

        done = threading.Event()
        payloads: list[dict] = []

        def capture(url, payload, secret, timeout):
            payloads.append(payload)
            done.set()

        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "https://h.example.com", "SPEC1_WEBHOOK_SECRET": ""}, clear=False):
            with patch("spec1_api.webhooks._deliver_one", side_effect=capture):
                webhooks.fire_cycle_completed(_make_stats(errors=["something broke"]))
                done.wait(timeout=2.0)

        assert payloads[0]["success"] is False


# ── _sign ─────────────────────────────────────────────────────────────────────

class TestSign:
    def test_signature_format(self):
        from spec1_api.webhooks import _sign
        sig = _sign(b"hello", "mysecret")
        assert sig.startswith("sha256=")
        assert len(sig) == len("sha256=") + 64  # sha256 hex = 64 chars

    def test_signature_is_deterministic(self):
        from spec1_api.webhooks import _sign
        assert _sign(b"payload", "secret") == _sign(b"payload", "secret")

    def test_different_secrets_produce_different_sigs(self):
        from spec1_api.webhooks import _sign
        assert _sign(b"payload", "secret1") != _sign(b"payload", "secret2")


# ── _deliver_one ──────────────────────────────────────────────────────────────

class TestDeliverOne:
    def test_success_logs_info(self):
        from spec1_api.webhooks import _deliver_one

        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = lambda self: self
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post = MagicMock(return_value=mock_resp)

        with patch("spec1_api.webhooks.httpx") as mock_httpx:
            mock_httpx.Client.return_value = mock_client
            # Should not raise
            _deliver_one("https://example.com", {"event": "test"}, None, 10)

    def test_failure_does_not_raise(self):
        from spec1_api.webhooks import _deliver_one

        with patch("spec1_api.webhooks.httpx") as mock_httpx:
            mock_httpx.Client.side_effect = Exception("connection refused")
            # Must not propagate
            _deliver_one("https://bad.example.com", {}, None, 5)


# ── _get_urls parsing ─────────────────────────────────────────────────────────

class TestGetUrls:
    def test_empty_env_returns_empty_list(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": ""}, clear=False):
            assert webhooks._get_urls() == []

    def test_single_url(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "https://example.com"}, clear=False):
            assert webhooks._get_urls() == ["https://example.com"]

    def test_multiple_urls_comma_separated(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "https://a.com, https://b.com"}, clear=False):
            urls = webhooks._get_urls()
            assert len(urls) == 2
            assert set(urls) == {"https://a.com", "https://b.com"}

    def test_strips_whitespace(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_URLS": "  https://example.com  "}, clear=False):
            assert webhooks._get_urls() == ["https://example.com"]

    def test_non_https_urls_filtered_out(self):
        from spec1_api import webhooks
        with patch.dict(
            os.environ,
            {"SPEC1_WEBHOOK_URLS": "http://insecure.example.com,https://secure.example.com"},
            clear=False,
        ):
            assert webhooks._get_urls() == ["https://secure.example.com"]


class TestGetTimeout:
    def test_valid_timeout(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_TIMEOUT": "15"}, clear=False):
            assert webhooks._get_timeout() == 15

    def test_invalid_timeout_uses_default(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_TIMEOUT": "abc"}, clear=False):
            assert webhooks._get_timeout() == 10

    def test_non_positive_timeout_uses_default(self):
        from spec1_api import webhooks
        with patch.dict(os.environ, {"SPEC1_WEBHOOK_TIMEOUT": "0"}, clear=False):
            assert webhooks._get_timeout() == 10
