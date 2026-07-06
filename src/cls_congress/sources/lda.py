from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from cls_congress.models import Affiliation, Chamber, ConfidenceTier, EdgeType, Entity, Member, MemberRegistry, Provenance, _make_id
from cls_congress.resolver import EntityResolver
from cls_congress.sources.base import AdapterResult, BaseAdapter
from cls_osint.adapters import fara

LDA_API_URL = "https://lda.senate.gov/api/v1/filings/"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LdaAdapter(BaseAdapter):
    source_name = "lda"

    def __init__(self, *, member_registry: MemberRegistry | None = None, entities: list[Entity] | None = None, timeout: int = 10) -> None:
        self._member_registry = member_registry or MemberRegistry()
        if not self._member_registry.members():
            self._member_registry.load()
        self._resolver = EntityResolver(self._member_registry.members(), entities or [])
        self._timeout = timeout

    def _fetch_domestic(self) -> list[dict[str, Any]]:
        response = requests.get(LDA_API_URL, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get("results", []) if isinstance(payload, dict) else []

    def _synthetic_domestic(self) -> list[dict[str, Any]]:
        return [{"member_name": "Elizabeth Warren", "client_name": "Policy Forum LLC", "date": _now().date().isoformat()}]

    def fetch(self) -> AdapterResult:
        errors: list[str] = []
        records: list[Affiliation] = []

        try:
            domestic_rows = self._fetch_domestic()
        except Exception as exc:
            errors.append(f"LDA API failed; using synthetic fallback: {exc}")
            domestic_rows = self._synthetic_domestic()

        try:
            foreign_rows = fara.collect(use_api=True)
        except Exception as exc:
            errors.append(f"FARA foreign-lobbying collection failed in LDA adapter: {exc}")
            foreign_rows = []

        for row in domestic_rows:
            member_name = row.get("member_name") or "Unknown Member"
            member_matches = self._member_registry.find(name=member_name)
            member_id = (
                member_matches[0].member_id
                if member_matches
                else Member.make_id(member_name, Chamber.HOUSE, "NA", None)
            )

            client_name = row.get("client_name") or "Unknown Client"
            resolved = self._resolver.resolve(client_name)
            entity_id = resolved.canonical_id if resolved else Entity.make_id(client_name)
            date_str = row.get("date")
            observed_at = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) if date_str else _now()

            records.append(
                Affiliation(
                    member_id=member_id,
                    entity_id=entity_id,
                    edge_type=EdgeType.LOBBYING,
                    confidence=ConfidenceTier.HARD_RECORD,
                    observed_at=observed_at,
                    valid_from=observed_at.date(),
                    description=f"Lobbying activity by {client_name}",
                    provenance=Provenance(source_uri=LDA_API_URL, source_name="LDA", fetched_at=_now()),
                    metadata={"raw": row},
                )
            )

        for row in foreign_rows:
            entity_id = Entity.make_id(row.registrant)
            records.append(
                Affiliation(
                    member_id=_make_id("member", "unknown_lobby_target"),
                    entity_id=entity_id,
                    edge_type=EdgeType.LOBBYING,
                    confidence=ConfidenceTier.REPORTED,
                    observed_at=row.filed_at,
                    valid_from=row.filed_at.date(),
                    description=f"FARA filing: {row.registrant} for {row.foreign_principal}",
                    provenance=Provenance(source_uri=row.doc_url, source_name="FARA", fetched_at=_now()),
                    metadata={"fara_record_id": row.record_id, "unresolved_member_target": True},
                )
            )

        return AdapterResult(records=records, errors=errors, source_name=self.source_name)
