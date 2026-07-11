from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cls_congress.anomaly import RollingBaseline
from cls_congress.models import Affiliation, Anomaly, Bill, Issue, Provenance, Signal
from cls_congress.publication.builder import IssueBuilder
from cls_congress.sources.base import AdapterResult, BaseAdapter
from cls_congress.triggers import TriggerDecision, TriggerPolicy, TriggerState, evaluate_trigger
from cls_congress.watch.base import WatchModule


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CycleResult:
    ran_at: datetime = field(default_factory=_now)
    affiliations: list[Affiliation] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    issue: Optional[Issue] = None
    trigger: Optional[TriggerDecision] = None
    adapter_errors: dict[str, list[str]] = field(default_factory=dict)
    watch_errors: dict[str, list[str]] = field(default_factory=dict)

    def ok(self) -> bool:
        return not self.adapter_errors and not self.watch_errors


class Pipeline:
    def __init__(
        self,
        *,
        adapters: Optional[list[BaseAdapter]] = None,
        watch_modules: Optional[list[WatchModule]] = None,
        baseline: Optional[RollingBaseline] = None,
        trigger_state: Optional[TriggerState] = None,
        trigger_policy: Optional[TriggerPolicy] = None,
        issue_builder: Optional[IssueBuilder] = None,
    ) -> None:
        self._adapters = adapters or []
        self._watch_modules = watch_modules or []
        self._baseline = baseline or RollingBaseline()
        self._trigger_state = trigger_state or TriggerState()
        self._trigger_policy = trigger_policy or TriggerPolicy()
        self._issue_builder = issue_builder or IssueBuilder()
        self._issue_counter = 0

    def run_cycle(self) -> CycleResult:
        result = CycleResult()

        for adapter in self._adapters:
            try:
                fetched: AdapterResult = adapter.fetch()
            except Exception as exc:
                result.adapter_errors[adapter.source_name] = [str(exc)]
                continue

            if fetched.errors:
                result.adapter_errors[adapter.source_name] = fetched.errors

            for record in fetched.records:
                if isinstance(record, Affiliation):
                    result.affiliations.append(record)
                elif isinstance(record, Bill):
                    result.bills.append(record)
                elif isinstance(record, Signal):
                    result.signals.append(record)
                    self._trigger_state.add_signal(record)
                    self._baseline.ingest(record)

        for watcher in self._watch_modules:
            try:
                watched = watcher.collect()
            except Exception as exc:
                result.watch_errors[watcher.entity_name] = [str(exc)]
                continue

            if watched.errors:
                result.watch_errors[watcher.entity_name] = watched.errors

            for signal in watched.signals:
                result.signals.append(signal)
                self._trigger_state.add_signal(signal)
                self._baseline.ingest(signal)

        by_entity: dict[str, float] = defaultdict(float)
        for signal in result.signals:
            if signal.entity_id:
                by_entity[signal.entity_id] += signal.weight

        for entity_id, observed in by_entity.items():
            anomaly = self._baseline.evaluate(
                entity_id,
                observed,
                "cross_pillar_friction",
                Provenance(source_uri="pipeline://congress", source_name="Congress Pipeline", fetched_at=_now()),
            )
            if anomaly:
                result.anomalies.append(anomaly)
                self._trigger_state.add_anomaly(anomaly)

        result.trigger = evaluate_trigger(self._trigger_state, self._trigger_policy)

        if result.trigger.should_publish:
            self._issue_counter += 1
            result.issue = self._issue_builder.build(self._issue_counter, result.signals, result.anomalies)
            self._trigger_state.last_published_at = result.issue.published_at
            self._trigger_state.pending_signals.clear()
            self._trigger_state.pending_anomalies.clear()

        return result


def run_congress_cycle(pipeline: Pipeline) -> CycleResult:
    return pipeline.run_cycle()
