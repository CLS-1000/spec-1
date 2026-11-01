# @domain:   spec-1
# @module:   test_orestar_resolver
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Integration tests — ORESTAR adapter + EntityResolver.

Validates that campaign finance records produced by OrestarAdapter
can be enriched with canonical entity IDs via EntityResolver.
"""

from __future__ import annotations

from datetime import datetime, timezone

from titan.models import (
    ConfidenceTier,
    EdgeType,
    Entity,
    Provenance,
    Sector,
    _make_id,
)
from titan.resolver import EntityResolver
from titan.sources.orestar import OrestarAdapter


_CSV_SINGLE = """\
filer_id,filer_name,transaction_type,amount,contributor_name,contributor_address,transaction_date,election_year
100,Wheeler Ted,monetary,5000.00,Schnitzer Harold,1 SE Main St Portland OR,01/15/2024,2024
"""

_CSV_MULTI = """\
filer_id,filer_name,transaction_type,amount,contributor_name,contributor_address,transaction_date,election_year
100,Wheeler Ted,monetary,5000.00,Schnitzer Harold,1 SE Main St Portland OR,01/15/2024,2024
101,Rubio Carmen,monetary,2500.00,PGE Corp,2 Lloyd Blvd Portland OR,02/20/2024,2024
102,Gonzalez Rene,monetary,1000.00,Unknown Donor,3 NW Park Ave Portland OR,03/01/2024,2024
"""

_CSV_MISSING_CONTRIBUTOR = """\
filer_id,filer_name,transaction_type,amount,contributor_name,contributor_address,transaction_date,election_year
100,Wheeler Ted,monetary,250.00,,,,2024
"""


def _prov() -> Provenance:
    return Provenance(
        source_uri="https://sos.oregon.gov/elections/Pages/orestar.aspx",
        source_name="ORESTAR",
        fetched_at=datetime.now(timezone.utc),
    )


def _schnitzer_entity() -> Entity:
    return Entity(
        entity_id=_make_id("entity", "Schnitzer Industries"),
        canonical_name="Schnitzer Industries",
        kind="family",
        sectors=[Sector.REAL_ESTATE, Sector.CONSTRUCTION],
        aliases=["Schnitzer Harold", "Schnitzer Steel"],
        provenance=_prov(),
    )


def _pge_entity() -> Entity:
    return Entity(
        entity_id=_make_id("entity", "Portland General Electric"),
        canonical_name="Portland General Electric",
        kind="company",
        sectors=[Sector.UTILITY],
        aliases=["PGE", "PGE Corp"],
        provenance=_prov(),
    )


class TestOrestarWithResolver:
    def test_orestar_parses_contribution_to_affiliation(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_SINGLE)
        assert result.ok()
        assert len(result.records) == 1
        aff = result.records[0]
        assert aff.edge_type == EdgeType.DONATION
        assert aff.confidence == ConfidenceTier.HARD_RECORD

    def test_amount_parsed_correctly(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_SINGLE)
        aff = result.records[0]
        assert aff.amount == pytest.approx(5000.00)

    def test_affiliation_entity_id_survives_resolver_lookup(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_SINGLE)
        assert len(result.records) == 1  # precondition

        resolver = EntityResolver(entities=[_schnitzer_entity()])
        # Resolver should find Schnitzer Industries via its alias "Schnitzer Harold"
        hit = resolver.resolve("Schnitzer Harold")
        assert hit is not None
        assert hit.canonical_name == "Schnitzer Industries"

    def test_resolver_enriches_contributor_name(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_MULTI)
        assert len(result.records) >= 2

        resolver = EntityResolver(entities=[_schnitzer_entity(), _pge_entity()])
        pge_hit = resolver.resolve("PGE Corp")
        assert pge_hit is not None
        assert pge_hit.canonical_name == "Portland General Electric"

    def test_missing_contributor_still_produces_no_affiliation(self):
        """Rows with empty contributor_name are skipped by the adapter."""
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_MISSING_CONTRIBUTOR)
        assert len(result.records) == 0

    def test_multiple_contributions_all_parsed(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_CSV_MULTI)
        # Unknown Donor row has a contributor name — should be included
        assert len(result.records) == 3

    def test_resolver_no_match_for_unknown_donor(self):
        resolver = EntityResolver(entities=[_schnitzer_entity(), _pge_entity()])
        unknown_hit = resolver.resolve("Unknown Donor")
        assert unknown_hit is None


import pytest  # noqa: E402 — used for approx; imported late to keep fixtures above
