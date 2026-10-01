# @domain:   citizens_source
# @module:   sources_orestar
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""ORESTAR adapter — Oregon SOS campaign finance records.

Source: Oregon Secretary of State bulk CSV export.
Export: https://sos.oregon.gov/elections/Pages/orestar.aspx
Columns (2025): filer_id, filer_name, transaction_type, amount,
    contributor_name, contributor_address, transaction_date, election_year

Fetch priority:
  1. Local CSV path (fastest, for pre-downloaded files)
  2. Live HTTP bulk ZIP download → writes cache on success
  3. Cached last-good CSV (if live fails)
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import requests

from cls_pdx1.models import Affiliation, ConfidenceTier, EdgeType, Provenance
from cls_pdx1.sources.base import AdapterResult, BaseAdapter

logger = logging.getLogger(__name__)

_SOURCE_URI_BASE = "https://sos.oregon.gov/elections/Pages/orestar.aspx"
_BULK_URL_TEMPLATE = (
    "https://sos.oregon.gov/elections/Documents/orestar/{year}_report_transactions.zip"
)
_HEADERS = {
    "User-Agent": "spec1-pdx1i/0.1 (civic intelligence; contact: research@spec1.io)",
}
_TIMEOUT = 60  # bulk file can be large


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_row(row: dict, fetched_at: datetime) -> Optional[Affiliation]:
    """Parse a single ORESTAR CSV row into an Affiliation edge."""
    try:
        amount_str = row.get("amount", "0").replace("$", "").replace(",", "").strip()
        amount = float(amount_str) if amount_str else 0.0
        txn_date_str = row.get("transaction_date", "")
        try:
            txn_date = datetime.strptime(txn_date_str, "%m/%d/%Y").date()
        except ValueError:
            txn_date = fetched_at.date()

        filer_name = row.get("filer_name", "").strip()
        contributor_name = row.get("contributor_name", "").strip()
        if not filer_name or not contributor_name:
            return None

        from cls_pdx1.models import Jurisdiction, _make_id

        official_id = _make_id("official", filer_name, "candidate", str(int(Jurisdiction.STATE_OREGON)))
        entity_id = _make_id("entity", contributor_name)

        return Affiliation(
            official_id=official_id,
            entity_id=entity_id,
            edge_type=EdgeType.DONATION,
            confidence=ConfidenceTier.HARD_RECORD,
            observed_at=fetched_at,
            valid_from=txn_date,
            amount=amount,
            description=f"ORESTAR: {contributor_name} → {filer_name} (${amount:,.2f})",
            provenance=Provenance(
                source_uri=_SOURCE_URI_BASE,
                source_name="ORESTAR",
                fetched_at=fetched_at,
            ),
        )
    except Exception as exc:
        logger.debug("ORESTAR row parse error: %s — row: %s", exc, row)
        return None


def _current_year() -> int:
    return datetime.now(timezone.utc).year


class OrestarAdapter(BaseAdapter):
    """Parses ORESTAR campaign finance records.

    Fetch priority:
      1. Local CSV path (fastest, for pre-downloaded files)
      2. Live HTTP bulk ZIP → writes cache on success
      3. Cached last-good CSV → if live fails
    """

    source_name = "ORESTAR"

    def __init__(
        self,
        csv_path: Optional[Union[str, Path]] = None,
        year: Optional[int] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._csv_path = Path(csv_path) if csv_path else None
        self._year = year or _current_year()
        self._cache_dir = cache_dir or Path("cache/pdx1")

    def _cache_path(self) -> Path:
        return self._cache_dir / f"orestar_{self._year}.csv"

    def _write_cache(self, csv_text: str) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path().write_text(csv_text, encoding="utf-8")
        except OSError as exc:
            logger.warning("ORESTAR: cache write failed: %s", exc)

    def _read_cache(self) -> Optional[str]:
        path = self._cache_path()
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("ORESTAR: cache read failed: %s", exc)
            return None

    def fetch(self) -> AdapterResult:
        if self._csv_path is not None:
            return self._parse_local()
        return self._fetch_with_fallback()

    def _parse_local(self) -> AdapterResult:
        if not self._csv_path or not self._csv_path.exists():
            return AdapterResult(
                source_name=self.source_name,
                errors=[f"CSV not found: {self._csv_path}"],
            )
        fetched_at = _now()
        records: list[Affiliation] = []
        errors: list[str] = []
        try:
            with self._csv_path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    aff = _parse_row(row, fetched_at)
                    if aff:
                        records.append(aff)
        except Exception as exc:
            errors.append(f"ORESTAR CSV read error: {exc}")
        logger.info("ORESTAR: parsed %d affiliations, %d errors", len(records), len(errors))
        return AdapterResult(records=records, errors=errors, source_name=self.source_name)

    def _fetch_with_fallback(self) -> AdapterResult:
        url = _BULK_URL_TEMPLATE.format(year=self._year)
        logger.info("ORESTAR: downloading bulk export from %s", url)
        fetch_error: Optional[str] = None
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, stream=True)
            resp.raise_for_status()
            raw_bytes = resp.content

            try:
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                    csv_name = next(
                        (n for n in zf.namelist() if n.lower().endswith(".csv")), None
                    )
                    if not csv_name:
                        return AdapterResult(
                            source_name=self.source_name,
                            errors=["ORESTAR ZIP contained no CSV file"],
                        )
                    csv_text = zf.read(csv_name).decode("utf-8-sig")
            except zipfile.BadZipFile:
                csv_text = raw_bytes.decode("utf-8-sig")

            self._write_cache(csv_text)
            return self.fetch_from_csv_text(csv_text)

        except requests.RequestException as exc:
            fetch_error = str(exc)
            logger.warning("ORESTAR HTTP fetch failed: %s — trying cache", fetch_error)

        cached = self._read_cache()
        if cached is not None:
            logger.info("ORESTAR: using cached data")
            result = self.fetch_from_csv_text(cached)
            result.errors.insert(0, f"ORESTAR live fetch failed ({fetch_error}); serving cached data")
            return result

        return AdapterResult(
            source_name=self.source_name,
            errors=[f"ORESTAR HTTP error: {fetch_error}; no cache available"],
        )

    def fetch_from_csv_text(self, csv_text: str) -> AdapterResult:
        """Parse from in-memory CSV text (for testing)."""
        fetched_at = _now()
        records: list[Affiliation] = []
        errors: list[str] = []
        try:
            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                aff = _parse_row(row, fetched_at)
                if aff:
                    records.append(aff)
        except Exception as exc:
            errors.append(f"CSV parse error: {exc}")
        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
