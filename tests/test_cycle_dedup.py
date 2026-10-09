# @domain:   intelligence
# @module:   test_cycle_dedup
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Cross-run dedup in run_cycle, and test isolation from the real repo paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import feedparser

from spec1_core.app.cycle import run_cycle
from spec1_core.intelligence.store import JsonlStore

REPO_ROOT = Path(__file__).resolve().parents[1]

_ITEM = """
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>Analysis of Russian military intelligence operations in Ukraine. NATO alliance
      defense strategy and nuclear deterrence reviewed. Cyber warfare threat assessment confirmed by
      Pentagon officials in a detailed security report on alliance operations.</description>
      <pubDate>Thu, 10 Apr 2025 12:00:00 +0000</pubDate>
    </item>"""


def _feed(*items: tuple[str, str]):
    body = "".join(_ITEM.format(title=t, link=l) for t, l in items)
    xml = f'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>{body}</channel></rss>'
    return feedparser.parse(xml)


TWO_ITEMS = (("Russia Military Intelligence Update", "https://example.com/a1"),
             ("NATO Defense Posture Review", "https://example.com/a2"))


def _run(store_path: Path, parsed, run_id: str, **kw) -> dict:
    with patch("spec1_core.signal.harvester.feedparser.parse", return_value=parsed):
        return run_cycle(store_path=store_path, run_id=run_id, environment="test",
                         feeds={"test_feed": "https://example.com/feed"}, verbose=False, **kw)


def test_store_signal_ids(tmp_path):
    store = JsonlStore(tmp_path / "s.jsonl")
    assert store.signal_ids() == set()
    store.append({"signal_id": "a"})
    store.append({"signal_id": "b"})
    store.append({"signal_id": "a"})
    store.append({"record_id": "no-signal-id"})
    assert store.signal_ids() == {"a", "b"}


def test_second_run_skips_signals_already_stored(tmp_path):
    store_path = tmp_path / "intel.jsonl"
    parsed = _feed(*TWO_ITEMS)

    first = _run(store_path, parsed, "run-dedup-1")
    assert first["records_stored"] > 0, "fixture must produce stored records for this test to mean anything"
    assert first["signals_skipped_seen"] == 0

    second = _run(store_path, parsed, "run-dedup-2")
    assert second["records_stored"] == 0
    assert second["signals_skipped_seen"] == first["records_stored"]
    assert second["signals_harvested"] == first["signals_harvested"]  # harvest itself is unchanged
    assert JsonlStore(store_path).count() == first["records_stored"]


def test_new_signal_still_stored_alongside_seen_ones(tmp_path):
    store_path = tmp_path / "intel.jsonl"
    _run(store_path, _feed(TWO_ITEMS[0]), "run-dedup-a")
    before = JsonlStore(store_path).signal_ids()

    stats = _run(store_path, _feed(*TWO_ITEMS), "run-dedup-b")
    assert stats["signals_skipped_seen"] == len(before)
    assert stats["records_stored"] == 1
    assert len(JsonlStore(store_path).signal_ids()) == len(before) + 1


def test_duplicate_item_within_one_harvest_stored_once(tmp_path):
    store_path = tmp_path / "intel.jsonl"
    stats = _run(store_path, _feed(TWO_ITEMS[0], TWO_ITEMS[0]), "run-dedup-dupe")
    assert stats["signals_harvested"] == 2
    assert stats["records_stored"] == 1
    assert stats["signals_skipped_seen"] == 1


def test_reprocess_seen_opt_out(tmp_path):
    store_path = tmp_path / "intel.jsonl"
    parsed = _feed(*TWO_ITEMS)
    first = _run(store_path, parsed, "run-dedup-x")
    second = _run(store_path, parsed, "run-dedup-y", skip_seen=False)
    assert second["signals_skipped_seen"] == 0
    assert second["records_stored"] == first["records_stored"]
    assert JsonlStore(store_path).count() == 2 * first["records_stored"]


def test_unreadable_store_fails_closed(tmp_path):
    """If prior signal IDs can't be read, nothing is scored or stored, and the error is recorded."""
    store_path = tmp_path / "intel.jsonl"
    with patch.object(JsonlStore, "signal_ids", side_effect=OSError("disk read failed")):
        stats = _run(store_path, _feed(*TWO_ITEMS), "run-dedup-fail")
    assert stats["signals_harvested"] == 2
    assert stats["records_stored"] == 0
    assert stats["opportunities_found"] == 0
    assert any(e.startswith("dedup:") for e in stats["errors"])
    assert JsonlStore(store_path).count() == 0


def test_missing_store_is_not_a_dedup_failure(tmp_path):
    """A first run with no store yet must still score and store normally."""
    stats = _run(tmp_path / "does-not-exist.jsonl", _feed(*TWO_ITEMS), "run-dedup-cold")
    assert stats["records_stored"] > 0
    assert not any(e.startswith("dedup:") for e in stats["errors"])


def _snapshot(paths: list[Path]) -> dict[str, float]:
    snap = {}
    for base in paths:
        if base.is_file():
            snap[str(base)] = base.stat().st_mtime
        elif base.is_dir():
            for p in base.rglob("*"):
                if p.is_file():
                    snap[str(p)] = p.stat().st_mtime
    return snap


def test_cycle_in_tests_writes_nothing_into_repo(tmp_path):
    """Regression guard for the June 17 batch of test-generated issue PDFs."""
    watched = [REPO_ROOT / p for p in ("briefs", "generated", "data", "logs", "spec1.db")]
    before = _snapshot(watched)
    stats = _run(tmp_path / "intel.jsonl", _feed(*TWO_ITEMS), "run-isolation")
    assert stats["records_stored"] > 0
    assert _snapshot(watched) == before
