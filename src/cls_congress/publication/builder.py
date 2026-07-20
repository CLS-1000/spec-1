from __future__ import annotations

from datetime import datetime, timezone

from cls_congress.models import Anomaly, Issue, IssueSection, Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IssueBuilder:
    def __init__(self, *, title_prefix: str = "Congress Brief", max_signals: int = 10) -> None:
        self._title_prefix = title_prefix
        self._max_signals = max_signals

    def build(self, issue_number: int, signals: list[Signal], anomalies: list[Anomaly]) -> Issue:
        published_at = _now()
        sections: list[IssueSection] = []

        if anomalies:
            sections.append(
                IssueSection(
                    title="Key anomalies",
                    body="\n".join(f"- {a.description}" for a in anomalies),
                    section_type="anomaly",
                    source_uri=anomalies[0].provenance.source_uri,
                    entity_ids=[a.entity_id for a in anomalies],
                )
            )

        if signals:
            sections.append(
                IssueSection(
                    title="Signal summary",
                    body="\n".join(f"- {s.description or s.kind}" for s in signals[: self._max_signals]),
                    section_type="signal",
                    source_uri=signals[0].provenance.source_uri,
                    member_ids=[s.member_id for s in signals if s.member_id],
                    entity_ids=[s.entity_id for s in signals if s.entity_id],
                    bill_ids=[s.bill_id for s in signals if s.bill_id],
                )
            )

        return Issue(
            issue_id=Issue.make_id(issue_number, published_at),
            issue_number=issue_number,
            title=f"{self._title_prefix} #{issue_number}",
            published_at=published_at,
            sections=sections,
            signal_ids=[s.signal_id for s in signals],
            anomaly_ids=[a.anomaly_id for a in anomalies],
        )
