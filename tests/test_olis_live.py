# @domain:   spec-1
# @module:   test_olis_live
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.sources.olis — OlisAdapter offline coverage.

All tests use in-memory fixture data — no HTTP calls.
"""

from __future__ import annotations

from unittest.mock import patch

import requests

from titan.models import BillStatus
from titan.sources.olis import OlisAdapter, _map_status


_INTRODUCED_FIXTURE = {
    "MeasureNumber": "HB 2001",
    "RelatingClause": "Relating to housing density standards.",
    "CurrentStatus": "introduced",
    "ChiefSponsor": "Smith",
    "Chamber": "House",
    "source_url": "https://www.oregonlegislature.gov/bills/HB2001",
}

_ENROLLED_FIXTURE = {
    "MeasureNumber": "SB 500",
    "RelatingClause": "Relating to wildfire mitigation.",
    "CurrentStatus": "Passed Both Chambers — enrolled",
    "ChiefSponsor": "Jones",
    "Chamber": "Senate",
    "source_url": "https://www.oregonlegislature.gov/bills/SB500",
}

_FAILED_FIXTURE = {
    "MeasureNumber": "HB 9999",
    "RelatingClause": "Relating to tax credits.",
    "CurrentStatus": "failed on floor vote",
    "ChiefSponsor": "",
    "Chamber": "House",
    "source_url": "https://www.oregonlegislature.gov/bills/HB9999",
}


class TestMapStatus:
    def test_introduced(self):
        assert _map_status("introduced") == BillStatus.INTRODUCED

    def test_enrolled_maps_to_passed_both(self):
        assert _map_status("Passed Both Chambers — enrolled") == BillStatus.PASSED_BOTH_CHAMBERS

    def test_signed(self):
        assert _map_status("signed by governor") == BillStatus.SIGNED

    def test_vetoed(self):
        assert _map_status("vetoed") == BillStatus.VETOED

    def test_overridden(self):
        assert _map_status("veto overridden") == BillStatus.OVERRIDDEN

    def test_passed_committee(self):
        assert _map_status("passed committee vote") == BillStatus.PASSED_COMMITTEE

    def test_passed_one_chamber(self):
        assert _map_status("passed House floor") == BillStatus.PASSED_ONE_CHAMBER

    def test_in_committee(self):
        assert _map_status("referred to committee") == BillStatus.IN_COMMITTEE

    def test_failed(self):
        assert _map_status("failed on floor vote") == BillStatus.FAILED

    def test_dead(self):
        assert _map_status("pocket veto — dead") == BillStatus.DEAD

    def test_unknown_maps_to_introduced(self):
        assert _map_status("some unknown status string") == BillStatus.INTRODUCED


class TestOlisAdapterOffline:
    def test_parse_introduced_bill(self):
        adapter = OlisAdapter(bill_data=[_INTRODUCED_FIXTURE])
        result = adapter.fetch()
        assert result.ok()
        assert len(result.records) == 1
        bill = result.records[0]
        assert bill.external_id == "HB 2001"
        assert bill.status == BillStatus.INTRODUCED

    def test_parse_enrolled_bill_status(self):
        adapter = OlisAdapter(bill_data=[_ENROLLED_FIXTURE])
        result = adapter.fetch()
        assert len(result.records) == 1
        assert result.records[0].status == BillStatus.PASSED_BOTH_CHAMBERS

    def test_parse_failed_bill_status(self):
        adapter = OlisAdapter(bill_data=[_FAILED_FIXTURE])
        result = adapter.fetch()
        assert len(result.records) == 1
        assert result.records[0].status == BillStatus.FAILED

    def test_missing_measure_skipped(self):
        bad = {"RelatingClause": "No measure number", "CurrentStatus": "introduced"}
        adapter = OlisAdapter(bill_data=[bad])
        result = adapter.fetch()
        assert len(result.records) == 0
        assert len(result.errors) == 1

    def test_result_ok_on_clean_input(self):
        adapter = OlisAdapter(bill_data=[_INTRODUCED_FIXTURE, _ENROLLED_FIXTURE])
        result = adapter.fetch()
        assert result.ok()
        assert len(result.records) == 2

    def test_sponsor_captured(self):
        adapter = OlisAdapter(bill_data=[_INTRODUCED_FIXTURE])
        result = adapter.fetch()
        bill = result.records[0]
        assert bill.sponsor == "Smith"

    def test_no_sponsor_is_none(self):
        """Empty sponsor string must be stored as None, not empty string."""
        adapter = OlisAdapter(bill_data=[_FAILED_FIXTURE])
        result = adapter.fetch()
        bill = result.records[0]
        assert bill.sponsor is None

    def test_no_bill_data_returns_error(self, tmp_path):
        """Live fetch fails and no cache exists — adapter returns one graceful error."""
        with patch("titan.sources.olis.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("connection refused")
            adapter = OlisAdapter(cache_dir=tmp_path)
            result = adapter.fetch()
        assert not result.ok()
        assert len(result.errors) == 1

    def test_chamber_preserved(self):
        adapter = OlisAdapter(bill_data=[_ENROLLED_FIXTURE])
        result = adapter.fetch()
        assert result.records[0].chamber == "Senate"

    def test_provenance_source_name_is_olis(self):
        adapter = OlisAdapter(bill_data=[_INTRODUCED_FIXTURE])
        result = adapter.fetch()
        assert result.records[0].provenance.source_name == "OLIS"
