# @domain:   citizens_source
# @module:   pipeline
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""PDX-1i pipeline orchestrator.

Runs all source adapters and watch modules, evaluates publication trigger,
and returns collected signals/anomalies. Failure-first: adapter errors are
logged and skipped — the pipeline does not crash on partial source failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.anomaly import RollingBaseline
from cls_pdx1.models import Affiliation, Anomaly, Bill, Signal
from cls_pdx1.sources.base import AdapterResult, BaseAdapter
from cls_pdx1.triggers import TriggerDecision, TriggerPolicy, TriggerState, evaluate_trigger
from cls_pdx1.watch.base import WatchModule

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CycleResult:
    """Aggregate output of one PDX-1i ingest cycle.

    ok() returns True only when all adapters and watch modules completed
    without errors — partial failures are logged but do not block the cycle.
    """

    ran_at: datetime = field(default_factory=_now)
    affiliations: list[Affiliation] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    trigger: Optional[TriggerDecision] = None
    adapter_errors: dict[str, list[str]] = field(default_factory=dict)    # source_name → errors
    watch_errors: dict[str, list[str]] = field(default_factory=dict)      # entity_name → errors

    def ok(self) -> bool:
        return not self.adapter_errors and not self.watch_errors


class Pipeline:
    """PDX-1i ingest cycle orchestrator — adapters → watch → anomaly → trigger."""

    def __init__(
        self,
        adapters: Optional[list[BaseAdapter]] = None,
        watch_modules: Optional[list[WatchModule]] = None,
        baseline: Optional[RollingBaseline] = None,
        trigger_state: Optional[TriggerState] = None,
        trigger_policy: Optional[TriggerPolicy] = None,
    ) -> None:
        self._adapters = adapters or []
        self._watch_modules = watch_modules or []
        self._baseline = baseline or RollingBaseline()
        self._trigger_state = trigger_state or TriggerState()
        self._trigger_policy = trigger_policy or TriggerPolicy()

    def run_cycle(self) -> CycleResult:
        result = CycleResult()

        # Run source adapters
        for adapter in self._adapters:
            try:
                ar: AdapterResult = adapter.fetch()
                if ar.errors:
                    result.adapter_errors[adapter.source_name] = ar.errors
                    logger.warning("%s: %d errors", adapter.source_name, len(ar.errors))
                for record in ar.records:
                    if isinstance(record, Affiliation):
                        result.affiliations.append(record)
                    elif isinstance(record, Bill):
                        result.bills.append(record)
            except Exception as exc:
                result.adapter_errors[adapter.source_name] = [str(exc)]
                logger.error("Adapter %s raised: %s", adapter.source_name, exc)

        # Run watch modules
        for wm in self._watch_modules:
            try:
                wr = wm.collect()
                if wr.errors:
                    result.watch_errors[wm.entity_name] = wr.errors
                for signal in wr.signals:
                    result.signals.append(signal)
                    self._trigger_state.add_signal(signal)
                    self._baseline.ingest(signal)
            except Exception as exc:
                result.watch_errors[wm.entity_name] = [str(exc)]
                logger.error("Watch module %s raised: %s", wm.entity_name, exc)

        # Evaluate trigger
        result.trigger = evaluate_trigger(self._trigger_state, self._trigger_policy)
        if result.trigger.should_publish:
            logger.info("Publish trigger fired: %s", result.trigger.reason)

        logger.info(
            "Cycle complete: %d affiliations, %d bills, %d signals, trigger=%s",
            len(result.affiliations),
            len(result.bills),
            len(result.signals),
            result.trigger.should_publish,
        )
        return result
