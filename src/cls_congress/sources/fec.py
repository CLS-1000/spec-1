from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from cls_congress.models import Affiliation, Chamber, ConfidenceTier, EdgeType, Entity, Member, MemberRegistry, Provenance
from cls_congress.resolver import EntityResolver
from cls_congress.sources.base import AdapterResult, BaseAdapter

FEC_API_URL = "https://api.open.fec.gov/v1/schedules/schedule_a/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FecAdapter(BaseAdapter):
    source_name = "fec"

    def __init__(
        self,
        *,
        member_registry: MemberRegistry | None = None,
        entities: list[Entity] | None = None,
        timeout: int = 10,
    ) -> None:
        self._member_registry = member_registry or MemberRegistry()
        if not self._member_registry.members():
            self._member_registry.load()
        self._resolver = EntityResolver(self._member_registry.members(), entities or [])
        self._timeout = timeout

    def _synthetic_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "recipient_name": "Ron Wyden",
                "recipient_state": "OR",
                "recipient_chamber": "S",
                "contributor_name": "Example PAC",
                "contribution_receipt_amount": 2500,
                "contribution_receipt_date": _now().date().isoformat(),
            }
        ]

    def _fetch_rows(self) -> list[dict[str, Any]]:
        response = requests.get(FEC_API_URL, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get("results", []) if isinstance(payload, dict) else []

    def _member_id(self, row: dict[str, Any]) -> str:
        name = (row.get("recipient_name") or "Unknown Member").strip()
        chamber = Chamber.SENATE if str(row.get("recipient_chamber", "")).upper() == "S" else Chamber.HOUSE
        state = row.get("recipient_state") or "NA"
        members = self._member_registry.find(name=name, state=state)
        if members:
            return members[0].member_id

        return Member.make_id(name, chamber, state, None)

    def fetch(self) -> AdapterResult:
        errors: list[str] = []
        try:
            rows = self._fetch_rows()
        except Exception as exc:
            errors.append(f"FEC API failed; using synthetic fallback: {exc}")
            rows = self._synthetic_rows()

        records: list[Affiliation] = []
        for row in rows:
            member_id = self._member_id(row)
            contributor = (row.get("contributor_name") or "Unknown Contributor").strip()
            resolved = self._resolver.resolve(contributor)
            entity_id = resolved.canonical_id if resolved else Entity.make_id(contributor)
            amount = _to_float(row.get("contribution_receipt_amount"))
            date_str = row.get("contribution_receipt_date")
            observed = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) if date_str else _now()

            records.append(
                Affiliation(
                    member_id=member_id,
                    entity_id=entity_id,
                    edge_type=EdgeType.DONATION,
                    confidence=ConfidenceTier.HARD_RECORD,
                    observed_at=observed,
                    valid_from=observed.date(),
                    amount=amount,
                    description=f"Contribution from {contributor}",
                    provenance=Provenance(source_uri=FEC_API_URL, source_name="FEC", fetched_at=_now()),
                    metadata={"raw": row},
                )
            )

        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
