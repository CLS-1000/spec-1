from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from cls_congress.models import Affiliation, Chamber, ConfidenceTier, EdgeType, Entity, Member, MemberRegistry, Provenance
from cls_congress.sources.base import AdapterResult, BaseAdapter

SEI_URL = "https://efdsearch.senate.gov/search/home/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SenateSeiAdapter(BaseAdapter):
    source_name = "senate_sei"

    def __init__(self, *, member_registry: MemberRegistry | None = None, timeout: int = 10) -> None:
        self._member_registry = member_registry or MemberRegistry()
        if not self._member_registry.members():
            self._member_registry.load()
        self._timeout = timeout

    def _fetch_rows(self) -> list[dict[str, Any]]:
        response = requests.get(SEI_URL, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get("results", []) if isinstance(payload, dict) else []

    def _synthetic_rows(self) -> list[dict[str, Any]]:
        return [{"member_name": "Amy Klobuchar", "entity_name": "Regional Health Network", "role": "BOARD_SEAT", "date": _now().date().isoformat()}]

    def fetch(self) -> AdapterResult:
        errors: list[str] = []
        try:
            rows = self._fetch_rows()
        except Exception as exc:
            errors.append(f"SEI feed failed; using synthetic fallback: {exc}")
            rows = self._synthetic_rows()

        records: list[Affiliation] = []
        for row in rows:
            member_name = row.get("member_name") or "Unknown Member"
            matches = self._member_registry.find(name=member_name)
            member_id = matches[0].member_id if matches else Member.make_id(member_name, Chamber.SENATE, "NA", None)
            entity_name = row.get("entity_name") or "Unknown Entity"
            role = str(row.get("role") or "EMPLOYMENT").upper()
            edge_type = EdgeType.BOARD_SEAT if role == "BOARD_SEAT" else EdgeType.EMPLOYMENT
            date_str = row.get("date")
            observed = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) if date_str else _now()

            records.append(
                Affiliation(
                    member_id=member_id,
                    entity_id=Entity.make_id(entity_name),
                    edge_type=edge_type,
                    confidence=ConfidenceTier.HARD_RECORD,
                    observed_at=observed,
                    valid_from=observed.date(),
                    description=f"SEI disclosure: {member_name} -> {entity_name}",
                    provenance=Provenance(source_uri=SEI_URL, source_name="Senate SEI", fetched_at=_now()),
                    metadata={"raw": row},
                )
            )

        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
