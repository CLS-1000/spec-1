# @domain:   machine
# @module:   webhooks
# @loc:      gh_main
# @status:   stable
# @depends:  spec1_core, cls_db

"""Webhook delivery for SPEC-1 cycle events.

When ``SPEC1_WEBHOOK_URLS`` is set (comma-separated list of HTTPS URLs),
SPEC-1 will POST a JSON payload to each URL after every completed cycle.

Payload schema::

    {
        "event": "cycle.completed",
        "run_id": "<run-id>",
        "started_at": "<ISO-8601>",
        "finished_at": "<ISO-8601>",
        "signals_harvested": <int>,
        "records_stored": <int>,
        "errors": ["..."],
        "success": <bool>
    }

Delivery is fire-and-forget (non-blocking background thread).  Failures are
logged but never crash the cycle.

Environment variables:
- ``SPEC1_WEBHOOK_URLS``: comma-separated list of webhook URLs
- ``SPEC1_WEBHOOK_SECRET``: optional HMAC-SHA256 secret; when set, adds an
  ``X-Spec1-Signature`` header with ``sha256=<hex>`` so receivers can verify
  authenticity
- ``SPEC1_WEBHOOK_TIMEOUT``: HTTP timeout in seconds (default: 10)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10


def _get_urls() -> list[str]:
    raw = os.environ.get("SPEC1_WEBHOOK_URLS", "")
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    valid: list[str] = []
    for url in urls:
        if url.lower().startswith("https://"):
            valid.append(url)
        else:
            logger.warning("Ignoring non-HTTPS webhook URL: %s", url)
    return valid


def _get_secret() -> Optional[str]:
    return os.environ.get("SPEC1_WEBHOOK_SECRET", "").strip() or None


def _get_timeout() -> int:
    raw = os.environ.get("SPEC1_WEBHOOK_TIMEOUT", str(_DEFAULT_TIMEOUT)).strip()
    try:
        timeout = int(raw)
    except ValueError:
        logger.warning("Invalid SPEC1_WEBHOOK_TIMEOUT=%r; using default=%s", raw, _DEFAULT_TIMEOUT)
        return _DEFAULT_TIMEOUT
    if timeout <= 0:
        logger.warning("Non-positive SPEC1_WEBHOOK_TIMEOUT=%s; using default=%s", timeout, _DEFAULT_TIMEOUT)
        return _DEFAULT_TIMEOUT
    return timeout


def _sign(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _deliver_one(url: str, payload: dict, secret: Optional[str], timeout: int) -> None:
    """POST *payload* to *url*.  Logs success/failure; never raises."""
    try:
        payload_bytes = json.dumps(payload, default=str).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "spec1-webhook/1.0",
        }
        if secret:
            headers["X-Spec1-Signature"] = _sign(payload_bytes, secret)

        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, content=payload_bytes, headers=headers)
        if resp.is_success:
            logger.info("Webhook delivered to %s (status=%s)", url, resp.status_code)
        else:
            logger.warning("Webhook to %s returned %s: %s", url, resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Webhook delivery to %s failed: %s", url, exc)


def fire_cycle_completed(stats: dict) -> None:
    """Fire cycle-completed webhook events asynchronously.

    This is non-blocking — delivery happens in daemon threads so it never
    delays or crashes the API response.
    """
    urls = _get_urls()
    if not urls:
        return

    secret = _get_secret()
    timeout = _get_timeout()

    payload = {
        "event": "cycle.completed",
        "run_id": stats.get("run_id", ""),
        "started_at": stats.get("started_at", ""),
        "finished_at": stats.get("finished_at", ""),
        "signals_harvested": stats.get("signals_harvested", 0),
        "records_stored": stats.get("records_stored", 0),
        "errors": stats.get("errors", []),
        "success": len(stats.get("errors", [])) == 0,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    for url in urls:
        # Daemon threads are intentionally fire-and-forget: they do not block
        # the API response and are automatically reaped if the process exits.
        # Trade-off: a webhook in-flight at shutdown may be lost.  Operators
        # that need guaranteed delivery should configure an external queue.
        t = threading.Thread(
            target=_deliver_one,
            args=(url, payload, secret, timeout),
            daemon=True,
        )
        t.start()
