# @domain:   publisher
# @module:   test_leads
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for cls_leads — lead generator, formatter, store."""

from __future__ import annotations

from datetime import datetime, timezone


from cls_leads.schemas import Lead
from cls_leads.generator import generate_leads, _score_record, _build_action_items
from cls_leads.formatter import lead_to_text, leads_to_text, lead_to_markdown, leads_to_markdown, leads_to_json
from cls_leads.store import LeadStore
from spec1_labels import PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM


def _make_lead(
    lead_id="lead_001",
    title="Test lead",
    summary="Test summary",
    priority="HIGH",
    category="MILITARY",
    confidence=0.75,
):
    return Lead(
        lead_id=lead_id,
        title=title,
        summary=summary,
        priority=priority,
        category=category,
        confidence=confidence,
        generated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )


def _make_intel_record(content="Defense activity detected", confidence=0.8):
    return {
        "record_id": "intel_001",
        "pattern": content,
        "content": content,
        "classification": "CORROBORATED",
        "confidence": confidence,
        "source_type": "rss",
    }


class TestLeadSchema:
    def test_to_dict_has_required_fields(self):
        lead = _make_lead()
        d = lead.to_dict()
        assert d["lead_id"] == "lead_001"
        assert d["priority"] == "HIGH"
        assert d["category"] == "MILITARY"
        assert d["confidence"] == 0.75

    def test_make_id_is_deterministic(self):
        now = "2024-01-15T10:00:00Z"
        id1 = Lead.make_id("Test title", now)
        id2 = Lead.make_id("Test title", now)
        assert id1 == id2
        assert id1.startswith("lead_")

    def test_make_id_differs_by_title(self):
        now = "2024-01-15T10:00:00Z"
        assert Lead.make_id("Title A", now) != Lead.make_id("Title B", now)


class TestScoreRecord:
    def test_nuclear_is_critical(self):
        priority, category = _score_record("Nuclear threat detected with WMD capabilities")
        assert priority == PRIORITY_CRITICAL

    def test_invasion_is_critical(self):
        priority, category = _score_record("Invasion forces crossed border with airstrike support")
        assert priority == PRIORITY_CRITICAL

    def test_cyber_is_high(self):
        priority, category = _score_record("APT41 breach of critical infrastructure")
        assert priority == PRIORITY_HIGH
        assert category == "CYBER"

    def test_fara_is_high(self):
        priority, category = _score_record("FARA filing for undisclosed foreign agent lobbying")
        assert priority == PRIORITY_HIGH
        assert category == "FARA"

    def test_psyop_is_high(self):
        priority, category = _score_record("Influence operation disinformation campaign detected")
        assert priority == PRIORITY_HIGH
        assert category == "PSYOP"

    def test_military_exercise_is_medium(self):
        priority, category = _score_record("Military exercise and joint drill scheduled in Pacific")
        assert priority == PRIORITY_MEDIUM

    def test_default_is_low(self):
        priority, category = _score_record("General intelligence assessment published")
        assert priority == PRIORITY_LOW


class TestBuildActionItems:
    def test_critical_has_escalate_action(self):
        actions = _build_action_items(PRIORITY_CRITICAL, "MILITARY", "nuclear threat")
        assert any("Escalate" in a for a in actions)

    def test_high_has_review_action(self):
        actions = _build_action_items(PRIORITY_HIGH, "CYBER", "breach detected")
        assert any("verify" in a.lower() or "review" in a.lower() for a in actions)

    def test_cyber_category_has_soc_action(self):
        actions = _build_action_items(PRIORITY_HIGH, "CYBER", "hack")
        assert any("SOC" in a for a in actions)

    def test_fara_category_has_fara_action(self):
        actions = _build_action_items(PRIORITY_HIGH, "FARA", "fara filing")
        assert any("FARA" in a for a in actions)


class TestGenerateLeads:
    def test_generates_leads_from_records(self):
        records = [
            _make_intel_record("Nuclear threat detected WMD capabilities"),
            _make_intel_record("APT41 cyber espionage critical infrastructure breach"),
            _make_intel_record("Military troop deployment escalation"),
        ]
        leads = generate_leads(records)
        assert len(leads) >= 1
        assert all(isinstance(l, Lead) for l in leads)

    def test_sorted_by_priority(self):
        records = [
            _make_intel_record("Military exercise joint drill", confidence=0.6),
            _make_intel_record("Nuclear threat WMD detected", confidence=0.9),
        ]
        leads = generate_leads(records)
        priorities = [l.priority for l in leads]
        priority_order = {
            PRIORITY_CRITICAL: 0,
            PRIORITY_HIGH: 1,
            PRIORITY_MEDIUM: 2,
            PRIORITY_LOW: 3,
        }
        values = [priority_order[p] for p in priorities]
        assert values == sorted(values)

    def test_respects_min_confidence(self):
        records = [
            _make_intel_record("Nuclear threat", confidence=0.9),
            _make_intel_record("Minor report", confidence=0.1),
        ]
        leads = generate_leads(records, min_confidence=0.5)
        assert all(l.confidence >= 0.5 for l in leads)

    def test_respects_max_leads(self):
        records = [_make_intel_record(f"Content {i}") for i in range(20)]
        leads = generate_leads(records, max_leads=5)
        assert len(leads) <= 5

    def test_skips_records_without_content(self):
        records = [{"record_id": "empty", "confidence": 0.9}]
        leads = generate_leads(records)
        assert leads == []

    def test_populates_source_record_ids(self):
        records = [{"record_id": "intel_x", "content": "nuclear threat WMD", "confidence": 0.9}]
        leads = generate_leads(records)
        assert len(leads) >= 1
        assert "intel_x" in leads[0].source_record_ids


class TestLeadFormatter:
    def test_lead_to_text_contains_title(self):
        lead = _make_lead(title="Critical nuclear threat detected")
        text = lead_to_text(lead)
        assert "Critical nuclear threat detected" in text

    def test_lead_to_text_shows_priority(self):
        lead = _make_lead(priority="CRITICAL")
        text = lead_to_text(lead)
        assert "CRITICAL" in text

    def test_leads_to_text_header(self):
        leads = [_make_lead(), _make_lead(lead_id="lead_002", title="Second lead")]
        text = leads_to_text(leads)
        assert "SPEC-1 INTELLIGENCE LEADS" in text
        assert "2 item" in text

    def test_leads_to_text_empty(self):
        text = leads_to_text([])
        assert "No actionable leads" in text

    def test_lead_to_markdown_contains_table(self):
        lead = _make_lead()
        md = lead_to_markdown(lead)
        assert "|" in md
        assert "Priority" in md

    def test_leads_to_markdown_header(self):
        leads = [_make_lead()]
        md = leads_to_markdown(leads)
        assert "# SPEC-1 Intelligence Leads" in md

    def test_leads_to_json_returns_list(self):
        leads = [_make_lead(), _make_lead(lead_id="lead_002")]
        result = leads_to_json(leads)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all("lead_id" in r for r in result)


class TestLeadStore:
    def test_save_and_read_back(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        lead = _make_lead()
        store.save(lead)

        records = list(store.read_all())
        assert len(records) == 1
        assert records[0]["lead_id"] == "lead_001"

    def test_save_batch(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        leads = [_make_lead(lead_id=f"lead_{i:03d}") for i in range(5)]
        store.save_batch(leads)
        assert store.count() == 5

    def test_by_priority_filter(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        store.save(_make_lead(lead_id="l1", priority="HIGH"))
        store.save(_make_lead(lead_id="l2", priority="MEDIUM"))
        store.save(_make_lead(lead_id="l3", priority="HIGH"))

        high = list(store.by_priority("HIGH"))
        assert len(high) == 2

    def test_by_category_filter(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        store.save(_make_lead(lead_id="l1", category="CYBER"))
        store.save(_make_lead(lead_id="l2", category="MILITARY"))

        cyber = list(store.by_category("CYBER"))
        assert len(cyber) == 1

    def test_latest_returns_last_n(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        for i in range(10):
            store.save(_make_lead(lead_id=f"lead_{i:03d}"))
        latest = store.latest(3)
        assert len(latest) == 3

    def test_clear(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        store.save(_make_lead())
        store.clear()
        assert store.count() == 0

    def test_empty_store_count_zero(self, tmp_path):
        store = LeadStore(tmp_path / "empty.jsonl")
        assert store.count() == 0


class TestLeadStoreDualWrite:
    def test_dual_write_persists_to_both_backends(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema
        from cls_db.repository import Repository

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)

        lead = _make_lead(lead_id="l_dw_001")
        store.save(lead)

        # JSONL has it
        jsonl_rows = list(store.read_all())
        assert len(jsonl_rows) == 1
        assert jsonl_rows[0]["lead_id"] == "l_dw_001"

        # SQLite has it too
        repo = Repository(db, "leads", pk_field="lead_id")
        db_rows = repo.all()
        assert len(db_rows) == 1
        assert db_rows[0]["lead_id"] == "l_dw_001"

    def test_dual_write_batch(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema
        from cls_db.repository import Repository

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)

        leads = [_make_lead(lead_id=f"l_batch_{i:03d}") for i in range(3)]
        store.save_batch(leads)

        jsonl_rows = list(store.read_all())
        assert len(jsonl_rows) == 3

        repo = Repository(db, "leads", pk_field="lead_id")
        assert repo.count() == 3

    def test_sqlite_failure_does_not_lose_jsonl(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema
        import unittest.mock

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)

        # Write a valid record, then break SQLite
        store.save(_make_lead(lead_id="l_ok"))
        with unittest.mock.patch.object(store._dual_writer.repo, "insert", side_effect=Exception("DB failure")):
            store.save(_make_lead(lead_id="l_after_failure"))

        jsonl_rows = list(store.read_all())
        assert len(jsonl_rows) == 2

    def test_jsonl_only_mode_still_works(self, tmp_path):
        store = LeadStore(tmp_path / "leads.jsonl")
        assert store._dual_writer is None
        store.save(_make_lead())
        assert store.count() == 1
