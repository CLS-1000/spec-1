from __future__ import annotations

from datetime import datetime, timezone

from cls_congress.models import Provenance, Signal
from cls_congress.pipeline import Pipeline
from cls_congress.sources.base import AdapterResult, BaseAdapter
from cls_congress.watch.base import WatchModule, WatchResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prov() -> Provenance:
    return Provenance(source_uri="https://example.com", source_name="test", fetched_at=_now())


class _EmptyAdapter(BaseAdapter):
    source_name = "empty"

    def fetch(self) -> AdapterResult:
        return AdapterResult(records=[], source_name=self.source_name)


class _SignalWatch(WatchModule):
    entity_id = "watch"
    entity_name = "watch"

    def collect(self) -> WatchResult:
        return WatchResult(
            entity_id=self.entity_id,
            entity_name=self.entity_name,
            signals=[
                Signal(
                    kind="watch_signal",
                    occurred_at=_now(),
                    detected_at=_now(),
                    entity_id="entity_1",
                    weight=6.0,
                    provenance=_prov(),
                )
            ],
        )


def test_zero_signals_no_issue():
    pipeline = Pipeline(adapters=[_EmptyAdapter()], watch_modules=[])
    result = pipeline.run_cycle()
    assert result.issue is None


def test_signals_can_generate_issue():
    pipeline = Pipeline(adapters=[_EmptyAdapter()], watch_modules=[_SignalWatch()])
    result = pipeline.run_cycle()
    assert result.issue is not None
    assert result.trigger is not None
    assert result.trigger.should_publish
