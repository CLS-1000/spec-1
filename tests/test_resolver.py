# @domain:   spec-1
# @module:   test_resolver
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.resolver — EntityResolver name resolution."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from titan.models import (
    Entity,
    Jurisdiction,
    Official,
    Provenance,
    Sector,
    _make_id,
)
from titan.resolver import EntityResolver


def _prov() -> Provenance:
    return Provenance(
        source_uri="https://example.gov/",
        source_name="fixture",
        fetched_at=datetime.now(timezone.utc),
    )


def _official(name: str, role: str = "Commissioner") -> Official:
    return Official(
        official_id=_make_id("official", name, role, str(int(Jurisdiction.CITY_PORTLAND))),
        name=name,
        role=role,
        jurisdiction=Jurisdiction.CITY_PORTLAND,
        provenance=_prov(),
    )


def _entity(canonical: str, aliases: list | None = None) -> Entity:
    return Entity(
        entity_id=_make_id("entity", canonical),
        canonical_name=canonical,
        kind="company",
        sectors=[Sector.REAL_ESTATE],
        aliases=aliases or [],
        provenance=_prov(),
    )


class TestEntityResolver:
    def test_exact_match(self):
        resolver = EntityResolver(officials=[_official("Ted Wheeler")])
        result = resolver.resolve("Ted Wheeler")
        assert result is not None
        assert result.canonical_name == "Ted Wheeler"
        assert result.kind == "official"

    def test_case_insensitive_match(self):
        resolver = EntityResolver(officials=[_official("Ted Wheeler")])
        result = resolver.resolve("ted wheeler")
        assert result is not None
        assert result.canonical_name == "Ted Wheeler"

    def test_no_match_returns_none(self):
        resolver = EntityResolver(officials=[_official("Ted Wheeler")])
        result = resolver.resolve("Unknown Person XYZ")
        assert result is None

    def test_confidence_exact_is_one(self):
        resolver = EntityResolver(officials=[_official("Carmen Rubio")])
        result = resolver.resolve("Carmen Rubio")
        assert result is not None
        assert result.confidence == 1.0

    def test_token_sort_match(self):
        resolver = EntityResolver(officials=[_official("Rene Gonzalez")])
        result = resolver.resolve("Gonzalez Rene")
        assert result is not None
        assert result.confidence == pytest.approx(0.9)

    def test_entity_resolved_by_canonical_name(self):
        resolver = EntityResolver(entities=[_entity("Schnitzer Industries")])
        result = resolver.resolve("Schnitzer Industries")
        assert result is not None
        assert result.kind == "entity"
        assert result.canonical_id == _make_id("entity", "Schnitzer Industries")

    def test_entity_resolved_by_alias(self):
        resolver = EntityResolver(
            entities=[_entity("Portland General Electric", aliases=["PGE", "PGE Corp"])]
        )
        result = resolver.resolve("PGE")
        assert result is not None
        assert result.canonical_name == "Portland General Electric"

    def test_ambiguous_prefers_highest_confidence(self):
        ent_exact = _entity("NW Natural Gas", aliases=["NW Natural"])
        ent_fuzzy = _entity("Northwest Natural Resources")
        resolver = EntityResolver(entities=[ent_exact, ent_fuzzy])
        result = resolver.resolve("NW Natural")
        assert result is not None
        assert result.canonical_name == "NW Natural Gas"
        assert result.confidence == 1.0

    def test_empty_name_returns_none(self):
        resolver = EntityResolver(officials=[_official("Ted Wheeler")])
        assert resolver.resolve("") is None
        assert resolver.resolve("   ") is None

    def test_resolve_all_drops_non_matches(self):
        resolver = EntityResolver(
            officials=[_official("Ted Wheeler"), _official("Carmen Rubio")]
        )
        results = resolver.resolve_all(["Ted Wheeler", "Unknown", "Carmen Rubio"])
        assert len(results) == 2
        names = {r.canonical_name for r in results}
        assert "Ted Wheeler" in names
        assert "Carmen Rubio" in names

    def test_size_counts_unique_records(self):
        resolver = EntityResolver(
            officials=[_official("A"), _official("B")],
            entities=[_entity("Corp X")],
        )
        assert resolver.size() == 3

    def test_reload_replaces_index(self):
        resolver = EntityResolver(officials=[_official("Ted Wheeler")])
        resolver.reload(officials=[_official("Carmen Rubio")], entities=[])
        assert resolver.resolve("Ted Wheeler") is None
        assert resolver.resolve("Carmen Rubio") is not None
