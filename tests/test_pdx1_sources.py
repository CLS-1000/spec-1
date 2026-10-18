# @domain:   spec-1
# @module:   test_pdx1_sources
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for cls_pdx1 source adapters."""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock, patch

from cls_pdx1.models import Affiliation, Bill, BillStatus, ConfidenceTier, EdgeType
from cls_pdx1.sources.orestar import OrestarAdapter
from cls_pdx1.sources.olis import OlisAdapter
from cls_pdx1.sources.sei import SeiAdapter
from cls_pdx1.sources.wa_pdc import WaPdcAdapter


# ---------------------------------------------------------------------------
# ORESTAR
# ---------------------------------------------------------------------------

_ORESTAR_CSV = """\
filer_id,filer_name,transaction_type,amount,contributor_name,contributor_address,transaction_date,election_year
1001,Jane Smith,contribution,$5000.00,Acme Corp,123 Main St,01/15/2024,2024
1002,Bob Jones,contribution,$1200.50,XYZ LLC,456 Oak Ave,03/22/2024,2024
1003,,contribution,$500.00,Unknown,,,
"""


class TestOrestarAdapter:
    def test_parses_valid_rows(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_ORESTAR_CSV)
        assert len(result.records) == 2  # row 3 skipped (no filer_name)

    def test_affiliation_type(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_ORESTAR_CSV)
        assert all(isinstance(r, Affiliation) for r in result.records)

    def test_edge_type_is_donation(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_ORESTAR_CSV)
        assert all(r.edge_type == EdgeType.DONATION for r in result.records)

    def test_confidence_is_hard_record(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_ORESTAR_CSV)
        assert all(r.confidence == ConfidenceTier.HARD_RECORD for r in result.records)

    def test_amount_parsed(self):
        adapter = OrestarAdapter()
        result = adapter.fetch_from_csv_text(_ORESTAR_CSV)
        amounts = [r.amount for r in result.records]
        assert 5000.0 in amounts

    def test_missing_csv_returns_error(self):
        adapter = OrestarAdapter(csv_path="/nonexistent/path.csv")
        result = adapter.fetch()
        assert len(result.errors) > 0

    def test_live_fetch_zip(self):
        """Adapter downloads ZIP, extracts CSV, parses records."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("transactions.csv", _ORESTAR_CSV)
        zip_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()

        with patch("cls_pdx1.sources.orestar.requests.get", return_value=mock_resp):
            adapter = OrestarAdapter(year=2024)
            result = adapter.fetch()

        assert len(result.records) == 2
        assert result.errors == []

    def test_live_fetch_http_error(self, tmp_path):
        """HTTP failure with no cache returns an error."""
        import requests as req
        with patch("cls_pdx1.sources.orestar.requests.get", side_effect=req.RequestException("timeout")):
            adapter = OrestarAdapter(year=2024, cache_dir=tmp_path / "empty_cache")
            result = adapter.fetch()
        assert len(result.errors) > 0
        assert "HTTP error" in result.errors[0]

    def test_cache_fallback_on_http_error(self, tmp_path):
        """HTTP failure falls back to cached CSV."""
        import requests as req
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "orestar_2024.csv").write_text(_ORESTAR_CSV, encoding="utf-8")

        with patch("cls_pdx1.sources.orestar.requests.get", side_effect=req.RequestException("down")):
            adapter = OrestarAdapter(year=2024, cache_dir=cache_dir)
            result = adapter.fetch()

        assert len(result.records) == 2
        assert any("cached" in e for e in result.errors)

    def test_successful_fetch_writes_cache(self, tmp_path):
        """Successful HTTP fetch writes cache to disk."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("transactions.csv", _ORESTAR_CSV)
        zip_bytes = buf.getvalue()

        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()

        cache_dir = tmp_path / "cache"
        with patch("cls_pdx1.sources.orestar.requests.get", return_value=mock_resp):
            adapter = OrestarAdapter(year=2024, cache_dir=cache_dir)
            adapter.fetch()

        assert (cache_dir / "orestar_2024.csv").exists()


# ---------------------------------------------------------------------------
# OLIS
# ---------------------------------------------------------------------------

_OLIS_BILLS = [
    {
        "MeasureNumber": "HB 1234",
        "RelatingClause": "An act relating to housing",
        "CurrentStatus": "In Committee",
        "Chamber": "House",
        "ChiefSponsor": "Rep. Smith",
        "source_url": "https://oregonlegislature.gov/bills/HB1234",
    },
    {
        "MeasureNumber": "SB 567",
        "RelatingClause": "An act relating to utilities",
        "CurrentStatus": "Passed Both Chambers",
        "Chamber": "Senate",
        "ChiefSponsor": "Sen. Jones",
        "source_url": "https://oregonlegislature.gov/bills/SB567",
    },
    {
        "MeasureNumber": "",   # should be skipped
        "RelatingClause": "Bad bill",
        "CurrentStatus": "Introduced",
        "Chamber": "House",
        "source_url": "https://oregonlegislature.gov/",
    },
]


class TestOlisAdapter:
    def test_parses_valid_bills(self):
        adapter = OlisAdapter(bill_data=_OLIS_BILLS)
        result = adapter.fetch()
        assert len(result.records) == 2

    def test_bill_type(self):
        adapter = OlisAdapter(bill_data=_OLIS_BILLS)
        result = adapter.fetch()
        assert all(isinstance(r, Bill) for r in result.records)

    def test_status_in_committee(self):
        adapter = OlisAdapter(bill_data=_OLIS_BILLS[:1])
        result = adapter.fetch()
        assert result.records[0].status == BillStatus.IN_COMMITTEE

    def test_status_passed_both_chambers(self):
        adapter = OlisAdapter(bill_data=_OLIS_BILLS[1:2])
        result = adapter.fetch()
        assert result.records[0].status == BillStatus.PASSED_BOTH_CHAMBERS

    def test_live_fetch_odata(self):
        """Adapter fetches OData JSON, paginates, parses bills."""
        page1 = {"value": _OLIS_BILLS[:1], "@odata.nextLink": "https://api.oregonlegislature.gov/page2"}
        page2 = {"value": _OLIS_BILLS[1:2]}  # only valid bill, not the empty-id stub

        responses = [MagicMock(), MagicMock()]
        responses[0].json.return_value = page1
        responses[0].raise_for_status = MagicMock()
        responses[1].json.return_value = page2
        responses[1].raise_for_status = MagicMock()

        with patch("cls_pdx1.sources.olis.requests.get", side_effect=responses):
            adapter = OlisAdapter()
            result = adapter.fetch()

        assert len(result.records) == 2
        assert result.errors == []

    def test_live_fetch_http_error(self, tmp_path):
        """HTTP failure with no cache returns an error."""
        import requests as req
        with patch("cls_pdx1.sources.olis.requests.get", side_effect=req.RequestException("timeout")):
            adapter = OlisAdapter(session_key="2025R1", cache_dir=tmp_path / "empty_cache")
            result = adapter.fetch()
        assert len(result.errors) > 0
        assert "HTTP error" in result.errors[0]

    def test_cache_fallback_on_http_error(self, tmp_path):
        """HTTP failure falls back to cached JSON."""
        import requests as req
        import json
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "olis_2025R1.json").write_text(
            json.dumps(_OLIS_BILLS[:2]), encoding="utf-8"
        )

        with patch("cls_pdx1.sources.olis.requests.get", side_effect=req.RequestException("down")):
            adapter = OlisAdapter(session_key="2025R1", cache_dir=cache_dir)
            result = adapter.fetch()

        assert len(result.records) == 2
        assert any("cached" in e for e in result.errors)

    def test_successful_fetch_writes_cache(self, tmp_path):
        """Successful HTTP fetch writes cache to disk."""
        page = {"value": _OLIS_BILLS[:2]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = page
        mock_resp.raise_for_status = MagicMock()

        cache_dir = tmp_path / "cache"
        with patch("cls_pdx1.sources.olis.requests.get", return_value=mock_resp):
            adapter = OlisAdapter(session_key="2025R1", cache_dir=cache_dir)
            adapter.fetch()

        assert (cache_dir / "olis_2025R1.json").exists()

    def test_sponsor_captured(self):
        adapter = OlisAdapter(bill_data=_OLIS_BILLS[:1])
        result = adapter.fetch()
        assert result.records[0].sponsor == "Rep. Smith"


# ---------------------------------------------------------------------------
# SEI
# ---------------------------------------------------------------------------

_SEI_RECORDS = [
    {
        "official_name": "Commissioner A",
        "role": "City Commissioner",
        "year": 2024,
        "source_url": "https://www.oregon.gov/ogec/pages/sei.aspx",
        "business_interests": [
            {"entity_name": "Realty Corp", "amount": 50000},
            {"entity_name": "Tech LLC", "amount": 0},
        ],
        "gifts": [
            {"donor": "Business PAC", "amount": 150},
        ],
    },
    {
        "official_name": "Senator B",
        "role": "State Senator",
        "year": 2024,
        "source_url": "https://www.oregon.gov/ogec/pages/sei.aspx",
        "business_interests": [],
        "gifts": [],
    },
]


class TestSeiAdapter:
    def test_parses_business_interests(self):
        adapter = SeiAdapter(records=_SEI_RECORDS)
        result = adapter.fetch()
        employment_affs = [r for r in result.records if r.edge_type == EdgeType.EMPLOYMENT]
        assert len(employment_affs) == 2  # 2 business interests for Commissioner A

    def test_parses_gifts(self):
        adapter = SeiAdapter(records=_SEI_RECORDS)
        result = adapter.fetch()
        gift_affs = [r for r in result.records if r.edge_type == EdgeType.DONATION]
        assert len(gift_affs) == 1

    def test_all_hard_record(self):
        adapter = SeiAdapter(records=_SEI_RECORDS)
        result = adapter.fetch()
        assert all(r.confidence == ConfidenceTier.HARD_RECORD for r in result.records)

    def test_missing_official_name_skipped(self):
        bad = [{"official_name": "", "role": "Mayor", "business_interests": [{"entity_name": "Corp"}], "gifts": []}]
        adapter = SeiAdapter(records=bad)
        result = adapter.fetch()
        assert len(result.records) == 0

    def test_jsonl_file(self, tmp_path):
        jsonl = tmp_path / "sei.jsonl"
        jsonl.write_text(
            "\n".join(json.dumps(r) for r in _SEI_RECORDS),
            encoding="utf-8",
        )
        adapter = SeiAdapter(jsonl_path=jsonl)
        result = adapter.fetch()
        assert len(result.records) >= 1

    def test_missing_jsonl_returns_error(self):
        adapter = SeiAdapter(jsonl_path="/nonexistent/sei.jsonl")
        result = adapter.fetch()
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# WA PDC
# ---------------------------------------------------------------------------

_WA_PDC_RECORDS = [
    {
        "filer_name": "Candidate X",
        "contributor_name": "Real Estate PAC",
        "amount": "10000",
        "receipt_date": "2024-04-15",
    },
    {
        "filer_name": "",   # should be skipped
        "contributor_name": "Nobody",
        "amount": "100",
        "receipt_date": "2024-01-01",
    },
]


class TestWaPdcAdapter:
    def test_parses_valid_records(self):
        adapter = WaPdcAdapter(records=_WA_PDC_RECORDS)
        result = adapter.fetch()
        assert len(result.records) == 1

    def test_edge_type_donation(self):
        adapter = WaPdcAdapter(records=_WA_PDC_RECORDS)
        result = adapter.fetch()
        assert result.records[0].edge_type == EdgeType.DONATION

    def test_amount_parsed(self):
        adapter = WaPdcAdapter(records=_WA_PDC_RECORDS)
        result = adapter.fetch()
        assert result.records[0].amount == 10000.0

    def test_no_records_returns_error(self):
        adapter = WaPdcAdapter()
        result = adapter.fetch()
        assert len(result.errors) > 0


# Shape of a real row from the OLIS ``Measures`` entity (OLOData model):
# prefix and number are separate, there is no CurrentStatus / RelatingClause /
# ChiefSponsor / Chamber, and status lives in Vetoed / ChapterNumber / CurrentLocation.
_LIVE_MEASURES = [
    {"SessionKey": "2025R1", "MeasurePrefix": "HB", "MeasureNumber": 2001,
     "CatchLine": "Relating to housing; declaring an emergency.",
     "CurrentLocation": "In committee upon adjournment", "Vetoed": False, "ChapterNumber": None},
    {"SessionKey": "2025R1", "MeasurePrefix": "SB", "MeasureNumber": 2001,
     "CatchLine": "Relating to wildfire.", "CurrentLocation": "Governor's desk",
     "Vetoed": False, "ChapterNumber": "Chapter 412"},
    {"SessionKey": "2025R1", "MeasurePrefix": "SB", "MeasureNumber": 976,
     "CatchLine": "Relating to cosmetics.", "CurrentLocation": "Governor's desk",
     "Vetoed": True, "ChapterNumber": None},
]


class TestOlisLiveShape:
    def _bills(self):
        return OlisAdapter(bill_data=_LIVE_MEASURES, session_key="2025R1").fetch().records

    def test_same_number_in_both_chambers_does_not_collide(self):
        bills = self._bills()
        assert [b.external_id for b in bills] == ["HB 2001", "SB 2001", "SB 976"]
        assert len({b.bill_id for b in bills}) == 3

    def test_title_comes_from_catchline(self):
        assert self._bills()[0].title == "Relating to housing; declaring an emergency."

    def test_status_uses_structured_fields(self):
        hb, sb_law, sb_veto = self._bills()
        assert hb.status == BillStatus.IN_COMMITTEE
        assert sb_law.status == BillStatus.SIGNED
        assert sb_veto.status == BillStatus.VETOED

    def test_chamber_from_prefix_and_url_to_measure(self):
        hb = self._bills()[0]
        assert hb.chamber == "House"
        assert hb.source_url == (
            "https://olis.oregonlegislature.gov/liz/2025R1/Measures/Overview/HB2001")

    def test_legacy_fixture_ids_unchanged(self):
        # Pre-fix fixture rows keep the same external_id, so stored bill_ids stay stable.
        legacy = OlisAdapter(bill_data=_OLIS_BILLS[:1]).fetch().records[0]
        assert legacy.external_id == "HB 1234"
