# @domain:   citizens_source
# @module:   publication_builder
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""IssueBuilder — assembles Metro Citizens Brief issues.

Enforces neutrality gate on every section before accepting it.
Produces markdown text. PDF and diagram are separate renderers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cls_pdx1.models import Anomaly, Issue, IssueSection, Signal, _make_id
from cls_pdx1.neutrality.section import section_gate

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IssueBuilder:
    """Accumulate sections for a single MCB issue, enforcing gates throughout."""

    def __init__(self, issue_number: int) -> None:
        self.issue_number = issue_number
        self._sections: list[IssueSection] = []
        self._signal_ids: list[str] = []
        self._anomaly_ids: list[str] = []
        self._rejected: list[tuple[str, list[str]]] = []

    def add_section(
        self,
        title: str,
        body: str,
        source_uri: str,
        section_type: str = "narrative",
        entity_ids: Optional[list[str]] = None,
        official_ids: Optional[list[str]] = None,
        bill_ids: Optional[list[str]] = None,
    ) -> bool:
        """Add a section. Returns False (and records reason) if neutrality gates fail."""
        ok, failures = section_gate(title, body, source_uri)
        if not ok:
            self._rejected.append((title, failures))
            logger.warning("Section rejected — %s: %s", title, failures)
            return False

        self._sections.append(
            IssueSection(
                title=title,
                body=body,
                source_uri=source_uri,
                section_type=section_type,
                entity_ids=entity_ids or [],
                official_ids=official_ids or [],
                bill_ids=bill_ids or [],
            )
        )
        return True

    def attach_signal(self, signal: Signal) -> None:
        self._signal_ids.append(signal.signal_id)

    def attach_anomaly(self, anomaly: Anomaly) -> None:
        self._anomaly_ids.append(anomaly.anomaly_id)

    def build(self, title: Optional[str] = None) -> Issue:
        now = _now()
        issue_id = _make_id("issue", str(self.issue_number), now.isoformat()[:10])
        return Issue(
            issue_id=issue_id,
            issue_number=self.issue_number,
            title=title or f"Metro Citizens Brief — Issue {self.issue_number}",
            published_at=now,
            sections=list(self._sections),
            signal_ids=list(self._signal_ids),
            anomaly_ids=list(self._anomaly_ids),
        )

    def rejected_sections(self) -> list[tuple[str, list[str]]]:
        return list(self._rejected)

    def section_count(self) -> int:
        return len(self._sections)
