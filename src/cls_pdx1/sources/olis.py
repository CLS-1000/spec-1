# @domain:   citizens_source
# @module:   sources_olis
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""OLIS adapter — Oregon Legislative Information System.

Tracks bills, votes, committee assignments, and hearing witnesses.
OData API: https://api.oregonlegislature.gov/odata/odataservice.svc/

Fetch priority:
  1. Pre-loaded bill_data (tests / manual injection)
  2. Live OData HTTP fetch → writes cache on success
  3. Cached last-good fetch (if live fails)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

from cls_pdx1.models import Bill, BillStatus, Jurisdiction, Provenance, _make_id
from cls_pdx1.sources.base import AdapterResult, BaseAdapter

logger = logging.getLogger(__name__)

_OLIS_BASE = "https://api.oregonlegislature.gov/odata/odataservice.svc/"
_MEASURES_URL = f"{_OLIS_BASE}Measures"
_SOURCE_URI = "https://www.oregonlegislature.gov/"
_HEADERS = {
    "User-Agent": "spec1-pdx1i/0.1 (civic intelligence; contact: research@spec1.io)",
    "Accept": "application/json",
}
_TIMEOUT = 20
_PAGE_SIZE = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _map_status(raw: str) -> BillStatus:
    raw_lower = raw.lower()
    # Check longest matches first to avoid substring ambiguity
    if "passed both chambers" in raw_lower or "enrolled" in raw_lower:
        return BillStatus.PASSED_BOTH_CHAMBERS
    if "signed" in raw_lower:
        return BillStatus.SIGNED
    if "vetoed" in raw_lower:
        return BillStatus.VETOED
    if "overridden" in raw_lower:
        return BillStatus.OVERRIDDEN
    if "passed committee" in raw_lower:
        return BillStatus.PASSED_COMMITTEE
    if "passed" in raw_lower:
        return BillStatus.PASSED_ONE_CHAMBER
    if "committee" in raw_lower:
        return BillStatus.IN_COMMITTEE
    if "failed" in raw_lower:
        return BillStatus.FAILED
    if "dead" in raw_lower or "pocket" in raw_lower:
        return BillStatus.DEAD
    return BillStatus.INTRODUCED


_CHAMBER_BY_PREFIX = {"H": "House", "S": "Senate"}
_MEASURE_URL = "https://olis.oregonlegislature.gov/liz/{session}/Measures/Overview/{prefix}{number}"


def _first(raw: dict[str, Any], *keys: str, default: Any = "") -> Any:
    """First non-empty value among ``keys``."""
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return default


def _external_id(raw: dict[str, Any]) -> str:
    """'HB 2001'. The live feed splits prefix and number; older fixtures don't.

    Using MeasureNumber alone would give HB 2001 and SB 2001 the same bill_id.
    """
    number = raw.get("MeasureNumber")
    prefix = (raw.get("MeasurePrefix") or "").strip()
    if number in (None, ""):
        return str(raw.get("bill_id") or "").strip()
    number = str(number).strip()
    return f"{prefix} {number}" if prefix else number


def _parse_date(value: Any) -> Optional[date]:
    """'2026-09-03T10:14:39' (OData) or '2026-09-03' → date; None if absent or malformed."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        return None


def _live_status(raw: dict[str, Any]) -> BillStatus:
    """Status from the fields the Measures entity actually has.

    Vetoed and ChapterNumber are structured; CurrentLocation is free text and
    only used when neither settles it.
    """
    if raw.get("Vetoed") is True:
        return BillStatus.VETOED
    if raw.get("ChapterNumber") not in (None, ""):
        return BillStatus.SIGNED
    return _map_status(str(raw.get("CurrentLocation") or "introduced"))


def _parse_bill(
    raw: dict[str, Any], fetched_at: datetime, session_key: Optional[str] = None
) -> Optional[Bill]:
    try:
        external_id = _external_id(raw)
        if not external_id:
            return None

        prefix = (raw.get("MeasurePrefix") or "").strip()
        title = _first(raw, "RelatingClause", "CatchLine", "RelatingToFull", "RelatingTo", "title")
        if "CurrentStatus" in raw or "status" in raw:
            status = _map_status(str(_first(raw, "CurrentStatus", "status", default="introduced")))
        else:
            status = _live_status(raw)
        sponsor = _first(raw, "ChiefSponsor", "sponsor")
        chamber = _first(raw, "Chamber", "chamber",
                         default=_CHAMBER_BY_PREFIX.get(prefix[:1].upper(), "Unknown"))
        session = raw.get("SessionKey") or session_key
        default_url = (
            _MEASURE_URL.format(session=session, prefix=prefix, number=raw["MeasureNumber"])
            if prefix and session else _SOURCE_URI
        )
        source_url = raw.get("source_url") or default_url

        bill_id = _make_id("bill", str(int(Jurisdiction.STATE_OREGON)), external_id)
        return Bill(
            bill_id=bill_id,
            external_id=external_id,
            title=str(title).strip() or external_id,
            jurisdiction=Jurisdiction.STATE_OREGON,
            chamber=chamber,
            sponsor=sponsor or None,
            status=status,
            introduced_at=_parse_date(_first(raw, "CreatedDate", "introduced_at", default=None)),
            last_action_at=_parse_date(_first(raw, "ModifiedDate", "last_action_at", default=None)),
            source_url=source_url,
            tags=raw.get("tags", []),
            provenance=Provenance(
                source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
                source_name="OLIS",
                fetched_at=fetched_at,
            ),
        )
    except Exception as exc:
        logger.debug("OLIS bill parse error: %s", exc)
        return None


def _current_session_key() -> str:
    year = datetime.now(timezone.utc).year
    return f"{year}R1"


class OlisAdapter(BaseAdapter):
    """Returns Bill records from OLIS.

    Fetch priority:
      1. pre-loaded bill_data (tests / manual injection)
      2. Live OData HTTP → writes cache on success
      3. Cached last-good fetch → if live fails
    """

    source_name = "OLIS"

    def __init__(
        self,
        bill_data: Optional[list[dict]] = None,
        session_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._bill_data = bill_data
        self._session_key = session_key or _current_session_key()
        self._cache_dir = cache_dir or Path("cache/pdx1")

    def _cache_path(self) -> Path:
        return self._cache_dir / f"olis_{self._session_key}.json"

    def _write_cache(self, data: list[dict]) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path().write_text(json.dumps(data), encoding="utf-8")
        except OSError as exc:
            logger.warning("OLIS: cache write failed: %s", exc)

    def _read_cache(self) -> Optional[list[dict]]:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("OLIS: cache read failed: %s", exc)
            return None

    def fetch(self) -> AdapterResult:
        if self._bill_data is not None:
            return self._parse_data(self._bill_data)
        return self._fetch_with_fallback()

    def _fetch_with_fallback(self) -> AdapterResult:
        all_data: list[dict] = []
        url: Optional[str] = _MEASURES_URL
        params: Optional[dict] = {
            "$format": "json",
            "$filter": f"SessionKey eq '{self._session_key}'",
            "$top": _PAGE_SIZE,
        }
        fetch_error: Optional[str] = None
        try:
            while url:
                resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                payload = resp.json()
                all_data.extend(payload.get("value", []))
                url = payload.get("@odata.nextLink")
                params = None
            logger.info("OLIS: fetched %d measures for session %s", len(all_data), self._session_key)
            self._write_cache(all_data)
            return self._parse_data(all_data)
        except requests.RequestException as exc:
            fetch_error = str(exc)
            logger.warning("OLIS HTTP fetch failed: %s — trying cache", fetch_error)

        cached = self._read_cache()
        if cached is not None:
            logger.info("OLIS: using cached data (%d records)", len(cached))
            result = self._parse_data(cached)
            result.errors.insert(0, f"OLIS live fetch failed ({fetch_error}); serving cached data")
            return result

        return AdapterResult(
            source_name=self.source_name,
            errors=[f"OLIS HTTP error: {fetch_error}; no cache available"],
        )

    def _parse_data(self, data: list[dict]) -> AdapterResult:
        fetched_at = _now()
        records: list[Bill] = []
        errors: list[str] = []
        for raw in data:
            bill = _parse_bill(raw, fetched_at, self._session_key)
            if bill:
                records.append(bill)
            else:
                errors.append(f"failed to parse: {_external_id(raw) or '?'}")
        logger.info("OLIS: parsed %d bills, %d errors", len(records), len(errors))
        return AdapterResult(records=records, errors=errors, source_name=self.source_name)


# ── Interim committee meetings ────────────────────────────────────────────────

_INTERIM_FALLBACK_SESSION = "2025I1"
_TAG_RE = re.compile(r"<[^>]+>")
_OLIS_TZ = ZoneInfo("America/Los_Angeles")   # OLIS meeting times are Salem local time
# Agenda lines that carry no topic of their own.
_BOILERPLATE_ITEMS = {
    "invited speakers only", "invited testimony only", "public testimony", "public hearing",
    "work session", "informational meeting", "informational meeting only",
}


def _get_all(entity: str, params: dict[str, Any]) -> list[dict]:
    """Every row of an OData entity query, following @odata.nextLink. Raises on HTTP error."""
    rows: list[dict] = []
    url: Optional[str] = f"{_OLIS_BASE}{entity}"
    query: Optional[dict[str, Any]] = {"$format": "json", **params}
    while url:
        resp = requests.get(url, params=query, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        rows.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
        query = None
    return rows


def latest_interim_session_key() -> str:
    """Newest interim SessionKey (e.g. '2025I1'); the fallback if OLIS can't be reached."""
    try:
        sessions = _get_all("LegislativeSessions", {"$orderby": "BeginDate desc", "$top": 10})
    except requests.RequestException as exc:
        logger.warning("OLIS: session lookup failed (%s); using %s", exc, _INTERIM_FALLBACK_SESSION)
        return _INTERIM_FALLBACK_SESSION
    for session in sessions:
        key = str(session.get("SessionKey") or "")
        if re.fullmatch(r"\d{4}I\d+", key):
            return key
    return _INTERIM_FALLBACK_SESSION


def _odata_dt(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(_OLIS_TZ)
    return f"datetime'{value.strftime('%Y-%m-%dT%H:%M:%S')}'"


def fetch_interim_meetings(
    session_key: str,
    since: datetime,
    until: datetime,
) -> list[dict[str, Any]]:
    """Committee meetings in [since, until] with their agenda items.

    Each meeting: committee_code, committee_name, meeting_date (tz-aware, Pacific),
    status, agenda_url, and items — a list of {"text", "measure"} with HTML
    stripped and empty items dropped. Raises requests.RequestException on
    HTTP failure; the caller decides how to degrade.
    """
    window = (f"SessionKey eq '{session_key}' and MeetingDate ge {_odata_dt(since)} "
              f"and MeetingDate le {_odata_dt(until)}")
    meetings = _get_all("CommitteeMeetings", {"$filter": window})
    items = _get_all("CommitteeAgendaItems", {"$filter": window})
    names = {
        c.get("CommitteeCode"): c.get("CommitteeName")
        for c in _get_all("Committees", {"$filter": f"SessionKey eq '{session_key}'"})
    }

    by_meeting: dict[tuple[str, str], list[dict[str, str]]] = {}
    for item in sorted(items, key=lambda i: i.get("PrintOrder") or 0):
        text = " ".join(_TAG_RE.sub(" ", str(item.get("Comments") or "")).split())
        prefix = (item.get("MeasurePrefix") or "").strip()
        number = item.get("MeasureNumber")
        measure = f"{prefix} {number}" if prefix and number not in (None, "") else ""
        if text.lower().rstrip(".") in _BOILERPLATE_ITEMS:
            text = ""
        if not text and not measure:
            continue
        # The API spells this field "CommitteCode" on agenda items.
        key = (str(item.get("CommitteCode") or item.get("CommitteeCode") or ""),
               str(item.get("MeetingDate") or ""))
        by_meeting.setdefault(key, []).append({"text": text, "measure": measure})

    out: list[dict[str, Any]] = []
    for m in meetings:
        code = str(m.get("CommitteeCode") or "")
        raw_date = str(m.get("MeetingDate") or "")
        try:
            when = datetime.fromisoformat(raw_date[:19]).replace(tzinfo=_OLIS_TZ)
        except ValueError:
            continue
        out.append({
            "session_key": session_key,
            "committee_code": code,
            "committee_name": names.get(code) or code,
            "meeting_date": when,
            "status": m.get("MeetingStatus") or "",
            "agenda_url": m.get("AgendaUrl") or _SOURCE_URI,
            "items": by_meeting.get((code, raw_date), []),
        })
    logger.info("OLIS: %d interim meetings (%d agenda items) for %s",
                len(out), sum(len(m["items"]) for m in out), session_key)
    return out
