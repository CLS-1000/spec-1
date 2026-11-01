# @domain:   spec-1
# @module:   test_pdx1_watch
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan watch modules."""

from __future__ import annotations


from titan.watch.base import WATCH_REGISTRY
from titan.watch.pge import PgeWatchModule
from titan.watch.nw_natural import NwNaturalWatchModule
from titan.watch.ppb import PpbWatchModule
from titan.watch.water_bureau import WaterBureauWatchModule
from titan.watch.trimet import TrimetWatchModule
from titan.watch.ohsu import OhsuWatchModule
from titan.watch.schnitzer import SchnitzerWatchModule


class TestWatchRegistry:
    def test_pge_registered(self):
        assert "entity_pge_portland_general_electric" in WATCH_REGISTRY

    def test_nw_natural_registered(self):
        assert "entity_nwnatural_northwest_natural" in WATCH_REGISTRY

    def test_ppb_registered(self):
        assert "entity_portland_police_bureau" in WATCH_REGISTRY

    def test_water_bureau_registered(self):
        assert "entity_portland_water_bureau" in WATCH_REGISTRY

    def test_trimet_registered(self):
        assert "entity_trimet" in WATCH_REGISTRY

    def test_ohsu_registered(self):
        assert "entity_ohsu" in WATCH_REGISTRY

    def test_schnitzer_registered(self):
        assert "entity_schnitzer_family_network" in WATCH_REGISTRY


class TestPgeWatchModule:
    def test_empty_returns_no_signals(self):
        m = PgeWatchModule()
        result = m.collect()
        assert result.signals == []
        assert result.ok()

    def test_rate_case_produces_signal(self):
        m = PgeWatchModule(rate_cases=[{
            "case_number": "UE-12345",
            "filing_type": "rate_case",
            "description": "General rate case",
            "source_url": "https://apps.puc.state.or.us/edockets/",
        }])
        result = m.collect()
        assert len(result.signals) == 1
        assert result.signals[0].kind == "pge_rate_case_filed"
        assert result.signals[0].entity_id == PgeWatchModule.entity_id

    def test_missing_case_number_skipped(self):
        m = PgeWatchModule(rate_cases=[{"case_number": "", "filing_type": "rate_case"}])
        result = m.collect()
        assert len(result.signals) == 0

    def test_signal_has_provenance(self):
        m = PgeWatchModule(rate_cases=[{"case_number": "UE-99", "source_url": "https://puc.state.or.us/"}])
        result = m.collect()
        assert result.signals[0].provenance.source_uri.startswith("https://")


class TestNwNaturalWatchModule:
    def test_rate_case_produces_signal(self):
        m = NwNaturalWatchModule(rate_cases=[{
            "case_number": "UM-9999",
            "filing_type": "rate_case",
            "source_url": "https://apps.puc.state.or.us/edockets/",
        }])
        result = m.collect()
        assert len(result.signals) == 1
        assert result.signals[0].kind == "nwnatural_rate_case_filed"


class TestPpbWatchModule:
    def test_budget_event_produces_signal(self):
        m = PpbWatchModule(events=[{
            "type": "budget",
            "description": "FY2025 budget approved",
            "source_url": "https://www.portland.gov/police",
        }])
        result = m.collect()
        assert len(result.signals) == 1
        assert result.signals[0].kind == "ppb_budget_change"

    def test_oversight_event(self):
        m = PpbWatchModule(events=[{
            "type": "oversight",
            "description": "COCL report issued",
            "source_url": "https://www.portland.gov/police",
        }])
        result = m.collect()
        assert result.signals[0].kind == "ppb_oversight_decision"

    def test_unknown_event_type_skipped(self):
        m = PpbWatchModule(events=[{"type": "unrecognised", "description": "x", "source_url": "https://portland.gov"}])
        result = m.collect()
        assert len(result.signals) == 0


class TestWaterBureauWatchModule:
    def test_rate_event_produces_signal(self):
        m = WaterBureauWatchModule(events=[{
            "type": "rate_proposal",
            "description": "5% rate increase proposed",
            "source_url": "https://www.portland.gov/water",
        }])
        result = m.collect()
        assert result.signals[0].kind == "water_bureau_rate_proposal"

    def test_contract_event(self):
        m = WaterBureauWatchModule(events=[{
            "type": "contract_award",
            "description": "Infrastructure contract awarded",
            "source_url": "https://www.portland.gov/water",
        }])
        result = m.collect()
        assert result.signals[0].kind == "water_bureau_contract_awarded"


class TestTrimetWatchModule:
    def test_board_event_produces_signal(self):
        m = TrimetWatchModule(events=[{
            "type": "board_meeting",
            "description": "Board appointment",
            "source_url": "https://trimet.org/",
        }])
        result = m.collect()
        assert result.signals[0].kind == "trimet_board_appointment"

    def test_fare_event(self):
        m = TrimetWatchModule(events=[{
            "type": "fare_change",
            "description": "Fare increase proposed",
            "source_url": "https://trimet.org/",
        }])
        result = m.collect()
        assert result.signals[0].kind == "trimet_fare_change_proposed"
        assert result.signals[0].weight == 3.0


class TestOhsuWatchModule:
    def test_board_appointment_signal(self):
        m = OhsuWatchModule(events=[{
            "type": "board_appointment",
            "description": "Governor appoints new board member",
            "source_url": "https://www.ohsu.edu/",
        }])
        result = m.collect()
        assert result.signals[0].kind == "ohsu_board_appointment"
        assert result.signals[0].weight == 3.0


class TestSchnitzerWatchModule:
    def test_donation_event(self):
        m = SchnitzerWatchModule(events=[{
            "type": "donation_spike",
            "description": "Schnitzer PAC donation detected",
            "source_url": "https://sos.oregon.gov/elections/Pages/orestar.aspx",
        }])
        result = m.collect()
        assert result.signals[0].kind == "schnitzer_donation_spike"

    def test_property_event(self):
        m = SchnitzerWatchModule(events=[{
            "type": "property_transaction",
            "description": "Downtown property sold",
            "source_url": "https://example.com/assessor",
        }])
        result = m.collect()
        assert result.signals[0].kind == "schnitzer_property_transaction"
