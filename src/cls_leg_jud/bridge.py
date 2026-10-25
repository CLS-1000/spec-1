"""Legislative desk bridge — OLIS and state-legislature records as spec1_core Signals.

Candidate generators for ``python -m spec1_core.app.cycle --desk legislative``.
Each candidate is a standard ``spec1_core.schemas.models.Signal`` whose
``metadata`` carries what the Leg-Jud desk needs downstream:

    domain    "state_leg.<state>.<kind>"  — routes to the state_leg section
    priority  ELEVATED | STANDARD | MONITOR — the desk skips the 4 gates
    state, bill, sponsor, status, disclosure_regime, disclosure_gap, source_url

Sources:
  - OLIS measures (current regular session) whose last action is in the window
  - OLIS interim committee meetings with their agenda items
  - OpenStates / LegiScan bills via cls_osint.adapters.state_legislative;
    its synthetic fallback sample is dropped — fake bills never reach the desk

No source failure is fatal: errors are counted and the other sources continue.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from spec1_core.schemas.models import Signal

logger = logging.getLogger(__name__)

DEFAULT_SINCE_DAYS = 90
DEFAULT_LOOKAHEAD_DAYS = 14     # upcoming interim hearings are desk material too
DEFAULT_LIMIT = 25              # each candidate costs one local-model verification

SOURCE_OLIS = "olis"
SOURCE_OLIS_INTERIM = "olis_interim"
SOURCE_TYPE = "legislative"

_PRIORITY_RANK = {"ELEVATED": 0, "STANDARD": 1, "MONITOR": 2}


def _signal_id(*parts: Any) -> str:
    """Stable per (source, item, action date): a new action on a bill is a new signal."""
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"leg-{digest[:16]}"


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time(12, 0), tzinfo=timezone.utc)


def _make_signal(
    *,
    source: str,
    key: str,
    text: str,
    url: str,
    author: str,
    when: datetime,
    run_id: str,
    environment: str,
    metadata: dict[str, Any],
) -> Signal:
    return Signal(
        signal_id=_signal_id(source, key, when.date().isoformat()),
        source=source,
        source_type=SOURCE_TYPE,
        text=text,
        url=url,
        author=author,
        published_at=when,
        velocity=0.0,
        engagement=0.0,
        run_id=run_id,
        environment=environment,
        metadata=metadata,
    )


# ── OLIS measures ─────────────────────────────────────────────────────────────

def _measure_priority(status_name: str) -> str:
    if status_name in ("SIGNED", "VETOED", "OVERRIDDEN", "PASSED_BOTH_CHAMBERS",
                       "ENROLLED", "PASSED_ONE_CHAMBER"):
        return "ELEVATED"
    if status_name in ("IN_COMMITTEE", "PASSED_COMMITTEE"):
        return "STANDARD"
    return "MONITOR"


def olis_measure_signals(
    bills: Iterable[Any],
    *,
    since: datetime,
    run_id: str,
    environment: str,
    counts: dict[str, int],
) -> list[Signal]:
    """cls_pdx1 ``Bill`` records whose last action is on or after *since*."""
    out: list[Signal] = []
    for bill in bills:
        acted = bill.last_action_at or bill.introduced_at
        if acted is None:
            counts["dropped_no_date"] += 1
            continue
        when = _as_datetime(acted)
        if when < since:
            counts["dropped_stale"] += 1
            continue
        status = bill.status.name
        status_text = status.lower().replace("_", " ")
        text = (
            f"Oregon {bill.external_id} ({bill.chamber}): {bill.title.rstrip('.')}. "
            f"Status: {status_text}. Last action {acted.isoformat()}."
            + (f" Chief sponsor: {bill.sponsor}." if bill.sponsor else "")
        )
        out.append(_make_signal(
            source=SOURCE_OLIS,
            key=bill.external_id,
            text=text,
            url=bill.source_url,
            author=bill.sponsor or "",
            when=when,
            run_id=run_id,
            environment=environment,
            metadata={
                "domain": "state_leg.or.measure",
                "priority": _measure_priority(status),
                "state": "OR",
                "bill": bill.external_id,
                "title": bill.title,
                "sponsor": bill.sponsor or "",
                "status": status_text,
                "disclosure_regime": "FULL",
                "disclosure_gap": False,
                "source_url": bill.source_url,
            },
        ))
    return out


# ── OLIS interim committees ───────────────────────────────────────────────────

def olis_interim_signals(
    meetings: Iterable[dict[str, Any]],
    *,
    since: datetime,
    until: datetime,
    run_id: str,
    environment: str,
    counts: dict[str, int],
) -> list[Signal]:
    """One signal per interim committee meeting that has a substantive agenda."""
    out: list[Signal] = []
    for m in meetings:
        when: datetime = m["meeting_date"]
        if not since <= when <= until:
            counts["dropped_stale"] += 1
            continue
        items = m.get("items") or []
        if not items:
            counts["dropped_empty_agenda"] += 1
            continue
        measures = sorted({i["measure"] for i in items if i.get("measure")})
        topics = "; ".join(
            (f"{i['measure']}: " if i.get("measure") else "") + i["text"]
            for i in items if i.get("text") or i.get("measure")
        )
        upcoming = when > datetime.now(timezone.utc)
        text = (
            f"Oregon interim committee — {m['committee_name']} "
            f"{'scheduled for' if upcoming else 'met'} {when.strftime('%Y-%m-%d %H:%M %Z')}. "
            f"Agenda: {topics}"
        )
        out.append(_make_signal(
            source=SOURCE_OLIS_INTERIM,
            key=f"{m['session_key']}:{m['committee_code']}:{when.isoformat()}",
            text=text,
            url=m.get("agenda_url", ""),
            author=m["committee_name"],
            when=when,
            run_id=run_id,
            environment=environment,
            metadata={
                "domain": "state_leg.or.interim_committee",
                "priority": "STANDARD" if measures else "MONITOR",
                "state": "OR",
                "bill": ", ".join(measures) or f"{m['committee_name']} agenda",
                "title": f"{m['committee_name']} — {when.date().isoformat()}",
                "sponsor": m["committee_name"],
                "status": "scheduled" if upcoming else "held",
                "disclosure_regime": "FULL",
                "disclosure_gap": False,
                "source_url": m.get("agenda_url", ""),
                "session_key": m["session_key"],
                "committee_code": m["committee_code"],
                "agenda_items": len(items),
            },
        ))
    return out


# ── Other states (OpenStates / LegiScan) ──────────────────────────────────────

def state_leg_signals(
    records: Iterable[Any],
    *,
    since: datetime,
    run_id: str,
    environment: str,
    counts: dict[str, int],
) -> list[Signal]:
    """cls_osint ``StateLegRecord``s filed on or after *since*; synthetic samples dropped."""
    out: list[Signal] = []
    for rec in records:
        if (rec.metadata or {}).get("source") == "synthetic":
            counts["dropped_synthetic"] += 1
            continue
        try:
            when = _as_datetime(date.fromisoformat(str(rec.filed_at)[:10]))
        except ValueError:
            counts["dropped_no_date"] += 1
            continue
        if when < since:
            counts["dropped_stale"] += 1
            continue
        source = str((rec.metadata or {}).get("source") or "openstates").lower()
        text = (
            f"{rec.state} {rec.bill_id} ({rec.chamber.title()}): {rec.title.rstrip('.')}. "
            f"Status: {rec.status.lower().replace('_', ' ')}. {rec.summary}"
            + (f" Sponsor: {rec.sponsor}." if rec.sponsor else "")
        )
        out.append(_make_signal(
            source=source,
            key=rec.record_id,
            text=text,
            url=rec.source_url,
            author=rec.sponsor or "",
            when=when,
            run_id=run_id,
            environment=environment,
            metadata={
                "domain": f"state_leg.{rec.state.lower()}.bill",
                "priority": "ELEVATED" if rec.status in ("ENACTED", "PASSED_HOUSE", "PASSED_SENATE")
                else "STANDARD",
                "state": rec.state,
                "bill": rec.bill_id,
                "title": rec.title,
                "sponsor": rec.sponsor or "",
                "status": rec.status.lower().replace("_", " "),
                "disclosure_regime": rec.disclosure_regime,
                "disclosure_gap": rec.disclosure_gap,
                "source_url": rec.source_url,
            },
        ))
    return out


# ── Orchestration ─────────────────────────────────────────────────────────────

def _default_olis_bills() -> tuple[list[Any], list[str]]:
    from cls_pdx1.sources.olis import OlisAdapter
    result = OlisAdapter().fetch()
    return result.records, result.errors


def _default_interim(since: datetime, until: datetime) -> list[dict[str, Any]]:
    from cls_pdx1.sources.olis import fetch_interim_meetings, latest_interim_session_key
    return fetch_interim_meetings(latest_interim_session_key(), since, until)


def _default_state_leg() -> list[Any]:
    from cls_osint.adapters.state_legislative import collect
    return collect()


def collect_candidates(
    *,
    run_id: str,
    environment: str = "production",
    since_days: int = DEFAULT_SINCE_DAYS,
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    limit: Optional[int] = DEFAULT_LIMIT,
    seen_ids: Optional[set[str]] = None,
    now: Optional[datetime] = None,
    olis_fetch: Callable[[], tuple[list[Any], list[str]]] = _default_olis_bills,
    interim_fetch: Callable[[datetime, datetime], list[dict[str, Any]]] = _default_interim,
    state_fetch: Callable[[], list[Any]] = _default_state_leg,
) -> tuple[list[Signal], dict[str, Any]]:
    """All legislative candidates in the window, newest and highest-priority first.

    Returns (signals, report). The report counts what each source yielded and
    why candidates were dropped; ``errors`` lists source failures.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=since_days)
    until = now + timedelta(days=lookahead_days)
    counts: dict[str, int] = {
        "dropped_no_date": 0, "dropped_stale": 0, "dropped_synthetic": 0,
        "dropped_empty_agenda": 0, "dropped_seen": 0, "dropped_over_limit": 0,
    }
    errors: list[str] = []
    per_source: dict[str, int] = {}
    signals: list[Signal] = []

    def _run(name: str, produce: Callable[[], list[Signal]]) -> None:
        try:
            got = produce()
        except Exception as exc:  # a dead source must not stop the desk
            logger.warning("Legislative source %s failed: %s", name, exc)
            errors.append(f"{name}:{exc}")
            got = []
        per_source[name] = len(got)
        signals.extend(got)

    def _olis() -> list[Signal]:
        bills, olis_errors = olis_fetch()
        errors.extend(f"olis:{e}" for e in olis_errors if "failed to parse" not in e)
        return olis_measure_signals(bills, since=since, run_id=run_id,
                                    environment=environment, counts=counts)

    _run(SOURCE_OLIS, _olis)
    _run(SOURCE_OLIS_INTERIM, lambda: olis_interim_signals(
        interim_fetch(since, until), since=since, until=until, run_id=run_id,
        environment=environment, counts=counts))
    _run("state_legislative", lambda: state_leg_signals(
        state_fetch(), since=since, run_id=run_id, environment=environment, counts=counts))
    if counts["dropped_synthetic"]:
        logger.warning("Dropped %d synthetic state-legislature record(s) — no live "
                       "OpenStates/LegiScan data (set OPENSTATES_API_KEY)", counts["dropped_synthetic"])

    if seen_ids:
        fresh = [s for s in signals if s.signal_id not in seen_ids]
        counts["dropped_seen"] = len(signals) - len(fresh)
        signals = fresh

    # Highest priority first; within a priority, closest to now (past or upcoming).
    signals.sort(key=lambda s: (_PRIORITY_RANK.get(s.metadata.get("priority"), 3),
                                abs((s.published_at - now).total_seconds())))
    if limit is not None and len(signals) > limit:
        counts["dropped_over_limit"] = len(signals) - limit
        signals = signals[:limit]

    report = {"per_source": per_source, "counts": counts, "errors": errors,
              "since": since.isoformat(), "until": until.isoformat()}
    return signals, report
