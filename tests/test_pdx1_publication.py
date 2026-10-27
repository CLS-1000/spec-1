# @domain:   spec-1
# @module:   test_pdx1_publication
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for cls_pdx1 publication layer."""

from __future__ import annotations

from datetime import datetime, timezone


from cls_pdx1.models import Anomaly, AnomalyTier, Issue, IssueSection, Provenance, Signal
from cls_pdx1.publication.builder import IssueBuilder
from cls_pdx1.publication.newsletter import to_markdown, write_markdown
from cls_pdx1.publication.diagram import build_graph_data, write_diagram
from cls_pdx1.models import (
    Affiliation, ConfidenceTier, EdgeType, Entity, Official,
    Jurisdiction, Sector,
)


def _now():
    return datetime.now(timezone.utc)


def _prov():
    return Provenance(source_uri="https://example.com/x", source_name="t", fetched_at=_now())


# ---------------------------------------------------------------------------
# IssueBuilder
# ---------------------------------------------------------------------------


class TestIssueBuilder:
    def test_clean_section_accepted(self):
        builder = IssueBuilder(issue_number=1)
        ok = builder.add_section(
            "City Council Budget Vote",
            "The council voted to approve the FY2025 budget.",
            "https://portland.gov/council/minutes",
        )
        assert ok
        assert builder.section_count() == 1

    def test_loaded_section_rejected(self):
        builder = IssueBuilder(issue_number=1)
        ok = builder.add_section(
            "Mayor Slammed by Critics",
            "The mayor admitted failure.",
            "https://portland.gov/",
        )
        assert not ok
        assert builder.section_count() == 0
        assert len(builder.rejected_sections()) == 1

    def test_missing_source_uri_rejected(self):
        builder = IssueBuilder(issue_number=1)
        ok = builder.add_section(
            "Title",
            "The council voted on the measure.",
            "",
        )
        assert not ok

    def test_build_returns_issue(self):
        builder = IssueBuilder(issue_number=3)
        builder.add_section("Title", "The city voted to proceed.", "https://portland.gov/")
        issue = builder.build("Test Issue")
        assert isinstance(issue, Issue)
        assert issue.issue_number == 3
        assert len(issue.sections) == 1

    def test_attach_signal(self):
        builder = IssueBuilder(issue_number=1)
        s = Signal(kind="x", occurred_at=_now(), detected_at=_now(), provenance=_prov())
        builder.attach_signal(s)
        issue = builder.build()
        assert s.signal_id in issue.signal_ids

    def test_attach_anomaly(self):
        builder = IssueBuilder(issue_number=1)
        a = Anomaly(
            entity_id="ent-1",
            tier=AnomalyTier.TIER_1,
            detected_at=_now(),
            kind="spike",
            description="x",
            provenance=_prov(),
        )
        builder.attach_anomaly(a)
        issue = builder.build()
        assert a.anomaly_id in issue.anomaly_ids

    def test_multiple_sections(self):
        builder = IssueBuilder(issue_number=2)
        for i in range(3):
            builder.add_section(
                f"Section {i}",
                "The council voted on the item.",
                f"https://portland.gov/item{i}",
            )
        assert builder.section_count() == 3


# ---------------------------------------------------------------------------
# Newsletter renderer
# ---------------------------------------------------------------------------


class TestNewsletterRenderer:
    def _issue(self):
        return Issue(
            issue_id=Issue.make_id(1, _now()),
            issue_number=1,
            title="Spring 2025 Update",
            published_at=_now(),
            sections=[
                IssueSection(
                    title="City Council Actions",
                    body="The council voted to approve the measure.",
                    source_uri="https://portland.gov/council",
                )
            ],
        )

    def test_markdown_contains_title(self):
        md = to_markdown(self._issue())
        assert "Metro Citizens Narrative" in md
        assert "Spring 2025 Update" in md

    def test_markdown_contains_section(self):
        md = to_markdown(self._issue())
        assert "City Council Actions" in md
        assert "council voted" in md

    def test_markdown_contains_source(self):
        md = to_markdown(self._issue())
        assert "portland.gov/council" in md

    def test_write_markdown_creates_file(self, tmp_path):
        path = write_markdown(self._issue(), tmp_path)
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text()
        assert "Metro Citizens Narrative" in content

    def test_empty_issue_markdown(self):
        empty = Issue(
            issue_id=Issue.make_id(2, _now()),
            issue_number=2,
            title="Empty",
            published_at=_now(),
        )
        md = to_markdown(empty)
        assert "No sections" in md


# ---------------------------------------------------------------------------
# Diagram exporter
# ---------------------------------------------------------------------------


class TestDiagramExporter:
    def _officials(self):
        return [
            Official(
                official_id=Official.make_id("Jane Doe", "Mayor", Jurisdiction.CITY_PORTLAND),
                name="Jane Doe",
                role="Mayor",
                jurisdiction=Jurisdiction.CITY_PORTLAND,
                provenance=_prov(),
            )
        ]

    def _entities(self):
        return [
            Entity(
                entity_id=Entity.make_id("Acme Corp"),
                canonical_name="Acme Corp",
                kind="company",
                sectors=[Sector.REAL_ESTATE],
                provenance=_prov(),
            )
        ]

    def _affiliations(self, official, entity):
        from datetime import date
        return [
            Affiliation(
                official_id=official.official_id,
                entity_id=entity.entity_id,
                edge_type=EdgeType.DONATION,
                confidence=ConfidenceTier.HARD_RECORD,
                observed_at=_now(),
                valid_from=date(2024, 1, 1),
                provenance=_prov(),
            )
        ]

    def test_graph_data_has_nodes_and_links(self):
        officials = self._officials()
        entities = self._entities()
        affs = self._affiliations(officials[0], entities[0])
        data = build_graph_data(officials, entities, affs)
        assert len(data["nodes"]) == 2
        assert len(data["links"]) == 1

    def test_node_has_required_fields(self):
        officials = self._officials()
        data = build_graph_data(officials, [], [])
        node = data["nodes"][0]
        assert "id" in node
        assert "label" in node
        assert "colour" in node

    def test_link_has_colour(self):
        officials = self._officials()
        entities = self._entities()
        affs = self._affiliations(officials[0], entities[0])
        data = build_graph_data(officials, entities, affs)
        link = data["links"][0]
        assert "colour" in link

    def test_write_diagram_creates_html(self, tmp_path):
        officials = self._officials()
        entities = self._entities()
        affs = self._affiliations(officials[0], entities[0])
        path = write_diagram(officials, entities, affs, tmp_path)
        assert path.exists()
        assert path.suffix == ".html"
        content = path.read_text()
        assert "d3" in content.lower()
        assert "Jane Doe" in content

    def test_empty_graph_still_renders(self, tmp_path):
        path = write_diagram([], [], [], tmp_path)
        assert path.exists()
