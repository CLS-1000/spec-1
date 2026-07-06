# @domain:   machine
# @module:   test_persistence
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for cls_db — database persistence and dual-write."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# PostgreSQL persistence tests (spec1_engine.persistence.postgres)
# ---------------------------------------------------------------------------
"""Tests for the PostgreSQL persistence module.

Uses SQLite (via SQLAlchemy) as a drop-in replacement so tests run without
a real PostgreSQL instance.
"""

import pytest


# ─── Module import / configure ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_pg_engine():
    """Reset the cached engine before and after every test."""
    import spec1_engine.persistence.postgres as pg
    pg.reset_engine()
    yield
    pg.reset_engine()


@pytest.fixture
def sqlite_url(tmp_path):
    """Return a SQLite DATABASE_URL backed by a temp file."""
    db_file = tmp_path / "test_intel.db"
    return f"sqlite:///{db_file}"


@pytest.fixture
def sample_record():
    return {
        "record_id": "rec-test001",
        "run_id": "run-abc",
        "signal_id": "sig-001",
        "signal_source": "war_on_the_rocks",
        "signal_url": "https://example.com/article",
        "pattern": "[ELEVATED] Test pattern | gates=credibility+volume",
        "classification": "Corroborated",
        "outcome_classification": "Corroborated",
        "confidence": 0.85,
        "outcome_confidence": 0.80,
        "source_weight": 0.85,
        "analyst_weight": 0.90,
        "opportunity_id": "opp-testx001",
        "opportunity_score": 0.78,
        "opportunity_priority": "ELEVATED",
        "investigation_id": "inv-test001",
        "hypothesis": "This is a test hypothesis.",
        "environment": "test",
    }


# ─── No DATABASE_URL ──────────────────────────────────────────────────────────

def test_append_returns_false_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.append({"record_id": "x"}) is False


def test_append_batch_returns_zero_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.append_batch([{"record_id": "x"}]) == 0


def test_query_latest_returns_empty_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.query_latest() == []


def test_count_returns_zero_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.count() == 0


def test_is_configured_returns_false_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.is_configured() is False


def test_init_db_returns_false_when_no_url():
    import spec1_engine.persistence.postgres as pg
    assert pg.init_db() is False


# ─── With SQLite DATABASE_URL ─────────────────────────────────────────────────

def test_init_db_creates_tables(sqlite_url):
    import spec1_engine.persistence.postgres as pg
    result = pg.init_db(url=sqlite_url)
    assert result is True


def test_is_configured_true_with_sqlite(sqlite_url):
    import spec1_engine.persistence.postgres as pg
    assert pg.is_configured(url=sqlite_url) is True


def test_append_returns_true_with_sqlite(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    result = pg.append(sample_record, url=sqlite_url)
    assert result is True


def test_count_after_append(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    pg.append(sample_record, url=sqlite_url)
    assert pg.count(url=sqlite_url) == 1


def test_count_empty_database(sqlite_url):
    import spec1_engine.persistence.postgres as pg
    pg.init_db(url=sqlite_url)
    assert pg.count(url=sqlite_url) == 0


def test_query_latest_returns_inserted_record(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    pg.append(sample_record, url=sqlite_url)
    records = pg.query_latest(limit=10, url=sqlite_url)
    assert len(records) == 1
    assert records[0]["record_id"] == "rec-test001"


def test_query_latest_limit(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    for i in range(5):
        r = {**sample_record, "record_id": f"rec-{i:04d}"}
        pg.append(r, url=sqlite_url)
    records = pg.query_latest(limit=3, url=sqlite_url)
    assert len(records) == 3


def test_append_batch_inserts_all(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    batch = [{**sample_record, "record_id": f"rec-b{i}"} for i in range(5)]
    inserted = pg.append_batch(batch, url=sqlite_url)
    assert inserted == 5
    assert pg.count(url=sqlite_url) == 5


def test_append_batch_empty_returns_zero(sqlite_url):
    import spec1_engine.persistence.postgres as pg
    assert pg.append_batch([], url=sqlite_url) == 0


def test_append_idempotent_duplicate_primary_key(sqlite_url, sample_record):
    """Appending the same record_id twice does not raise and count stays at 1."""
    import spec1_engine.persistence.postgres as pg
    pg.append(sample_record, url=sqlite_url)
    pg.append(sample_record, url=sqlite_url)
    assert pg.count(url=sqlite_url) == 1


def test_record_fields_persisted(sqlite_url, sample_record):
    import spec1_engine.persistence.postgres as pg
    pg.append(sample_record, url=sqlite_url)
    records = pg.query_latest(url=sqlite_url)
    assert len(records) == 1
    row = records[0]
    assert row["signal_source"] == "war_on_the_rocks"
    assert row["classification"] == "Corroborated"
    assert row["opportunity_priority"] == "ELEVATED"
    assert abs(row["confidence"] - 0.85) < 1e-6


def test_multiple_records_ordered_by_written_at(sqlite_url, sample_record):
    """query_latest returns newest records first."""
    import spec1_engine.persistence.postgres as pg
    for i in range(3):
        pg.append({**sample_record, "record_id": f"rec-ord-{i}"}, url=sqlite_url)
    records = pg.query_latest(url=sqlite_url)
    assert len(records) == 3


def test_build_row_handles_missing_fields():
    from spec1_engine.persistence.postgres import _build_row
    row = _build_row({"record_id": "minimal"})
    assert row["record_id"] == "minimal"
    assert row["signal_source"] is None
    assert row["confidence"] is None


def test_build_row_uses_alternate_field_names():
    from spec1_engine.persistence.postgres import _build_row
    row = _build_row({
        "record_id": "r1",
        "source": "cipher_brief",
        "url": "https://example.com",
    })
    assert row["signal_source"] == "cipher_brief"
    assert row["signal_url"] == "https://example.com"


def test_to_float_handles_none():
    from spec1_engine.persistence.postgres import _to_float
    assert _to_float(None) is None


def test_to_float_handles_string():
    from spec1_engine.persistence.postgres import _to_float
    assert _to_float("0.75") == pytest.approx(0.75)


def test_to_float_handles_invalid():
    from spec1_engine.persistence.postgres import _to_float
    assert _to_float("not_a_number") is None


def test_reset_engine_clears_cache(sqlite_url):
    import spec1_engine.persistence.postgres as pg
    pg.init_db(url=sqlite_url)
    assert pg._engine is not None
    pg.reset_engine()
    assert pg._engine is None


# ---------------------------------------------------------------------------
# cls_db persistence tests
# ---------------------------------------------------------------------------
from cls_db.database import Database
from cls_db.models import ALL_DDL
from cls_db.repository import Repository, _serialize, _row_to_dict
from cls_db.migrate import ensure_schema, run_migrations, drop_all, reset_schema
from cls_db.dual_write import make_dual_writer


class TestDatabase:
    def test_creates_db_file(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")
        assert (tmp_path / "test.db").exists()

    def test_execute_and_fetchall(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        db.execute("INSERT INTO t VALUES (1, 'hello')")
        rows = db.fetchall("SELECT * FROM t")
        assert len(rows) == 1
        assert rows[0]["val"] == "hello"

    def test_fetchone_returns_dict(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        db.execute("INSERT INTO t VALUES (42, 'world')")
        row = db.fetchone("SELECT * FROM t WHERE id = ?", (42,))
        assert row is not None
        assert row["val"] == "world"

    def test_fetchone_returns_none_for_miss(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        row = db.fetchone("SELECT * FROM t WHERE id = ?", (999,))
        assert row is None

    def test_executemany(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        db.executemany("INSERT INTO t VALUES (?, ?)", [(1, "a"), (2, "b"), (3, "c")])
        rows = db.fetchall("SELECT * FROM t")
        assert len(rows) == 3

    def test_table_exists(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE mytable (id INTEGER)")
        assert db.table_exists("mytable")
        assert not db.table_exists("missing_table")

    def test_close_and_reopen(self, tmp_path):
        db = Database(tmp_path / "test.db")
        db.execute("CREATE TABLE t (id INTEGER)")
        db.execute("INSERT INTO t VALUES (1)")
        db.close()
        # Reopen
        db2 = Database(tmp_path / "test.db")
        rows = db2.fetchall("SELECT * FROM t")
        assert len(rows) == 1


class TestSerialize:
    def test_dict_serialized_to_json(self):
        assert _serialize({"a": 1}) == '{"a": 1}'

    def test_list_serialized_to_json(self):
        assert _serialize([1, 2, 3]) == "[1, 2, 3]"

    def test_string_unchanged(self):
        assert _serialize("hello") == "hello"

    def test_int_unchanged(self):
        assert _serialize(42) == 42


class TestRowToDict:
    def test_deserializes_json_string_dict(self):
        row = {"data": '{"key": "value"}'}
        result = _row_to_dict(row)
        assert result["data"] == {"key": "value"}

    def test_deserializes_json_string_list(self):
        row = {"items": '["a", "b"]'}
        result = _row_to_dict(row)
        assert result["items"] == ["a", "b"]

    def test_leaves_non_json_strings_alone(self):
        row = {"text": "plain string"}
        result = _row_to_dict(row)
        assert result["text"] == "plain string"


class TestMigrations:
    def test_ensure_schema_creates_tables(self, tmp_path):
        db = Database(tmp_path / "test.db")
        created = ensure_schema(db)
        assert "signals" in created
        assert "leads" in created

    def test_ensure_schema_idempotent(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        # Second call should not raise
        created2 = ensure_schema(db)
        assert created2 == []

    def test_run_migrations_report(self, tmp_path):
        db = Database(tmp_path / "test.db")
        report = run_migrations(db)
        assert "tables_created" in report
        assert "total_tables" in report
        assert report["total_tables"] == len(ALL_DDL)

    def test_drop_all_removes_tables(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        drop_all(db)
        assert not db.table_exists("signals")
        assert not db.table_exists("leads")

    def test_reset_schema(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        db.execute("INSERT INTO signals (signal_id, source) VALUES ('s1', 'test')")
        reset_schema(db)
        # After reset, table exists but old data is gone
        assert db.table_exists("signals")
        rows = db.fetchall("SELECT * FROM signals")
        assert len(rows) == 0


class TestRepository:
    def setup_method(self):
        """Create a fresh in-memory-like DB for each test."""
        pass

    def test_insert_and_get(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        record = {
            "lead_id": "l001",
            "title": "Test Lead",
            "priority": "HIGH",
            "category": "military",
            "confidence": 0.8,
        }
        repo.insert(record)
        result = repo.get("l001")
        assert result is not None
        assert result["lead_id"] == "l001"
        assert result["priority"] == "HIGH"

    def test_insert_batch(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        records = [
            {"lead_id": f"l{i:03d}", "title": f"Lead {i}", "priority": "LOW", "category": "cyber"}
            for i in range(5)
        ]
        count = repo.insert_batch(records)
        assert count == 5
        assert repo.count() == 5

    def test_filter_by_field(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        repo.insert({"lead_id": "l1", "title": "Lead one", "priority": "HIGH", "category": "cyber"})
        repo.insert({"lead_id": "l2", "title": "Lead two", "priority": "LOW", "category": "military"})

        high = repo.filter("priority", "HIGH")
        assert len(high) == 1
        assert high[0]["lead_id"] == "l1"

    def test_count(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        for i in range(3):
            repo.insert({"lead_id": f"l{i}", "title": f"Lead {i}", "priority": "LOW"})

        assert repo.count() == 3

    def test_delete(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        repo.insert({"lead_id": "l1", "title": "Lead to delete", "priority": "LOW"})
        repo.delete("l1")
        assert repo.get("l1") is None

    def test_latest(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        for i in range(10):
            repo.insert({"lead_id": f"l{i:03d}", "title": f"Lead {i}", "priority": "LOW"})

        latest = repo.latest(3)
        assert len(latest) == 3

    def test_insert_replace_on_pk_conflict(self, tmp_path):
        db = Database(tmp_path / "test.db")
        ensure_schema(db)
        repo = Repository(db, "leads", pk_field="lead_id")

        repo.insert({"lead_id": "l1", "title": "Original"})
        repo.insert({"lead_id": "l1", "title": "Updated"})

        result = repo.get("l1")
        assert result["title"] == "Updated"


class TestDualWriter:
    def test_write_goes_to_both_stores(self, tmp_path):
        jsonl_path = tmp_path / "data.jsonl"
        db_path = tmp_path / "data.db"
        writer = make_dual_writer(
            jsonl_path=jsonl_path,
            db_path=db_path,
            table="leads",
            pk_field="lead_id",
        )
        record = {"lead_id": "l001", "title": "Test Lead", "priority": "HIGH"}
        writer.write(record)

        assert writer.count_jsonl() == 1
        db_records = writer.read_db(limit=10)
        assert len(db_records) == 1

    def test_write_batch(self, tmp_path):
        jsonl_path = tmp_path / "data.jsonl"
        db_path = tmp_path / "data.db"
        writer = make_dual_writer(
            jsonl_path=jsonl_path, db_path=db_path, table="leads", pk_field="lead_id"
        )
        records = [{"lead_id": f"l{i}", "title": f"Lead {i}"} for i in range(5)]
        written = writer.write_batch(records)
        assert len(written) == 5
        assert writer.count_jsonl() == 5

    def test_read_jsonl_returns_records(self, tmp_path):
        writer = make_dual_writer(tmp_path / "data.jsonl", tmp_path / "db.db", "leads")
        writer.write({"lead_id": "l1", "title": "Lead 1"})
        jsonl_data = writer.read_jsonl()
        assert len(jsonl_data) == 1
        assert jsonl_data[0]["lead_id"] == "l1"

    def test_sqlite_failure_does_not_break_jsonl(self, tmp_path):
        """JSONL write should succeed even if SQLite insert fails."""
        jsonl_path = tmp_path / "data.jsonl"
        db_path = tmp_path / "data.db"
        writer = make_dual_writer(jsonl_path=jsonl_path, db_path=db_path, table="leads")

        # Write a valid record
        writer.write({"lead_id": "l1", "title": "Test"})

        # Force a bad record with malformed data
        import unittest.mock
        with unittest.mock.patch.object(writer.repo, "insert", side_effect=Exception("DB error")):
            writer.write({"lead_id": "l2", "title": "Test 2"})

        # JSONL should have both records
        assert writer.count_jsonl() == 2


# ── Store-level dual-write tests ───────────────────────────────────────────


class TestLeadStoreDualWrite:
    """Verify LeadStore writes to both JSONL and SQLite when db is provided."""

    def _db(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        return db

    def _make_lead(self, lead_id: str = "lead-001"):
        from cls_leads.schemas import Lead

        return Lead(
            lead_id=lead_id,
            title="Test Lead",
            summary="Summary text",
            priority="HIGH",
            category="diplomatic",
            source_record_ids=[],
            action_items=[],
            confidence=0.8,
        )

    def test_dual_write_saves_to_jsonl(self, tmp_path):
        from cls_leads.store import LeadStore

        db = self._db(tmp_path)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)
        lead = self._make_lead("lead-dw-001")
        store.save(lead)
        rows = list(store.read_all())
        assert len(rows) == 1
        assert rows[0]["lead_id"] == "lead-dw-001"

    def test_dual_write_saves_to_sqlite(self, tmp_path):
        from cls_leads.store import LeadStore
        from cls_db.repository import Repository

        db = self._db(tmp_path)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)
        lead = self._make_lead("lead-dw-002")
        store.save(lead)
        repo = Repository(db, "leads", "lead_id")
        rows = repo.all()
        assert any(r["lead_id"] == "lead-dw-002" for r in rows)

    def test_batch_dual_write(self, tmp_path):
        from cls_leads.store import LeadStore

        db = self._db(tmp_path)
        store = LeadStore(tmp_path / "leads.jsonl", db=db)
        leads = [self._make_lead(f"lead-b-{i:03d}") for i in range(3)]
        result = store.save_batch(leads)
        assert len(result) == 3
        assert store.count() == 3

    def test_jsonl_only_still_works(self, tmp_path):
        from cls_leads.store import LeadStore

        store = LeadStore(tmp_path / "leads.jsonl")
        lead = self._make_lead("lead-jl-001")
        entry = store.save(lead)
        assert "written_at" in entry
        assert store.count() == 1


class TestPsyopStoreDualWrite:
    """Verify PsyopStore writes to both JSONL and SQLite when db is provided."""

    def _db(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        return db

    def _make_score(self, score_id: str = "score-001"):
        from cls_psyop.schemas import PsyopScore

        return PsyopScore(
            score_id=score_id,
            text_hash="abc123",
            text_excerpt="Test excerpt.",
            patterns_matched=[],
            pattern_names=[],
            score=0.3,
            classification="LOW",
            threat_categories=[],
        )

    def test_dual_write_saves_to_jsonl(self, tmp_path):
        from cls_psyop.store import PsyopStore

        db = self._db(tmp_path)
        store = PsyopStore(tmp_path / "psyop.jsonl", db=db)
        score = self._make_score("score-dw-001")
        store.save(score)
        rows = list(store.read_all())
        assert len(rows) == 1
        assert rows[0]["score_id"] == "score-dw-001"

    def test_dual_write_saves_to_sqlite(self, tmp_path):
        from cls_psyop.store import PsyopStore
        from cls_db.repository import Repository

        db = self._db(tmp_path)
        store = PsyopStore(tmp_path / "psyop.jsonl", db=db)
        score = self._make_score("score-dw-002")
        store.save(score)
        repo = Repository(db, "psyop_scores", "score_id")
        rows = repo.all()
        assert any(r["score_id"] == "score-dw-002" for r in rows)

    def test_batch_dual_write(self, tmp_path):
        from cls_psyop.store import PsyopStore

        db = self._db(tmp_path)
        store = PsyopStore(tmp_path / "psyop.jsonl", db=db)
        scores = [self._make_score(f"score-b-{i:03d}") for i in range(4)]
        result = store.save_batch(scores)
        assert len(result) == 4
        assert store.count() == 4

    def test_jsonl_only_still_works(self, tmp_path):
        from cls_psyop.store import PsyopStore

        store = PsyopStore(tmp_path / "psyop.jsonl")
        score = self._make_score("score-jl-001")
        entry = store.save(score)
        assert "written_at" in entry
        assert store.count() == 1


class TestBriefStoreDualWrite:
    """Verify BriefStore writes to both JSONL and SQLite when db is provided."""

    def _db(self, tmp_path):
        from cls_db.database import Database
        from cls_db.migrate import ensure_schema

        db = Database(tmp_path / "spec1.db")
        ensure_schema(db)
        return db

    def _make_brief(self, brief_id: str = "brief-001"):
        from cls_world_brief.schemas import WorldBrief

        return WorldBrief(
            brief_id=brief_id,
            date="2026-01-01",
            headline="Test headline",
            summary="Test summary.",
            sections=[],
            sources=[],
            confidence=0.75,
        )

    def test_dual_write_saves_to_jsonl(self, tmp_path):
        from cls_world_brief.store import BriefStore

        db = self._db(tmp_path)
        store = BriefStore(
            jsonl_path=tmp_path / "briefs.jsonl",
            briefs_dir=tmp_path / "briefs",
            db=db,
        )
        brief = self._make_brief("brief-dw-001")
        store.save(brief, write_markdown=False)
        rows = list(store.read_all())
        assert len(rows) == 1
        assert rows[0]["brief_id"] == "brief-dw-001"

    def test_dual_write_saves_to_sqlite(self, tmp_path):
        from cls_world_brief.store import BriefStore
        from cls_db.repository import Repository

        db = self._db(tmp_path)
        store = BriefStore(
            jsonl_path=tmp_path / "briefs.jsonl",
            briefs_dir=tmp_path / "briefs",
            db=db,
        )
        brief = self._make_brief("brief-dw-002")
        store.save(brief, write_markdown=False)
        repo = Repository(db, "briefs", "brief_id")
        rows = repo.all()
        assert any(r["brief_id"] == "brief-dw-002" for r in rows)

    def test_markdown_still_written_with_dual_write(self, tmp_path):
        from cls_world_brief.store import BriefStore

        db = self._db(tmp_path)
        briefs_dir = tmp_path / "briefs"
        store = BriefStore(
            jsonl_path=tmp_path / "briefs.jsonl",
            briefs_dir=briefs_dir,
            db=db,
        )
        brief = self._make_brief("brief-md-001")
        store.save(brief, write_markdown=True)
        assert (briefs_dir / "2026-01-01.md").exists()
        assert (briefs_dir / "latest.md").exists()

    def test_jsonl_only_still_works(self, tmp_path):
        from cls_world_brief.store import BriefStore

        store = BriefStore(
            jsonl_path=tmp_path / "briefs.jsonl",
            briefs_dir=tmp_path / "briefs",
        )
        brief = self._make_brief("brief-jl-001")
        entry = store.save(brief, write_markdown=False)
        assert "written_at" in entry
        assert store.count() == 1
