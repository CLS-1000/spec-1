# @domain:   publisher
# @module:   test_weekly_brief
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Tests for cls_weekly_brief module."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from cls_weekly_brief import (
    EvidenceTier,
    EvidenceItem,
    WeeklySection,
    PublicWeeklyBrief,
    produce_weekly_brief,
    to_markdown,
    to_json_summary,
    to_full_json,
    WeeklyBriefStore,
)


class TestEvidenceItem:
    def test_evidence_item_creation(self):
        item = EvidenceItem(
            content="Test evidence",
            tier=EvidenceTier.VERIFIED,
            confidence=0.95,
            source_ids=["rec_123"],
        )
        assert item.content == "Test evidence"
        assert item.tier == EvidenceTier.VERIFIED
        assert item.confidence == 0.95

    def test_evidence_item_to_dict(self):
        item = EvidenceItem(
            content="Test",
            tier=EvidenceTier.INFERRED,
            source_ids=["id1", "id2"],
            confidence=0.7,
        )
        d = item.to_dict()
        assert d["content"] == "Test"
        assert d["tier"] == "INFERRED"
        assert d["confidence"] == 0.7


class TestWeeklySection:
    def test_weekly_section_creation(self):
        section = WeeklySection(
            title="Military Intelligence",
            category="MILITARY",
        )
        assert section.title == "Military Intelligence"
        assert section.category == "MILITARY"
        assert len(section.verified_items) == 0

    def test_weekly_section_with_items(self):
        item = EvidenceItem("Test", tier=EvidenceTier.VERIFIED)
        section = WeeklySection(
            title="Test Section",
            category="TEST",
            verified_items=[item],
        )
        assert len(section.verified_items) == 1
        assert section.verified_items[0].content == "Test"

    def test_weekly_section_to_dict(self):
        item = EvidenceItem("Test", tier=EvidenceTier.VERIFIED)
        section = WeeklySection(
            title="Test",
            category="TEST",
            verified_items=[item],
        )
        d = section.to_dict()
        assert d["title"] == "Test"
        assert len(d["verified_items"]) == 1


class TestPublicWeeklyBrief:
    def test_brief_creation(self):
        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Test summary",
            methodology_note="Test methodology",
        )
        assert brief.week_id == "2026-W34"
        assert brief.records_analyzed == 0

    def test_brief_make_id(self):
        brief_id = PublicWeeklyBrief.make_id("2026-W34")
        assert brief_id.startswith("pwb_")
        assert len(brief_id) == 16  # pwb_ + 12 hex chars

    def test_brief_to_dict(self):
        brief = PublicWeeklyBrief(
            brief_id="pwb_123",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Test",
            methodology_note="Methodology",
            records_analyzed=10,
        )
        d = brief.to_dict()
        assert d["brief_id"] == "pwb_123"
        assert d["records_analyzed"] == 10
        assert "produced_at" in d


class TestProduceWeeklyBrief:
    def test_produce_brief_no_records(self):
        brief = produce_weekly_brief([])
        assert brief.records_analyzed == 0
        assert brief.verified_count == 0
        assert brief.inferred_count == 0
        assert brief.speculation_count == 0

    def test_produce_brief_with_verified_records(self):
        now = datetime.now(timezone.utc)
        records = [
            {
                "record_id": "rec_1",
                "pattern": "Military activity detected",
                "classification": "CORROBORATED",
                "confidence": 0.95,
                "source_weight": 0.8,
                "written_at": now.isoformat(),
                "keywords": ["military", "defense"],
            }
        ]
        brief = produce_weekly_brief(records, week_id="2026-W34")
        assert brief.records_analyzed == 1
        assert brief.verified_count == 1

    def test_produce_brief_with_inferred_records(self):
        now = datetime.now(timezone.utc)
        records = [
            {
                "record_id": "rec_2",
                "pattern": "Possible activity",
                "classification": "MONITOR",
                "confidence": 0.75,
                "source_weight": 0.65,
                "written_at": now.isoformat(),
            }
        ]
        brief = produce_weekly_brief(records, week_id="2026-W34")
        assert brief.records_analyzed == 1
        assert brief.inferred_count == 1

    def test_produce_brief_categorization(self):
        now = datetime.now(timezone.utc)
        records = [
            {
                "record_id": "rec_military",
                "pattern": "Military deployment",
                "classification": "CORROBORATED",
                "confidence": 0.9,
                "source_weight": 0.8,
                "written_at": now.isoformat(),
                "keywords": ["military", "army"],
            },
            {
                "record_id": "rec_cyber",
                "pattern": "Cyber attack detected",
                "classification": "CORROBORATED",
                "confidence": 0.9,
                "source_weight": 0.8,
                "written_at": now.isoformat(),
                "keywords": ["cyber", "hack"],
            },
        ]
        brief = produce_weekly_brief(records, week_id="2026-W34")
        assert brief.records_analyzed == 2
        assert len(brief.sections) == 2

    def test_week_id_inference(self):
        now = datetime.now(timezone.utc)
        records = [
            {
                "record_id": "rec",
                "pattern": "Test",
                "written_at": now.isoformat(),
            }
        ]
        brief = produce_weekly_brief(records)
        assert brief.week_id is not None
        assert "W" in brief.week_id


class TestFormatters:
    def test_to_markdown_basic(self):
        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Test summary",
            methodology_note="Test methodology",
        )
        md = to_markdown(brief)
        assert "SPEC-1 Public Weekly Intelligence Brief" in md
        assert "2026-W34" in md
        assert "Test summary" in md
        assert "Test methodology" in md

    def test_to_markdown_with_sections(self):
        item = EvidenceItem("Test evidence", tier=EvidenceTier.VERIFIED, confidence=0.9)
        section = WeeklySection(
            title="Test Section",
            category="TEST",
            verified_items=[item],
        )
        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
            sections=[section],
        )
        md = to_markdown(brief)
        assert "Test Section" in md
        assert "Test evidence" in md
        assert "VERIFIED" in md or "✓" in md

    def test_to_json_summary(self):
        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
            records_analyzed=5,
            verified_count=3,
            inferred_count=2,
        )
        summary = to_json_summary(brief)
        assert summary["brief_id"] == "pwb_test"
        assert summary["records_analyzed"] == 5
        assert summary["verified_count"] == 3

    def test_to_full_json(self):
        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
        )
        full = to_full_json(brief)
        assert full["brief_id"] == "pwb_test"
        assert "sections" in full


class TestWeeklyBriefStore:
    def test_store_creation(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)
        assert not store_path.exists()

    def test_store_save_and_read(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)

        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
        )
        entry = store.save(brief, write_markdown=False)

        assert store_path.exists()
        assert entry["brief_id"] == "pwb_test"
        assert "written_at" in entry

    def test_store_read_all(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)

        for i in range(3):
            brief = PublicWeeklyBrief(
                brief_id=f"pwb_{i}",
                week_id=f"2026-W{30+i:02d}",
                week_start="2026-08-18",
                week_end="2026-08-25",
                executive_summary="Summary",
                methodology_note="Methods",
            )
            store.save(brief, write_markdown=False)

        all_briefs = list(store.read_all())
        assert len(all_briefs) == 3

    def test_store_latest(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)

        brief1 = PublicWeeklyBrief(
            brief_id="pwb_1",
            week_id="2026-W33",
            week_start="2026-08-11",
            week_end="2026-08-18",
            executive_summary="Summary 1",
            methodology_note="Methods",
        )
        store.save(brief1, write_markdown=False)

        brief2 = PublicWeeklyBrief(
            brief_id="pwb_2",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary 2",
            methodology_note="Methods",
        )
        store.save(brief2, write_markdown=False)

        latest = store.latest()
        assert latest is not None
        assert latest["brief_id"] == "pwb_2"

    def test_store_get_by_week_id(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)

        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
        )
        store.save(brief, write_markdown=False)

        found = store.get_by_week_id("2026-W34")
        assert found is not None
        assert found["brief_id"] == "pwb_test"

        not_found = store.get_by_week_id("2026-W99")
        assert not_found is None

    def test_store_write_markdown(self, tmp_path: Path):
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)

        brief = PublicWeeklyBrief(
            brief_id="pwb_test",
            week_id="2026-W34",
            week_start="2026-08-18",
            week_end="2026-08-25",
            executive_summary="Summary",
            methodology_note="Methods",
        )
        store.save(brief, write_markdown=True)

        md_dir = store_path.parent / "markdown"
        assert md_dir.exists()
        md_file = md_dir / "weekly_2026-W34.md"
        assert md_file.exists()

        md_content = md_file.read_text()
        assert "SPEC-1 Public Weekly Intelligence Brief" in md_content


class TestIntegration:
    def test_full_workflow(self, tmp_path: Path):
        # Create some test records
        now = datetime.now(timezone.utc)
        records = [
            {
                "record_id": "rec_1",
                "pattern": "Military activity",
                "classification": "CORROBORATED",
                "confidence": 0.9,
                "source_weight": 0.8,
                "written_at": now.isoformat(),
                "keywords": ["military"],
            },
            {
                "record_id": "rec_2",
                "pattern": "Cyber incident",
                "classification": "ESCALATE",
                "confidence": 0.8,
                "source_weight": 0.75,
                "written_at": now.isoformat(),
                "keywords": ["cyber"],
            },
        ]

        # Produce brief
        brief = produce_weekly_brief(records, week_id="2026-W34")

        # Store and retrieve
        store_path = tmp_path / "weekly_briefs.jsonl"
        store = WeeklyBriefStore(store_path)
        store.save(brief, write_markdown=True)

        retrieved = store.get_by_week_id("2026-W34")
        assert retrieved is not None
        assert retrieved["records_analyzed"] == 2

        # Format
        md = to_markdown(brief)
        assert len(md) > 0
        assert "Military" in md or "military" in md.lower()
