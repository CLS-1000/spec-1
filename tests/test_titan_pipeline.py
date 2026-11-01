# @domain:   spec-1
# @module:   test_pdx1_pipeline
# @loc:      gh_main
# @status:   testing
# @depends:  NONE

"""Tests for titan.pipeline orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone


from titan.models import Affiliation, Bill, ConfidenceTier, EdgeType, Jurisdiction, Provenance, Signal, _make_id
from titan.pipeline import CycleResult, Pipeline
from titan.sources.base import AdapterResult, BaseAdapter
from titan.triggers import TriggerPolicy
from titan.watch.base import WatchModule, WatchResult

from datetime import date


def _now():
    return datetime.now(timezone.utc)


def _prov():
    return Provenance(source_uri="https://example.com/x", source_name="t", fetched_at=_now())


class _GoodAdapter(BaseAdapter):
    source_name = "good_source"

    def __init__(self, records):
        self._records = records

    def fetch(self) -> AdapterResult:
        return AdapterResult(records=self._records, source_name=self.source_name)


class _ErrorAdapter(BaseAdapter):
    source_name = "bad_source"

    def fetch(self) -> AdapterResult:
        return AdapterResult(errors=["network timeout"], source_name=self.source_name)


class _RaisingAdapter(BaseAdapter):
    source_name = "raising_source"

    def fetch(self) -> AdapterResult:
        raise RuntimeError("adapter exploded")


class _GoodWatcher(WatchModule):
    entity_id = "ent_test"
    entity_name = "Test Entity"

    def __init__(self, signals):
        self._sigs = signals

    def collect(self) -> WatchResult:
        return WatchResult(entity_id=self.entity_id, entity_name=self.entity_name, signals=self._sigs)


class _ErrorWatcher(WatchModule):
    entity_id = "ent_error"
    entity_name = "Error Entity"

    def collect(self) -> WatchResult:
        return WatchResult(entity_id=self.entity_id, entity_name=self.entity_name, errors=["fetch failed"])


def _aff():
    return Affiliation(
        official_id="off_1",
        entity_id="ent_1",
        edge_type=EdgeType.DONATION,
        confidence=ConfidenceTier.HARD_RECORD,
        observed_at=_now(),
        valid_from=date(2024, 1, 1),
        provenance=_prov(),
    )


def _signal():
    return Signal(kind="test_event", occurred_at=_now(), detected_at=_now(), provenance=_prov(), weight=2.0)


class TestPipelineBasic:
    def test_empty_pipeline_runs_without_error(self):
        p = Pipeline()
        result = p.run_cycle()
        assert isinstance(result, CycleResult)
        assert result.trigger is not None

    def test_adapter_affiliations_collected(self):
        aff = _aff()
        p = Pipeline(adapters=[_GoodAdapter([aff])])
        result = p.run_cycle()
        assert len(result.affiliations) == 1

    def test_adapter_bills_collected(self):
        bill = Bill(
            bill_id=_make_id("bill", str(int(Jurisdiction.STATE_OREGON)), "HB 1"),
            external_id="HB 1",
            title="Test",
            jurisdiction=Jurisdiction.STATE_OREGON,
            chamber="House",
            source_url="https://oregonlegislature.gov/",
            provenance=_prov(),
        )
        p = Pipeline(adapters=[_GoodAdapter([bill])])
        result = p.run_cycle()
        assert len(result.bills) == 1

    def test_adapter_errors_captured(self):
        p = Pipeline(adapters=[_ErrorAdapter()])
        result = p.run_cycle()
        assert "bad_source" in result.adapter_errors

    def test_raising_adapter_does_not_crash_pipeline(self):
        p = Pipeline(adapters=[_RaisingAdapter()])
        result = p.run_cycle()
        assert "raising_source" in result.adapter_errors

    def test_watch_signals_collected(self):
        sig = _signal()
        p = Pipeline(watch_modules=[_GoodWatcher([sig])])
        result = p.run_cycle()
        assert len(result.signals) == 1

    def test_watch_errors_captured(self):
        p = Pipeline(watch_modules=[_ErrorWatcher()])
        result = p.run_cycle()
        assert "Error Entity" in result.watch_errors

    def test_trigger_evaluates(self):
        sigs = [_signal() for _ in range(5)]
        policy = TriggerPolicy(signal_weight_threshold=5.0, min_spacing_days=0)
        p = Pipeline(
            watch_modules=[_GoodWatcher(sigs)],
            trigger_policy=policy,
        )
        result = p.run_cycle()
        assert result.trigger is not None

    def test_multiple_adapters_merged(self):
        p = Pipeline(adapters=[_GoodAdapter([_aff()]), _GoodAdapter([_aff()])])
        result = p.run_cycle()
        assert len(result.affiliations) == 2
