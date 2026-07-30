# @domain:   citizens_source
# @module:   sources_sei
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""SEI adapter — Oregon Government Ethics Commission Statement of Economic Interest.

SEI filings disclose every official's employer, household income sources,
business interests, and gifts. Highest signal-per-dollar source.

Export: OGEC provides annual JSONL/CSV exports at:
https://www.oregon.gov/ogec/pages/sei.aspx

Provide jsonl_path or records list for offline/test use.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from cls_pdx1.models import Affiliation, ConfidenceTier, EdgeType, Jurisdiction, Provenance, _make_id
from cls_pdx1.sources.base import AdapterResult, BaseAdapter

logger = logging.getLogger(__name__)

_SOURCE_URI = "https://www.oregon.gov/ogec/pages/sei.aspx"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_interest(raw: dict[str, Any], fetched_at: datetime) -> list[Affiliation]:
    """Convert one SEI record into one or more Affiliation edges."""
    results: list[Affiliation] = []
    try:
        official_name = raw.get("official_name", raw.get("filer_name", "")).strip()
        role = raw.get("role", raw.get("position", "official")).strip()
        year = raw.get("year", fetched_at.year)
        source_url = raw.get("source_url", _SOURCE_URI)

        if not official_name:
            return results

        official_id = _make_id("official", official_name, role, str(int(Jurisdiction.STATE_OREGON)))
        prov = Provenance(
            source_uri=source_url if source_url.startswith("http") else _SOURCE_URI,
            source_name="OGEC-SEI",
            fetched_at=fetched_at,
        )

        for interest in raw.get("business_interests", []):
            entity_name = interest.get("entity_name", "").strip()
            if not entity_name:
                continue
            entity_id = _make_id("entity", entity_name)
            amount = float(interest.get("amount", 0.0) or 0.0)
            results.append(
                Affiliation(
                    official_id=official_id,
                    entity_id=entity_id,
                    edge_type=EdgeType.EMPLOYMENT,
                    confidence=ConfidenceTier.HARD_RECORD,
                    observed_at=fetched_at,
                    valid_from=date(int(year), 1, 1),
                    amount=amount if amount else None,
                    description=f"SEI business interest: {entity_name}",
                    provenance=prov,
                )
            )

        for gift in raw.get("gifts", []):
            donor_name = gift.get("donor", "").strip()
            if not donor_name:
                continue
            entity_id = _make_id("entity", donor_name)
            amount = float(gift.get("amount", 0.0) or 0.0)
            results.append(
                Affiliation(
                    official_id=official_id,
                    entity_id=entity_id,
                    edge_type=EdgeType.DONATION,
                    confidence=ConfidenceTier.HARD_RECORD,
                    observed_at=fetched_at,
                    valid_from=date(int(year), 1, 1),
                    amount=amount if amount else None,
                    description=f"SEI gift from {donor_name}",
                    provenance=prov,
                )
            )

    except Exception as exc:
        logger.debug("SEI parse error: %s — record: %s", exc, raw.get("official_name", "?"))
    return results


class SeiAdapter(BaseAdapter):
    """Parses OGEC SEI records from JSONL file or in-memory list."""

    source_name = "OGEC-SEI"

    def __init__(
        self,
        jsonl_path: Optional[Union[str, Path]] = None,
        records: Optional[list[dict]] = None,
    ) -> None:
        self._jsonl_path = Path(jsonl_path) if jsonl_path else None
        self._records = records

    def fetch(self) -> AdapterResult:
        if self._records is not None:
            return self._parse_list(self._records)

        if self._jsonl_path is not None:
            if not self._jsonl_path.exists():
                return AdapterResult(
                    source_name=self.source_name,
                    errors=[f"SEI JSONL not found: {self._jsonl_path}"],
                )
            return self._parse_jsonl(self._jsonl_path)

        return AdapterResult(
            source_name=self.source_name,
            errors=["SEI HTTP fetch not implemented — provide jsonl_path or records"],
        )

    def _parse_jsonl(self, path: Path) -> AdapterResult:
        fetched_at = _now()
        affiliations: list[Affiliation] = []
        errors: list[str] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    affiliations.extend(_parse_interest(raw, fetched_at))
                except Exception as exc:
                    errors.append(f"JSONL parse error: {exc}")
        logger.info("SEI: parsed %d affiliations, %d errors", len(affiliations), len(errors))
        return AdapterResult(records=affiliations, errors=errors, source_name=self.source_name)

    def _parse_list(self, records: list[dict]) -> AdapterResult:
        fetched_at = _now()
        affiliations: list[Affiliation] = []
        errors: list[str] = []
        for raw in records:
            try:
                affiliations.extend(_parse_interest(raw, fetched_at))
            except Exception as exc:
                errors.append(str(exc))
        return AdapterResult(records=affiliations, errors=errors, source_name=self.source_name)
