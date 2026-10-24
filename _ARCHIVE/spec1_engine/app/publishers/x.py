"""app/publishers/x.py — World State Brief publisher.

Single-writer, append-only, run_id-traced. Emits the daily 06:00 PT thread
to X. Honors the same 4-gate pattern as the rest of SPEC-1: any section
that fails validation is skipped, never silently downgraded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

try:
    import tweepy
except ImportError:  # tweepy is an optional runtime dep
    tweepy = None  # type: ignore[assignment]

from cls_db.publish_log import append_event, has_x_publish, load_x_publish
from spec1_engine.schemas.brief import BriefSection, WorldStateBrief

logger = logging.getLogger(__name__)

PT = ZoneInfo("America/Los_Angeles")
MAX_POST_CHARS = 280
ARCHIVE_URL = "https://mjlak1000.github.io/cls-portfolio"


@dataclass(frozen=True)
class PublishResult:
    run_id: str
    thread_root_id: str
    posted_count: int
    skipped_sections: tuple[str, ...]
    cycle_utc: datetime


class XPublisher:
    """Single-writer publisher. One instance per cycle; never share."""

    def __init__(self, client: "tweepy.Client", *, dry_run: bool = False) -> None:
        self._client = client
        self._dry_run = dry_run

    def publish_brief(
        self,
        brief: WorldStateBrief,
        *,
        run_id: str,
    ) -> PublishResult:
        cycle_utc = datetime.now(timezone.utc)

        if self._already_published(run_id):
            logger.info("run_id=%s already published; idempotent skip", run_id)
            return self._load_result(run_id)

        posts = self._render_thread(brief, run_id=run_id, cycle_utc=cycle_utc)
        thread_root_id, posted = self._emit_thread(posts)

        result = PublishResult(
            run_id=run_id,
            thread_root_id=thread_root_id,
            posted_count=posted,
            skipped_sections=tuple(s.kind for s in brief.sections if not s.valid),
            cycle_utc=cycle_utc,
        )
        append_event(
            "x_publish",
            run_id=run_id,
            thread_root_id=thread_root_id,
            posted_count=posted,
            skipped_sections=result.skipped_sections,
            cycle_utc=cycle_utc.isoformat(),
        )
        return result

    # --- rendering ---

    def _render_thread(
        self,
        brief: WorldStateBrief,
        *,
        run_id: str,
        cycle_utc: datetime,
    ) -> list[str]:
        valid = [s for s in brief.sections if s.valid]
        n = len(valid)
        if n == 0:
            raise RuntimeError(f"run_id={run_id} no valid sections; refusing publish")

        date_pt = cycle_utc.astimezone(PT).strftime("%Y-%m-%d")
        total = n + 1  # sections + footer (header is unnumbered)

        posts: list[str] = [
            _truncate(
                f"World State Brief · {date_pt}\n"
                f"{brief.synopsis}\n\n"
                f"↓ {n} verified signal{'s' if n != 1 else ''}"
            )
        ]
        for i, section in enumerate(valid, start=1):
            posts.append(_truncate(_render_section(section, i, total)))
        posts.append(
            _truncate(
                f"[{total}/{total}] run_id: {run_id[:8]}\n"
                f"cycle: {cycle_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
                f"methodology + archive: {ARCHIVE_URL}"
            )
        )
        return posts

    # --- emission ---

    def _emit_thread(self, posts: Sequence[str]) -> tuple[str, int]:
        if self._dry_run:
            for p in posts:
                logger.info("DRY %s", p.replace("\n", " ⏎ "))
            return ("dry-run", len(posts))

        root_id: str | None = None
        in_reply_to: str | None = None
        posted = 0
        for p in posts:
            resp = self._client.create_tweet(text=p, in_reply_to_tweet_id=in_reply_to)
            tweet_id = resp.data["id"]
            in_reply_to = tweet_id
            root_id = root_id or tweet_id
            posted += 1
        assert root_id is not None
        return (root_id, posted)

    # --- idempotency (delegated to cls_db) ---

    def _already_published(self, run_id: str) -> bool:
        return has_x_publish(run_id)

    def _load_result(self, run_id: str) -> PublishResult:
        return load_x_publish(run_id)


# --- section rendering ---

def _render_section(section: BriefSection, idx: int, total: int) -> str:
    head = f"[{idx}/{total}]"
    d = section.payload
    if section.kind == "congress_trade":
        return (
            f"{head} CONGRESS · TRADE CONFLICT\n"
            f"{d['member']} · {d['chamber']} · {d['party']}-{d['state']}\n"
            f"{d['ticker']} {d['action']} {d['amount_band']}\n"
            f"committee: {d['committee_overlap']:.2f} · donor: {d['donor_proximity']:.2f}\n"
            f"conflict: {d['composite']:.2f}"
        )
    if section.kind == "fara_proximity":
        return (
            f"{head} FARA · PROXIMITY FLAG\n"
            f"{d['registrant']} → {d['country']}\n"
            f"bill: {d['bill_id']}\n"
            f"proximity: {d['score']:.2f}"
        )
    if section.kind == "model_legislation":
        return (
            f"{head} MODEL LEGISLATION\n"
            f"origin: {d['origin_state']} · {d['bill_id']}\n"
            f"propagated: {d['n_states']} states\n"
            f"language match: {d['top_match_pct']:.0%}"
        )
    if section.kind == "sector_signal":
        return (
            f"{head} SECTOR SIGNAL\n"
            f"sector: {d['sector']}\n"
            f"active bills: {d['active_bills']} · velocity: {d['velocity']}"
        )
    raise ValueError(f"unknown section kind: {section.kind}")


def _truncate(text: str) -> str:
    if len(text) <= MAX_POST_CHARS:
        return text
    return text[: MAX_POST_CHARS - 1].rstrip() + "…"
